"""
Voice Emotion Detection Module
================================
Combines OpenSMILE eGeMAPS for interpretable acoustic features
with wav2vec2 for speech emotion classification and Whisper for ASR.

Feature hierarchy:
  1. OpenSMILE eGeMAPS  — 88 functionals → key subset extracted
  2. torchaudio MFCC    — 13-dim MFCC + delta + delta-delta (if torch available)
  3. librosa fallback   — pitch, loudness, MFCC, spectral features

New computed signals (psychoacoustic research-backed):
  - distress_index   : Composite of jitter, shimmer, 1/HNR, pitch variability
  - pause_density    : Proportion of silence in speech (~hesitancy / low energy)
  - mfcc_vector      : Full 13-dim MFCC mean (for downstream ML if needed)

Privacy: Only extracted features are stored — raw audio is NEVER persisted.
"""

import os
import numpy as np
from typing import Optional, List

# ============================================
# LAZY MODEL LOADING (Singleton)
# ============================================

_opensmile_extractor = None
_voice_emotion_pipeline = None
_asr_pipeline = None


def _get_opensmile_extractor():
    """Lazy-load OpenSMILE eGeMAPS feature extractor"""
    global _opensmile_extractor
    if _opensmile_extractor is None:
        try:
            import opensmile
            _opensmile_extractor = opensmile.Smile(
                feature_set=opensmile.FeatureSet.eGeMAPSv02,
                feature_level=opensmile.FeatureLevel.Functionals,
            )
            print("[VOICE] ✅ OpenSMILE eGeMAPS extractor loaded")
        except ImportError:
            print("[VOICE] ⚠️ opensmile not installed — using librosa fallback")
            _opensmile_extractor = "fallback"
        except Exception as e:
            print(f"[VOICE] ⚠️ OpenSMILE init failed: {e} — using librosa fallback")
            _opensmile_extractor = "fallback"
    return _opensmile_extractor


def _get_voice_emotion_pipeline():
    """Lazy-load wav2vec2 speech emotion recognition pipeline"""
    global _voice_emotion_pipeline
    if _voice_emotion_pipeline is None:
        try:
            from transformers import pipeline
            _voice_emotion_pipeline = pipeline(
                "audio-classification",
                model="r-f/wav2vec-english-speech-emotion-recognition",
                top_k=5
            )
            print("[VOICE] ✅ wav2vec2 emotion classifier loaded")
        except Exception as e:
            if "kenlm" in str(e) or "pyctcdecode" in str(e):
                print(f"[VOICE] ⚠️ Optional dependency missing for full decoder features: {e}")
            print(f"[VOICE] ⚠️ wav2vec2 model load failed: {e}")
            _voice_emotion_pipeline = "unavailable"
    return _voice_emotion_pipeline


def _get_asr_pipeline():
    """Lazy-load ASR pipeline for transcription (Whisper Tiny)"""
    global _asr_pipeline
    if _asr_pipeline is None:
        try:
            from transformers import pipeline
            print("[VOICE] ⏳ Loading ASR model (openai/whisper-tiny)...")
            _asr_pipeline = pipeline(
                "automatic-speech-recognition",
                model="openai/whisper-tiny",
            )
            print("[VOICE] ✅ ASR model loaded")
        except Exception as e:
            print(f"[VOICE] ⚠️ ASR model load failed: {e}")
            _asr_pipeline = "unavailable"
    return _asr_pipeline


# ============================================
# TORCHAUDIO MFCC PIPELINE (primary upgrade)
# ============================================

