"""
Voice Emotion Detection Module
================================
Uses librosa for acoustic feature extraction, wav2vec2 for speech emotion
classification, and Deepgram Nova-2 for ASR transcription.

Feature extraction:
  - librosa: pitch (F0 via pyin), loudness (RMS), MFCC (13-dim + delta),
              spectral features, pause density via voiced-flag

Computed psychoacoustic signals:
  - distress_index : Composite of jitter, shimmer, pitch variability, pause density
  - pause_density  : Proportion of silent frames (hesitancy / low energy marker)
  - mfcc_vector    : 13-dim MFCC mean vector

Privacy: Only extracted features are stored  raw audio is NEVER persisted.
"""

import os
import numpy as np
from typing import Optional


# ============================================
# LAZY MODEL LOADING (Singleton)
# ============================================

_voice_emotion_pipeline = None


def _get_voice_emotion_pipeline():
    """Lazy-load wav2vec2 speech emotion recognition pipeline."""
    global _voice_emotion_pipeline
    if _voice_emotion_pipeline is None:
        try:
            from transformers import pipeline
            _voice_emotion_pipeline = pipeline(
                "audio-classification",
                model="r-f/wav2vec-english-speech-emotion-recognition",
                top_k=5
            )
            print("[VOICE] wav2vec2 emotion classifier loaded")
        except Exception as e:
            print(f"[VOICE] wav2vec2 load failed: {e}")
            _voice_emotion_pipeline = "unavailable"
    return _voice_emotion_pipeline



# ============================================
# PSYCHOACOUSTIC DISTRESS INDEX
# ============================================

def _compute_distress_index(features: dict) -> float:
    """
    Composite psychoacoustic distress index (0 = healthy, 1 = high distress).

    Based on clinical voice research:
    - High jitter (pitch perturbation)     vocal tension, anxiety
    - High shimmer (amplitude variation)   emotional dysregulation
    - Low HNR (breathy/rough voice)        depression, sadness marker
    - High pitch variability               anxiety / rapid arousal
    - Extreme pause density                monotone depression or fragmented speech

    Weights derived from literature (Cummins et al. 2015; Alghowinem et al. 2013).
    """
    jitter_raw   = features.get("jitter", 0.0)
    jitter_norm  = min(1.0, jitter_raw / 0.02)          # 2% = max clinical concern

    shimmer_raw  = features.get("shimmer", 0.0)
    shimmer_norm = min(1.0, shimmer_raw / 3.0)           # 3 dB = max clinical concern

    hnr_raw      = features.get("hnr", 15.0)             # 15 dB = typical healthy HNR
    hnr_distress = max(0.0, min(1.0, 1.0 - (hnr_raw / 25.0)))  # low HNR  high distress

    pitch_std      = features.get("pitch_std", 0.0)
    pitch_std_norm = min(1.0, pitch_std / 10.0)          # 10 semitones std  max concern

    pause_density  = features.get("pause_density", 0.25)
    # U-shaped penalty: 0.2-0.4 is normal; extremes signal distress
    pause_distress = min(1.0, abs(pause_density - 0.3) / 0.7)

    distress = (
        0.30 * jitter_norm  +
        0.25 * shimmer_norm +
        0.25 * hnr_distress +
        0.10 * pitch_std_norm +
        0.10 * pause_distress
    )
    return round(float(min(max(distress, 0.0), 1.0)), 3)


# ============================================
# AROUSAL / VALENCE ESTIMATORS
# ============================================

def _estimate_arousal(features: dict) -> float:
    """
    Estimate arousal (activation level) from acoustic features.
    High arousal: high pitch, high loudness, fast speech, high spectral flux.
    Returns 0 (very calm)  1 (very activated).
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
    Positive valence: higher pitch, more harmonic, wider pitch range.
    Returns 0 (very negative)  1 (very positive).
    """
    pitch_norm = min(max((features.get("pitch_mean", 0) - 100) / 200, 0), 1)
    hnr_norm   = min(max(features.get("hnr", 0) / 20, 0), 1)
    pitch_var  = min(max(features.get("pitch_std", 0) / 50, 0), 1)

    valence = 0.40 * pitch_norm + 0.35 * hnr_norm + 0.25 * pitch_var
    return round(min(max(valence, 0), 1), 3)