def _extract_mfcc_with_torchaudio(audio_path: str, n_mfcc: int = 13) -> Optional[dict]:
    """
    Extract MFCC features using torchaudio for a proper mel-spectrogram pipeline.
    Returns a dict with mfcc_vector (13-dim), delta (velocity), delta2 (acceleration).
    Falls back to None if torchaudio/torch not available.
    """
    try:
        import torch
        import torchaudio
        import torchaudio.transforms as T

        waveform, sr = torchaudio.load(audio_path)

        # Convert to mono
        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)

        # Resample to 16kHz if needed
        if sr != 16000:
            resampler = T.Resample(orig_freq=sr, new_freq=16000)
            waveform = resampler(waveform)
            sr = 16000

        # MFCC transform: 13 coefficients, hann window
        mfcc_transform = T.MFCC(
            sample_rate=sr,
            n_mfcc=n_mfcc,
            melkwargs={
                "n_fft": 400,
                "hop_length": 160,
                "n_mels": 40,
                "f_min": 80.0,
                "f_max": 8000.0,
            }
        )
        mfcc = mfcc_transform(waveform)   # shape: [1, n_mfcc, time]
        mfcc = mfcc.squeeze(0)            # [n_mfcc, time]

        # Delta and delta-delta (velocity + acceleration)
        delta_transform = T.ComputeDeltas()
        mfcc_delta  = delta_transform(mfcc)
        mfcc_delta2 = delta_transform(mfcc_delta)

        mfcc_np     = mfcc.numpy()        # [13, T]
        delta_np    = mfcc_delta.numpy()
        delta2_np   = mfcc_delta2.numpy()

        mfcc_means      = mfcc_np.mean(axis=1).tolist()       # 13 scalars
        delta_means     = delta_np.mean(axis=1).tolist()
        delta2_means    = delta2_np.mean(axis=1).tolist()

        # Energy-based pause / silence detection
        # Frames with energy below threshold are considered silent
        energy = mfcc_np[0]   # MFCC-0 is log energy
        energy_threshold = float(np.percentile(energy, 25))
        pause_frames = np.sum(energy < energy_threshold)
        pause_density = float(pause_frames / max(len(energy), 1))

        print(f"[VOICE] 🎵 torchaudio MFCC extracted: mfcc_0={mfcc_means[0]:.2f}, pause_density={pause_density:.2f}")

        return {
            "mfcc_vector": mfcc_means,
            "mfcc_delta":  delta_means,
            "mfcc_delta2": delta2_means,
            "pause_density": float(pause_density),
            "extraction_method": "torchaudio_mfcc",
        }

    except ImportError:
        print("[VOICE] ⚠️ torchaudio not available — will use librosa for MFCC")
        return None
    except Exception as e:
        print(f"[VOICE] ⚠️ torchaudio MFCC failed: {e}")
        return None


# ============================================
# PSYCHOACOUSTIC DISTRESS INDEX
# ============================================

def _compute_distress_index(features: dict) -> float:
    """
    Composite psychoacoustic distress index (0 = healthy, 1 = high distress).

    Based on clinical voice research:
    - High jitter (pitch perturbation)    → vocal tension, anxiety
    - High shimmer (amplitude variation)  → emotional dysregulation
    - Low HNR (breathy/rough voice)       → depression, sadness marker
    - High pitch variability              → anxiety / rapid arousal
    - Low pause_density adjusted          → monotone depression marker

    Weights derived from literature (Cummins et al. 2015; Alghowinem et al. 2013).
    """
    # --- jitter component (0-1, normalized to typical clinical range 0-2%) ---
    jitter_raw = features.get("jitter", 0.0)
    jitter_norm = min(1.0, jitter_raw / 0.02)        # 2% = max clinical concern

    # --- shimmer component (0-1, normalized to 0-3 dB) ---
    shimmer_raw = features.get("shimmer", 0.0)
    shimmer_norm = min(1.0, shimmer_raw / 3.0)

    # --- HNR component: low HNR → high distress ---
    hnr_raw = features.get("hnr", 15.0)              # 15 dB is typical healthy HNR
    # Invert: HNR of 0 dB → distress 1.0, HNR ≥ 25 dB → distress 0.0
    hnr_distress = max(0.0, min(1.0, 1.0 - (hnr_raw / 25.0)))

    # --- pitch variability (normalised pitch std) ---
    pitch_std = features.get("pitch_std", 0.0)
    pitch_std_norm = min(1.0, pitch_std / 10.0)       # 10 semitones std → max concern

    # --- pause density: very high (>0.6) or very low (<0.1) both signal distress ---
    pause_density = features.get("pause_density", 0.25)
    # U-shaped penalty: 0.2-0.4 is normal; extremes get penalised
    pause_distress = abs(pause_density - 0.3) / 0.7   # 0 at 0.3, 1 at 0 or 1
    pause_distress = min(1.0, pause_distress)

    # --- Weighted combination ---
    distress = (
        0.30 * jitter_norm +
        0.25 * shimmer_norm +
        0.25 * hnr_distress +
        0.10 * pitch_std_norm +
        0.10 * pause_distress
    )
    return round(float(min(max(distress, 0.0), 1.0)), 3)


# ============================================
# FEATURE EXTRACTION (OpenSMILE eGeMAPS)
# ============================================

def extract_acoustic_features(audio_path: str) -> dict:
    """
    Extract interpretable acoustic features from audio.

    Primary:  OpenSMILE eGeMAPS (88 functionals → key subset)
    Fallback: librosa pitch/loudness/MFCC pipeline

    Additional signals always computed:
    - torchaudio MFCC vector (13-dim) when torch is available
    - distress_index  — composite psychoacoustic distress score
    - pause_density   — proportion of silent frames

    Args:
        audio_path: Path to audio file (WAV, MP3, WebM)

    Returns:
        Dictionary of interpretable acoustic + psychoacoustic features
    """
    extractor = _get_opensmile_extractor()

    if extractor != "fallback" and extractor is not None:
        features = _extract_with_opensmile(extractor, audio_path)
    else:
        features = _extract_with_librosa(audio_path)

    # --- Augment with torchaudio MFCC (always attempt) ---
    torchaudio_result = _extract_mfcc_with_torchaudio(audio_path)
    if torchaudio_result:
        features["mfcc_vector"]    = torchaudio_result["mfcc_vector"]
        features["mfcc_delta"]     = torchaudio_result["mfcc_delta"]
        features["mfcc_delta2"]    = torchaudio_result["mfcc_delta2"]
        # Prefer torchaudio pause_density if OpenSMILE didn't compute it
        if features.get("pause_density", 0.0) == 0.0:
            features["pause_density"] = torchaudio_result["pause_density"]
    else:
        # Ensure key exists even without torchaudio
        if "mfcc_vector" not in features:
            features["mfcc_vector"] = [features.get("mfcc_1_mean", 0.0)] + [0.0] * 12
        if "mfcc_delta" not in features:
            features["mfcc_delta"] = [0.0] * 13
        if "mfcc_delta2" not in features:
            features["mfcc_delta2"] = [0.0] * 13

    # --- Compute psychoacoustic distress index ---
    features["distress_index"] = _compute_distress_index(features)

    print(f"[VOICE] 📊 Distress index: {features['distress_index']:.2f} | "
          f"Pause density: {features.get('pause_density', 0):.2f} | "
          f"Arousal: {features.get('arousal', 0.5):.2f}")

    return features


def _extract_with_opensmile(extractor, audio_path: str) -> dict:
    """Extract features using OpenSMILE eGeMAPS"""
    try:
        features_df = extractor.process_file(audio_path)
        row = features_df.iloc[0]

        result = {
            "pitch_mean":   float(row.get("F0semitoneFrom27.5Hz_sma3nz_amean", 0)),
            "pitch_std":    float(row.get("F0semitoneFrom27.5Hz_sma3nz_stddevNorm", 0)),
            "loudness_mean": float(row.get("loudness_sma3_amean", 0)),
            "loudness_std": float(row.get("loudness_sma3_stddevNorm", 0)),
            "jitter":       float(row.get("jitterLocal_sma3nz_amean", 0)),
            "shimmer":      float(row.get("shimmerLocaldB_sma3nz_amean", 0)),
            "hnr":          float(row.get("HNRdBACF_sma3nz_amean", 0)),
            "speech_rate":  float(row.get("StddevUnvoicedSegmentLength", 0)),
            "mfcc_1_mean":  float(row.get("mfcc1_sma3_amean", 0)),
            "spectral_flux": float(row.get("spectralFlux_sma3_amean", 0)),
            # pause density via voiced-segment proportion
            "pause_density": max(0.0, min(1.0, 1.0 - float(row.get("MeanVoicedSegmentLengthSec", 0.5)))),
            "extraction_method": "opensmile_egemaps",
        }

        result["arousal"] = _estimate_arousal(result)
        result["valence"] = _estimate_valence(result)

        print(f"[VOICE] eGeMAPS features: pitch={result['pitch_mean']:.1f}, "
              f"loudness={result['loudness_mean']:.2f}, "
              f"jitter={result['jitter']:.4f}, shimmer={result['shimmer']:.4f}, "
              f"arousal={result['arousal']:.2f}")
        return result

    except Exception as e:
        print(f"[VOICE] OpenSMILE extraction failed: {e}, falling back to librosa")
        return _extract_with_librosa(audio_path)