# ============================================
# ACOUSTIC FEATURE EXTRACTION (librosa  primary)
# ============================================

def _empty_features(method: str) -> dict:
    """Return safe zero-filled feature dict when extraction fails."""
    return {
        "pitch_mean": 0.0,    "pitch_std": 0.0,
        "loudness_mean": 0.0, "loudness_std": 0.0,
        "jitter": 0.0,        "shimmer": 0.0,       "hnr": 0.0,
        "speech_rate": 0.0,   "mfcc_1_mean": 0.0,
        "mfcc_vector":  [0.0] * 13,
        "mfcc_delta":   [0.0] * 13,
        "mfcc_delta2":  [0.0] * 13,
        "spectral_flux": 0.0,
        "pause_density": 0.25,
        "arousal": 0.5,       "valence": 0.5,
        "distress_index": 0.0,
        "extraction_method": method,
    }


def extract_acoustic_features(audio_path: str) -> dict:
    """
    Extract interpretable acoustic features from a WAV file using librosa.

    Returns a dict containing:
      pitch_mean, pitch_std, loudness_mean, loudness_std,
      jitter, shimmer, hnr (0  not computed by librosa),
      speech_rate, mfcc_vector (13-dim), mfcc_delta, mfcc_delta2,
      spectral_flux, pause_density,
      arousal, valence, distress_index
    """
    try:
        import librosa

        #  Load audio 
        try:
            y, sr = librosa.load(audio_path, sr=16000, mono=True)
            print(f"[VOICE] librosa loaded: {len(y)} samples @ {sr}Hz")
        except Exception as load_err:
            print(f"[VOICE] librosa.load (sr=16000) failed: {load_err}")
            try:
                y, sr = librosa.load(audio_path, sr=None, mono=True)
                if sr != 16000:
                    y = librosa.resample(y, orig_sr=sr, target_sr=16000)
                    sr = 16000
            except Exception as e2:
                print(f"[VOICE] librosa load (both methods) failed: {e2}")
                return _empty_features(f"librosa_failed")

        if len(y) == 0:
            print("[VOICE] Audio array is empty after loading")
            return _empty_features("librosa_empty")

        #  Pitch (F0) via pyin 
        f0, voiced_flag, _ = librosa.pyin(
            y, fmin=librosa.note_to_hz('C2'),
            fmax=librosa.note_to_hz('C7'), sr=sr
        )
        f0_valid = f0[~np.isnan(f0)] if f0 is not None else np.array([0.0])

        #  Loudness (RMS energy) 
        rms = librosa.feature.rms(y=y)[0]

        #  MFCCs (13 coefficients) 
        mfccs       = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        mfcc_means  = mfccs.mean(axis=1).tolist()
        mfcc_deltas = librosa.feature.delta(mfccs).mean(axis=1).tolist()
        mfcc_d2     = librosa.feature.delta(mfccs, order=2).mean(axis=1).tolist()

        #  Spectral centroid flux 
        spec_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]

        #  Pause density (via voiced flag) 
        if voiced_flag is not None and len(voiced_flag) > 0:
            voiced_ratio  = float(np.sum(voiced_flag) / max(len(voiced_flag), 1))
            pause_density = max(0.0, min(1.0, 1.0 - voiced_ratio))
        else:
            pause_density = 0.25    # neutral default

        result = {
            "pitch_mean":    float(np.mean(f0_valid))  if len(f0_valid) > 0 else 0.0,
            "pitch_std":     float(np.std(f0_valid))   if len(f0_valid) > 0 else 0.0,
            "loudness_mean": float(np.mean(rms)),
            "loudness_std":  float(np.std(rms))        if len(rms) > 1 else 0.0,
            "jitter":        float(np.mean(np.abs(np.diff(f0_valid)))) if len(f0_valid) > 1 else 0.0,
            "shimmer":       float(np.mean(np.abs(np.diff(rms))))      if len(rms) > 1 else 0.0,
            "hnr":           0.0,    # HNR not easily computed via librosa
            "speech_rate":   float(np.sum(voiced_flag) / (len(y) / sr)) if voiced_flag is not None else 0.0,
            "mfcc_1_mean":   float(mfcc_means[1]) if len(mfcc_means) > 1 else 0.0,
            "mfcc_vector":   mfcc_means,
            "mfcc_delta":    mfcc_deltas,
            "mfcc_delta2":   mfcc_d2,
            "spectral_flux": float(np.mean(np.abs(np.diff(spec_centroid)))),
            "pause_density": pause_density,
            "extraction_method": "librosa",
        }

        result["arousal"]       = _estimate_arousal(result)
        result["valence"]       = _estimate_valence(result)
        result["distress_index"] = _compute_distress_index(result)

        print(f"[VOICE] Features: pitch={result['pitch_mean']:.1f}Hz, "
              f"loudness={result['loudness_mean']:.4f}, "
              f"pause_density={result['pause_density']:.2f}, "
              f"distress_index={result['distress_index']:.2f}")
        return result

    except ImportError:
        print("[VOICE] librosa not installed  returning empty features")
        return _empty_features("no_librosa")
    except Exception as e:
        print(f"[VOICE] Acoustic extraction failed: {e}")
        return _empty_features("librosa_error")