def _extract_with_librosa(audio_path: str) -> dict:
    """Feature extraction using librosa (primary fallback)"""
    try:
        import librosa

        # ── Load audio ──
        try:
            y, sr = librosa.load(audio_path, sr=16000, mono=True)
            print(f"[VOICE] 📊 librosa loaded: {len(y)} samples @ {sr}Hz")
        except Exception as load_err:
            print(f"[VOICE] ⚠️ librosa.load with sr=16000 failed: {load_err}")
            try:
                y, sr = librosa.load(audio_path, sr=None, mono=True)
                if sr != 16000:
                    y = librosa.resample(y, orig_sr=sr, target_sr=16000)
                    sr = 16000
            except Exception as e2:
                print(f"[VOICE] ❌ librosa load (both methods) failed: {e2}")
                return _empty_features(f"librosa_failed_{str(e2)[:40]}")

        if len(y) == 0:
            print("[VOICE] ⚠️ Audio array is empty after loading")
            return _empty_features("librosa_empty")

        # ── Pitch (F0) via pyin ──
        f0, voiced_flag, voiced_probs = librosa.pyin(
            y, fmin=librosa.note_to_hz('C2'),
            fmax=librosa.note_to_hz('C7'), sr=sr
        )
        f0_valid = f0[~np.isnan(f0)] if f0 is not None else np.array([0.0])

        # ── Loudness (RMS energy) ──
        rms = librosa.feature.rms(y=y)[0]

        # ── MFCCs (13 coefficients) ──
        mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        mfcc_means  = mfccs.mean(axis=1).tolist()   # [13 scalars]
        mfcc_deltas = librosa.feature.delta(mfccs).mean(axis=1).tolist()
        mfcc_d2     = librosa.feature.delta(mfccs, order=2).mean(axis=1).tolist()

        # ── Spectral centroid ──
        spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]

        # ── Pause density via voiced flag ──
        if voiced_flag is not None and len(voiced_flag) > 0:
            voiced_ratio    = float(np.sum(voiced_flag) / max(len(voiced_flag), 1))
            pause_density   = max(0.0, min(1.0, 1.0 - voiced_ratio))
        else:
            pause_density = 0.25       # neutral default

        result = {
            "pitch_mean":    float(np.mean(f0_valid))       if len(f0_valid) > 0 else 0.0,
            "pitch_std":     float(np.std(f0_valid))        if len(f0_valid) > 0 else 0.0,
            "loudness_mean": float(np.mean(rms)),
            "loudness_std":  float(np.std(rms))             if len(rms) > 1 else 0.0,
            "jitter":        float(np.mean(np.abs(np.diff(f0_valid)))) if len(f0_valid) > 1 else 0.0,
            "shimmer":       float(np.mean(np.abs(np.diff(rms))))      if len(rms) > 1 else 0.0,
            "hnr":           0.0,                           # HNR not easily computed via librosa
            "speech_rate":   float(np.sum(voiced_flag) / (len(y) / sr)) if voiced_flag is not None else 0.0,
            "mfcc_1_mean":   float(mfcc_means[1]) if len(mfcc_means) > 1 else 0.0,
            "mfcc_vector":   mfcc_means,
            "mfcc_delta":    mfcc_deltas,
            "mfcc_delta2":   mfcc_d2,
            "spectral_flux": float(np.mean(np.abs(np.diff(spectral_centroid)))),
            "pause_density": pause_density,
            "extraction_method": "librosa_fallback",
        }

        result["arousal"] = _estimate_arousal(result)
        result["valence"] = _estimate_valence(result)

        print(f"[VOICE] librosa features: pitch={result['pitch_mean']:.1f}, "
              f"loudness={result['loudness_mean']:.4f}, "
              f"pause_density={result['pause_density']:.2f}")
        return result

    except ImportError:
        print("[VOICE] ⚠️ librosa not installed — returning empty features")
        return _empty_features("no_extractor")
    except Exception as e:
        print(f"[VOICE] librosa extraction failed: {e}")
        return _empty_features("librosa_error")


def _empty_features(method: str) -> dict:
    """Return empty feature dict when extraction fails"""
    return {
        "pitch_mean": 0.0,   "pitch_std": 0.0,
        "loudness_mean": 0.0, "loudness_std": 0.0,
        "jitter": 0.0,       "shimmer": 0.0,       "hnr": 0.0,
        "speech_rate": 0.0,  "mfcc_1_mean": 0.0,
        "mfcc_vector":  [0.0] * 13,
        "mfcc_delta":   [0.0] * 13,
        "mfcc_delta2":  [0.0] * 13,
        "spectral_flux": 0.0,
        "pause_density": 0.25,
        "arousal": 0.5,      "valence": 0.5,
        "distress_index": 0.0,
        "extraction_method": method,
    }


def _estimate_arousal(features: dict) -> float:
    """
    Estimate arousal (activation level) from acoustic features.
    High arousal: high pitch, high loudness, fast speech, high spectral flux
    Low arousal:  low pitch, low loudness, slow speech
    Returns 0 (very calm) → 1 (very activated)
    """
    pitch_norm    = min(max((features.get("pitch_mean", 0) - 100) / 200, 0), 1)
    loudness_norm = min(max(features.get("loudness_mean", 0) / 0.5, 0), 1)
    rate_norm     = min(max(features.get("speech_rate", 0) / 6, 0), 1)
    flux_norm     = min(max(features.get("spectral_flux", 0) / 100, 0), 1)

    arousal = 0.35 * pitch_norm + 0.30 * loudness_norm + 0.20 * rate_norm + 0.15 * flux_norm
    return round(min(max(arousal, 0), 1), 3)


def _estimate_valence(features: dict) -> float:
    """
    Estimate valence (positive/negative sentiment) from acoustic features.
    Positive valence: higher pitch, more harmonic, wider pitch range
    Negative valence: lower pitch, breathier, narrower range
    Returns 0 (very negative) → 1 (very positive)
    """
    pitch_norm = min(max((features.get("pitch_mean", 0) - 100) / 200, 0), 1)
    hnr_norm   = min(max(features.get("hnr", 0) / 20, 0), 1)
    pitch_var  = min(max(features.get("pitch_std", 0) / 50, 0), 1)

    valence = 0.40 * pitch_norm + 0.35 * hnr_norm + 0.25 * pitch_var
    return round(min(max(valence, 0), 1), 3)


# ============================================
# EMOTION CLASSIFICATION (wav2vec2)
# ============================================

_EMOTION_MAP = {
    "angry":    "anger",
    "calm":     "neutral",
    "disgust":  "disgust",
    "fearful":  "fear",
    "happy":    "joy",
    "neutral":  "neutral",
    "sad":      "sadness",
    "surprised": "surprise",
    "fear":     "fear",
    "anger":    "anger",
    "happiness": "joy",
    "sadness":  "sadness",
    "surprise": "surprise",
}


def classify_voice_emotion(audio_path: str) -> dict:
    """
    Classify emotion from speech using wav2vec2.

    Uses r-f/wav2vec-english-speech-emotion-recognition model
    (trained on SAVEE + RAVDESS + TESS; 97.5% accuracy on eval set).

    Args:
        audio_path: Path to audio file

    Returns:
        {emotion, confidence, raw_label, all_scores}
    """
    pipeline_cls = _get_voice_emotion_pipeline()

    if pipeline_cls == "unavailable":
        print("[VOICE] wav2vec2 unavailable — returning neutral")
        return {"emotion": "neutral", "confidence": 0.0, "raw_label": "unavailable", "all_scores": {}}

    try:
        import librosa

        try:
            y, sr = librosa.load(audio_path, sr=16000, mono=True)
            print(f"[VOICE] 🎵 Loaded for classification: {len(y)} samples @ {sr}Hz")
        except Exception as load_error:
            print(f"[VOICE] ⚠️ Load attempt 1 failed: {load_error}")
            try:
                y, sr = librosa.load(audio_path, sr=None, mono=True)
                if sr != 16000:
                    y = librosa.resample(y, orig_sr=sr, target_sr=16000)
                    sr = 16000
            except Exception as e2:
                print(f"[VOICE] ❌ Classification load failed: {e2}")
                return {"emotion": "neutral", "confidence": 0.0, "raw_label": "load_error", "all_scores": {}}

        if len(y) == 0:
            return {"emotion": "neutral", "confidence": 0.0, "raw_label": "empty", "all_scores": {}}

        results = pipeline_cls(y, top_k=5)

        if not results:
            return {"emotion": "neutral", "confidence": 0.0, "raw_label": "no_results", "all_scores": {}}

        top = results[0]
        raw_label  = top["label"].lower()
        confidence = float(top["score"])
        mapped_emotion = _EMOTION_MAP.get(raw_label, "neutral")

        all_scores = {}
        for r in results:
            label = _EMOTION_MAP.get(r["label"].lower(), r["label"].lower())
            all_scores[label] = round(float(r["score"]), 4)

        print(f"[VOICE] wav2vec2 emotion: {mapped_emotion} ({confidence:.2%}) [raw: {raw_label}]")

        return {
            "emotion":    mapped_emotion,
            "confidence": round(confidence, 4),
            "raw_label":  raw_label,
            "all_scores": all_scores,
        }

    except ImportError:
        print("[VOICE] ⚠️ librosa not installed — cannot load audio for classification")
        return {"emotion": "neutral", "confidence": 0.0, "raw_label": "no_librosa", "all_scores": {}}
    except Exception as e:
        print(f"[VOICE] Classification error: {e}")
        return {"emotion": "neutral", "confidence": 0.0, "raw_label": f"error: {e}", "all_scores": {}}