# ============================================
# EMOTION CLASSIFICATION (wav2vec2)
# ============================================

_EMOTION_MAP = {
    "angry":     "anger",
    "calm":      "neutral",
    "disgust":   "disgust",
    "fearful":   "fear",
    "happy":     "joy",
    "neutral":   "neutral",
    "sad":       "sadness",
    "surprised": "surprise",
    "fear":      "fear",
    "anger":     "anger",
    "happiness": "joy",
    "sadness":   "sadness",
    "surprise":  "surprise",
}


def classify_voice_emotion(audio_path: str) -> dict:
    """
    Classify emotion from speech using wav2vec2
    (r-f/wav2vec-english-speech-emotion-recognition).

    Returns:
        {emotion, confidence, raw_label, all_scores}
    """
    clf = _get_voice_emotion_pipeline()

    if clf == "unavailable":
        print("[VOICE] wav2vec2 unavailable  returning neutral")
        return {"emotion": "neutral", "confidence": 0.0, "raw_label": "unavailable", "all_scores": {}}

    try:
        import librosa
        try:
            y, sr = librosa.load(audio_path, sr=16000, mono=True)
        except Exception:
            y, sr = librosa.load(audio_path, sr=None, mono=True)
            if sr != 16000:
                y = librosa.resample(y, orig_sr=sr, target_sr=16000)

        if len(y) == 0:
            return {"emotion": "neutral", "confidence": 0.0, "raw_label": "empty", "all_scores": {}}

        results = clf(y, top_k=5)
        if not results:
            return {"emotion": "neutral", "confidence": 0.0, "raw_label": "no_results", "all_scores": {}}

        top            = results[0]
        raw_label      = top["label"].lower()
        confidence     = float(top["score"])
        mapped_emotion = _EMOTION_MAP.get(raw_label, "neutral")

        all_scores = {
            _EMOTION_MAP.get(r["label"].lower(), r["label"].lower()): round(float(r["score"]), 4)
            for r in results
        }

        print(f"[VOICE] wav2vec2 emotion: {mapped_emotion} ({confidence:.2%}) [raw: {raw_label}]")
        return {
            "emotion":    mapped_emotion,
            "confidence": round(confidence, 4),
            "raw_label":  raw_label,
            "all_scores": all_scores,
        }

    except Exception as e:
        print(f"[VOICE] wav2vec2 classification error: {e}")
        return {"emotion": "neutral", "confidence": 0.0, "raw_label": f"error", "all_scores": {}}


# ============================================
# ASR / TRANSCRIPTION (Deepgram Nova-2 API)
# ============================================