# ============================================
# EMOTION FUSION (Text + Voice)
# ============================================

def fuse_emotions(
    text_emotion: dict,
    voice_emotion: dict,
    alpha: float = 0.6
) -> dict:
    """
    Fuse text and voice emotion signals using confidence-weighted average.

    Strategy:
    - alpha controls text weight (default 0.6 = text slightly dominant)
    - If voice confidence < 0.3, rely on text alone
    - If text and voice agree, boost confidence
    - If they disagree, use the higher-confidence signal but flag conflict

    Args:
        text_emotion:  {emotion, confidence}
        voice_emotion: {emotion, confidence}
        alpha: Weight for text signal (0-1). 1.0=text only, 0.0=voice only
    """
    text_emo  = text_emotion.get("emotion", "neutral")
    text_conf = float(text_emotion.get("confidence", 0.5))
    voice_emo = voice_emotion.get("emotion", "neutral")
    voice_conf = float(voice_emotion.get("confidence", 0.0))

    if voice_conf < 0.3:
        return {
            "emotion": text_emo, "confidence": text_conf,
            "source": "text", "conflict": False,
            "text_emotion": text_emo, "voice_emotion": voice_emo,
        }

    if text_emo == voice_emo:
        combined_conf = min(0.95, text_conf * 0.7 + voice_conf * 0.3 + 0.1)
        return {
            "emotion": text_emo, "confidence": round(combined_conf, 3),
            "source": "agreement", "conflict": False,
            "text_emotion": text_emo, "voice_emotion": voice_emo,
        }

    text_weighted  = text_conf * alpha
    voice_weighted = voice_conf * (1 - alpha)

    if text_weighted >= voice_weighted:
        final_emotion = text_emo
        final_conf    = text_conf * 0.8
        source        = "text"
    else:
        final_emotion = voice_emo
        final_conf    = voice_conf * 0.8
        source        = "voice"

    print(f"[VOICE] Fusion conflict: text={text_emo}({text_conf:.2f}) vs "
          f"voice={voice_emo}({voice_conf:.2f}) → {final_emotion} (source: {source})")

    return {
        "emotion": final_emotion, "confidence": round(final_conf, 3),
        "source": source, "conflict": True,
        "text_emotion": text_emo, "voice_emotion": voice_emo,
    }


# ============================================
# ASR / TRANSCRIPTION
# ============================================

def transcribe_audio(audio_path: str) -> str:
    """
    Transcribe audio to text using Whisper-tiny (via Transformers pipeline).
    Loads audio via scipy/librosa to avoid ffmpeg dependency.

    Args:
        audio_path: Path to audio file

    Returns:
        Transcribed text string, or "" if failed
    """
    asr = _get_asr_pipeline()

    if asr == "unavailable":
        return ""

    try:
        if not os.path.exists(audio_path):
            print(f"[VOICE] ⚠️ Audio file not found for transcription: {audio_path}")
            return ""

        import numpy as np
        speech = None

        # 1. Try scipy.io.wavfile (fastest, no ffmpeg)
        try:
            import scipy.io.wavfile as wavfile
            from scipy import signal
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                sr, data = wavfile.read(audio_path)

            if data.dtype == np.int16:
                data = data.astype(np.float32) / 32768.0
            elif data.dtype == np.int32:
                data = data.astype(np.float32) / 2147483648.0
            elif data.dtype == np.uint8:
                data = (data.astype(np.float32) - 128.0) / 128.0
            if len(data.shape) > 1:
                data = data.mean(axis=1)
            if sr != 16000:
                samples = int(len(data) * 16000 / sr)
                data = signal.resample(data, samples)

            speech = data

        except Exception as e_scipy:
            print(f"[VOICE] ⚠️ scipy load failed: {e_scipy}")

        # 2. Fallback to librosa
        if speech is None:
            try:
                import librosa
                speech, _ = librosa.load(audio_path, sr=16000, mono=True)
                print("[VOICE] ✅ Audio loaded for ASR using librosa")
            except Exception as e_librosa:
                print(f"[VOICE] ❌ ASR audio loading failed (scipy & librosa): {e_librosa}")
                return ""

        result = asr(speech)
        text   = result.get("text", "").strip()

        if text:
            print(f"[VOICE] 📝 Transcription: \"{text}\"")
        else:
            print("[VOICE] ⚠️ Transcription resulted in empty text")

        return text

    except Exception as e:
        print(f"[VOICE] ❌ Transcription failed: {e}")
        return ""