def transcribe_audio(audio_path: str) -> str:
    """
    Transcribe audio using the Deepgram Nova-2 pre-recorded API.
    Sends the WAV file bytes directly  no ffmpeg or local model needed.

    Args:
        audio_path: Path to a 16kHz mono WAV file.

    Returns:
        Transcribed text string, or "" if failed.
    """
    api_key = os.getenv("DEEPGRAM_API_KEY", "")
    if not api_key:
        print("[VOICE] DEEPGRAM_API_KEY not set  transcription skipped")
        return ""

    if not os.path.exists(audio_path):
        print(f"[VOICE] Audio file not found for transcription: {audio_path}")
        return ""

    try:
        import httpx

        with open(audio_path, "rb") as f:
            audio_bytes = f.read()

        print("[VOICE] Sending audio to Deepgram Nova-2...")
        response = httpx.post(
            "https://api.deepgram.com/v1/listen",
            params={
                "model":        "nova-2",
                "language":     "en",
                "smart_format": "true",
                "punctuate":    "true",
            },
            headers={
                "Authorization": f"Token {api_key}",
                "Content-Type":  "audio/wav",
            },
            content=audio_bytes,
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()

        channels = data.get("results", {}).get("channels", [])
        if not channels:
            print("[VOICE] Deepgram returned no channels")
            return ""

        transcript = channels[0]["alternatives"][0].get("transcript", "").strip()

        if transcript:
            print(f"[VOICE] Deepgram transcription: \"{transcript}\"")
        else:
            print("[VOICE] Deepgram returned empty transcript")

        return transcript

    except Exception as e:
        print(f"[VOICE] Deepgram transcription failed: {e}")
        return ""



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

    - alpha controls text weight (default 0.6 = text slightly dominant)
    - If voice confidence < 0.3, rely on text alone
    - If text and voice agree, boost confidence
    - If they disagree, use the higher-confidence signal
    """
    text_emo   = text_emotion.get("emotion", "neutral")
    text_conf  = float(text_emotion.get("confidence", 0.5))
    voice_emo  = voice_emotion.get("emotion", "neutral")
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
          f"voice={voice_emo}({voice_conf:.2f})  {final_emotion} (source: {source})")

    return {
        "emotion": final_emotion, "confidence": round(final_conf, 3),
        "source": source, "conflict": True,
        "text_emotion": text_emo, "voice_emotion": voice_emo,
    }


# ============================================
# STARTUP MODEL PRELOAD
# ============================================

def preload_all_voice_models() -> dict:
    """
    Eagerly load voice ML models at server startup.

    Models loaded:
      - wav2vec2 (r-f/wav2vec-english-speech-emotion-recognition)

    Transcription is handled by Deepgram API  no local model needed.

    Returns a status dict for logging.
    """
    status = {}

    print("[VOICE-PRELOAD] Loading wav2vec2 emotion classifier...")
    try:
        clf = _get_voice_emotion_pipeline()
        status["wav2vec2"] = "ok" if clf != "unavailable" else "unavailable"
        print(f"[VOICE-PRELOAD] wav2vec2: {status['wav2vec2']}")
    except Exception as e:
        status["wav2vec2"] = f"error: {e}"
        print(f"[VOICE-PRELOAD] wav2vec2 failed: {e}")

    deepgram_key = os.getenv("DEEPGRAM_API_KEY", "")
    status["deepgram"] = "ok" if deepgram_key else "DEEPGRAM_API_KEY missing"
    print(f"[VOICE-PRELOAD] Deepgram: {status['deepgram']}")

    return status


# ============================================
# FULL VOICE ANALYSIS (unified convenience)
# ============================================

def analyze_voice_full(audio_path: str) -> dict:
    """
    Run full voice analysis in ONE pass:
      1. Acoustic feature extraction  (librosa)
      2. Emotion classification        (wav2vec2)
      3. ASR transcription             (Deepgram Nova-2 API)

    Returns:
        {
          acoustic_features : dict    feature dict with distress_index, etc.
          emotion           : str     mapped emotion label
          confidence        : float
          arousal           : float
          valence           : float
          distress_index    : float   psychoacoustic composite distress score
          pause_density     : float
          mfcc_vector       : list[float]   13-dim MFCC means
          all_scores        : dict
          extraction_method : str
          transcription     : str    ASR output (reuse, don't call separately)
        }
    """
    features      = extract_acoustic_features(audio_path)
    emotion_info  = classify_voice_emotion(audio_path)
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
        "extraction_method":  features.get("extraction_method", "librosa"),
        "transcription":      transcription,
    }