# ============================================
# FULL VOICE ANALYSIS (unified convenience function)
# ============================================

def preload_all_voice_models() -> dict:
    """
    Eagerly load all voice ML models at server startup so that the first
    user voice request doesn't incur a 10-30s model download/load delay.

    Returns a status dict for logging.
    """
    status = {}

    print("[VOICE-PRELOAD] Loading OpenSMILE eGeMAPS extractor...")
    try:
        extractor = _get_opensmile_extractor()
        status["opensmile"] = "ok" if extractor != "fallback" else "fallback"
        print(f"[VOICE-PRELOAD] OpenSMILE: {status['opensmile']}")
    except Exception as e:
        status["opensmile"] = f"error: {e}"
        print(f"[VOICE-PRELOAD] OpenSMILE failed: {e}")

    print("[VOICE-PRELOAD] Loading wav2vec2 emotion classifier...")
    try:
        clf = _get_voice_emotion_pipeline()
        status["wav2vec2"] = "ok" if clf != "unavailable" else "unavailable"
        print(f"[VOICE-PRELOAD] wav2vec2: {status['wav2vec2']}")
    except Exception as e:
        status["wav2vec2"] = f"error: {e}"
        print(f"[VOICE-PRELOAD] wav2vec2 failed: {e}")

    print("[VOICE-PRELOAD] Loading Whisper-tiny ASR model...")
    try:
        asr = _get_asr_pipeline()
        status["whisper"] = "ok" if asr != "unavailable" else "unavailable"
        print(f"[VOICE-PRELOAD] Whisper: {status['whisper']}")
    except Exception as e:
        status["whisper"] = f"error: {e}"
        print(f"[VOICE-PRELOAD] Whisper failed: {e}")

    return status


def analyze_voice_full(audio_path: str) -> dict:
    """
    Run full voice analysis pipeline in ONE pass:
      1. Acoustic feature extraction (OpenSMILE → torchaudio → librosa)
      2. Emotion classification (wav2vec2)
      3. ASR transcription (Whisper-tiny)

    NOTE: Callers that only need features (voice_preprocessing_node) can
    use the returned `transcription` field and skip a second ASR call.

    Args:
        audio_path: Path to audio file

    Returns:
        {
            acoustic_features : dict  — full feature dict with distress_index, etc.
            emotion           : str   — mapped emotion label
            confidence        : float
            arousal           : float
            valence           : float
            distress_index    : float — psychoacoustic composite distress score
            pause_density     : float
            mfcc_vector       : list[float]  — 13-dim MFCC means
            all_scores        : dict
            extraction_method : str
            transcription     : str   — ASR output (reuse, don't call separately)
        }
    """
    features     = extract_acoustic_features(audio_path)
    emotion_info = classify_voice_emotion(audio_path)
    transcription = transcribe_audio(audio_path)

    return {
        "acoustic_features":  features,
        "emotion":            emotion_info.get("emotion", "neutral"),
        "confidence":         emotion_info.get("confidence", 0.0),
        "arousal":            features.get("arousal", 0.5),
        "valence":            features.get("valence", 0.5),
        "distress_index":     features.get("distress_index", 0.0),
        "pause_density":      features.get("pause_density", 0.25),
        "mfcc_vector":        features.get("mfcc_vector", [0.0] * 13),
        "all_scores":         emotion_info.get("all_scores", {}),
        "extraction_method":  features.get("extraction_method", "unknown"),
        "transcription":      transcription,
    }
