"""
Voice Emotion Detection Module
Combines OpenSMILE eGeMAPS for interpretable acoustic features
with wav2vec2 for speech emotion classification.

Privacy: Only extracted features are stored — raw audio is NEVER persisted.
"""

import os
import numpy as np
from typing import Optional

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
            # Handle missing optional dependencies (kenlm, pyctcdecode) gracefully
            if "kenlm" in str(e) or "pyctcdecode" in str(e):
                print(f"[VOICE] ⚠️ Optional dependency missing for full decoder features: {e}")
                print("[VOICE] 💡 Tip: Install 'pyctcdecode' and 'kenlm' for better performance if possible.")
                # We can still proceed if the pipeline object was created but warned, 
                # but if initialization failed completely, we mark unavailable.
                # However, usually the pipeline call fails if dependencies are strict.
                # If we are here, it failed.
                pass 
            
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
# FEATURE EXTRACTION (OpenSMILE eGeMAPS)
# ============================================

def extract_acoustic_features(audio_path: str) -> dict:
    """
    Extract interpretable acoustic features from audio using eGeMAPS.
    
    Features extracted:
    - pitch_mean, pitch_std: Fundamental frequency (F0) statistics
    - loudness_mean: Perceived loudness
    - speech_rate: Estimated syllables per second
    - jitter: Voice quality — pitch perturbation
    - shimmer: Voice quality — amplitude perturbation
    - hnr: Harmonics-to-noise ratio
    - mfcc_1_mean: First MFCC coefficient (spectral shape)
    
    Args:
        audio_path: Path to audio file (WAV, MP3, WebM)
        
    Returns:
        Dictionary of interpretable acoustic features
    """
    extractor = _get_opensmile_extractor()
    
    if extractor != "fallback" and extractor is not None:
        return _extract_with_opensmile(extractor, audio_path)
    else:
        return _extract_with_librosa(audio_path)


def _extract_with_opensmile(extractor, audio_path: str) -> dict:
    """Extract features using OpenSMILE eGeMAPS"""
    try:
        features = extractor.process_file(audio_path)
        
        # Extract key interpretable features from eGeMAPS
        row = features.iloc[0]
        
        result = {
            "pitch_mean": float(row.get("F0semitoneFrom27.5Hz_sma3nz_amean", 0)),
            "pitch_std": float(row.get("F0semitoneFrom27.5Hz_sma3nz_stddevNorm", 0)),
            "loudness_mean": float(row.get("loudness_sma3_amean", 0)),
            "loudness_std": float(row.get("loudness_sma3_stddevNorm", 0)),
            "jitter": float(row.get("jitterLocal_sma3nz_amean", 0)),
            "shimmer": float(row.get("shimmerLocaldB_sma3nz_amean", 0)),
            "hnr": float(row.get("HNRdBACF_sma3nz_amean", 0)),
            "speech_rate": float(row.get("StddevUnvoicedSegmentLength", 0)),
            "mfcc_1_mean": float(row.get("mfcc1_sma3_amean", 0)),
            "spectral_flux": float(row.get("spectralFlux_sma3_amean", 0)),
            "extraction_method": "opensmile_egemaps"
        }
        
        # Derive arousal and valence from acoustic features
        # High pitch + high loudness + high speech rate → high arousal
        result["arousal"] = _estimate_arousal(result)
        result["valence"] = _estimate_valence(result)
        
        print(f"[VOICE] eGeMAPS features extracted: pitch={result['pitch_mean']:.1f}, "
              f"loudness={result['loudness_mean']:.2f}, arousal={result['arousal']:.2f}")
        return result
        
    except Exception as e:
        print(f"[VOICE] OpenSMILE extraction failed: {e}, falling back to librosa")
        return _extract_with_librosa(audio_path)


def _extract_with_librosa(audio_path: str) -> dict:
    """Fallback feature extraction using librosa"""
    try:
        import librosa
        
        # Load audio with detailed error handling
        try:
            y, sr = librosa.load(audio_path, sr=16000, mono=True)
            print(f"[VOICE] 📊 Loaded audio: {len(y)} samples at {sr}Hz")
        except Exception as load_error:
            print(f"[VOICE] ⚠️ librosa.load failed: {load_error}")
            print(f"[VOICE] Trying with sr=None to detect native sample rate...")
            try:
                y, sr = librosa.load(audio_path, sr=None, mono=True)
                # Resample to 16kHz
                if sr != 16000:
                    y = librosa.resample(y, orig_sr=sr, target_sr=16000)
                    sr = 16000
                print(f"[VOICE] ✅ Loaded with native detection: {len(y)} samples at {sr}Hz")
            except Exception as e2:
                print(f"[VOICE] ❌ Both methods failed: {e2}")
                return _empty_features(f"librosa_failed_{str(e2)[:50]}")
        
        if len(y) == 0:
            print("[VOICE] ⚠️ Audio array is empty after loading")
            return _empty_features("librosa_empty")
        
        # F0 (pitch)
        f0, voiced_flag, voiced_probs = librosa.pyin(
            y, fmin=librosa.note_to_hz('C2'),
            fmax=librosa.note_to_hz('C7'), sr=sr
        )
        f0_valid = f0[~np.isnan(f0)] if f0 is not None else np.array([0])
        
        # Loudness (RMS energy)
        rms = librosa.feature.rms(y=y)[0]
        
        # MFCCs
        mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        
        # Spectral features
        spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        
        result = {
            "pitch_mean": float(np.mean(f0_valid)) if len(f0_valid) > 0 else 0.0,
            "pitch_std": float(np.std(f0_valid)) if len(f0_valid) > 0 else 0.0,
            "loudness_mean": float(np.mean(rms)),
            "loudness_std": float(np.std(rms)),
            "jitter": float(np.mean(np.abs(np.diff(f0_valid)))) if len(f0_valid) > 1 else 0.0,
            "shimmer": float(np.mean(np.abs(np.diff(rms)))) if len(rms) > 1 else 0.0,
            "hnr": 0.0,  # HNR not easily computed via librosa
            "speech_rate": float(np.sum(voiced_flag) / (len(y) / sr)) if voiced_flag is not None else 0.0,
            "mfcc_1_mean": float(np.mean(mfccs[1])) if mfccs.shape[0] > 1 else 0.0,
            "spectral_flux": float(np.mean(np.abs(np.diff(spectral_centroid)))),
            "extraction_method": "librosa_fallback"
        }
        
        result["arousal"] = _estimate_arousal(result)
        result["valence"] = _estimate_valence(result)
        
        print(f"[VOICE] librosa features extracted: pitch={result['pitch_mean']:.1f}, "
              f"loudness={result['loudness_mean']:.4f}")
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
        "pitch_mean": 0.0, "pitch_std": 0.0,
        "loudness_mean": 0.0, "loudness_std": 0.0,
        "jitter": 0.0, "shimmer": 0.0, "hnr": 0.0,
        "speech_rate": 0.0, "mfcc_1_mean": 0.0,
        "spectral_flux": 0.0,
        "arousal": 0.5, "valence": 0.5,
        "extraction_method": method
    }


def _estimate_arousal(features: dict) -> float:
    """
    Estimate arousal (activation level) from acoustic features.
    High arousal: high pitch, high loudness, fast speech, high spectral flux
    Low arousal: low pitch, low loudness, slow speech
    
    Returns value between 0 (very calm) and 1 (very activated)
    """
    # Normalize features to 0-1 range using typical speech ranges
    pitch_norm = min(max((features.get("pitch_mean", 0) - 100) / 200, 0), 1)
    loudness_norm = min(max(features.get("loudness_mean", 0) / 0.5, 0), 1)
    rate_norm = min(max(features.get("speech_rate", 0) / 6, 0), 1)
    flux_norm = min(max(features.get("spectral_flux", 0) / 100, 0), 1)
    
    # Weighted combination
    arousal = 0.35 * pitch_norm + 0.30 * loudness_norm + 0.20 * rate_norm + 0.15 * flux_norm
    return round(min(max(arousal, 0), 1), 3)


def _estimate_valence(features: dict) -> float:
    """
    Estimate valence (positive/negative) from acoustic features.
    Positive valence: higher pitch, more harmonic, wider pitch range
    Negative valence: lower pitch, breathier, narrower range
    
    Returns value between 0 (very negative) and 1 (very positive)
    """
    pitch_norm = min(max((features.get("pitch_mean", 0) - 100) / 200, 0), 1)
    hnr_norm = min(max(features.get("hnr", 0) / 20, 0), 1)
    pitch_var = min(max(features.get("pitch_std", 0) / 50, 0), 1)
    
    # Weighted combination (valence is harder to determine from acoustics alone)
    valence = 0.40 * pitch_norm + 0.35 * hnr_norm + 0.25 * pitch_var
    return round(min(max(valence, 0), 1), 3)


# ============================================
# EMOTION CLASSIFICATION (wav2vec2)
# ============================================

# Map model's emotion labels to our standard set
_EMOTION_MAP = {
    "angry": "anger",
    "calm": "neutral",
    "disgust": "disgust",
    "fearful": "fear",
    "happy": "joy",
    "neutral": "neutral",
    "sad": "sadness",
    "surprised": "surprise",
    # Additional mappings for robustness
    "fear": "fear",
    "anger": "anger",
    "happiness": "joy",
    "sadness": "sadness",
    "surprise": "surprise",
}


def classify_voice_emotion(audio_path: str) -> dict:
    """
    Classify emotion from speech using wav2vec2.
    
    Uses the r-f/wav2vec-english-speech-emotion-recognition model,
    trained on SAVEE + RAVDESS + TESS (97.5% accuracy on eval set).
    
    Args:
        audio_path: Path to audio file
        
    Returns:
        Dictionary with:
        - emotion: Mapped emotion label (anger, joy, sadness, etc.)
        - confidence: Model confidence (0-1)
        - raw_label: Original model label
        - all_scores: All emotion scores
    """
    pipeline_cls = _get_voice_emotion_pipeline()
    
    if pipeline_cls == "unavailable":
        print("[VOICE] wav2vec2 unavailable — returning neutral")
        return {
            "emotion": "neutral",
            "confidence": 0.0,
            "raw_label": "unavailable",
            "all_scores": {}
        }
    
    try:
        import librosa
        # Load audio at 16kHz (model requirement)
        try:
            y, sr = librosa.load(audio_path, sr=16000, mono=True)
            print(f"[VOICE] 🎵 Loaded for classification: {len(y)} samples at {sr}Hz")
        except Exception as load_error:
            print(f"[VOICE] ⚠️ First load attempt failed: {load_error}")
            print(f"[VOICE] Retrying with native sample rate detection...")
            try:
                y, sr = librosa.load(audio_path, sr=None, mono=True)
                if sr != 16000:
                    y = librosa.resample(y, orig_sr=sr, target_sr=16000)
                    sr = 16000
                print(f"[VOICE] ✅ Loaded with native detection: {len(y)} samples")
            except Exception as e2:
                print(f"[VOICE] ❌ Classification load failed: {e2}")
                return {"emotion": "neutral", "confidence": 0.0, "raw_label": "load_error", "all_scores": {}}
        
        if len(y) == 0:
            print("[VOICE] ⚠️ Audio array is empty")
            return {"emotion": "neutral", "confidence": 0.0, "raw_label": "empty", "all_scores": {}}
        
        # Classify
        results = pipeline_cls(y, top_k=5)
        
        if not results:
            return {"emotion": "neutral", "confidence": 0.0, "raw_label": "no_results", "all_scores": {}}
        
        # Get top prediction
        top = results[0]
        raw_label = top["label"].lower()
        confidence = float(top["score"])
        
        # Map to our emotion set
        mapped_emotion = _EMOTION_MAP.get(raw_label, "neutral")
        
        # Build all scores dict
        all_scores = {}
        for r in results:
            label = _EMOTION_MAP.get(r["label"].lower(), r["label"].lower())
            all_scores[label] = round(float(r["score"]), 4)
        
        print(f"[VOICE] wav2vec2 emotion: {mapped_emotion} ({confidence:.2%}) [raw: {raw_label}]")
        
        return {
            "emotion": mapped_emotion,
            "confidence": round(confidence, 4),
            "raw_label": raw_label,
            "all_scores": all_scores
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
    - If voice confidence is very low (<0.3), rely on text alone
    - If text and voice agree, boost confidence
    - If they disagree, use the higher-confidence signal but flag conflict
    
    Args:
        text_emotion: {"emotion": str, "confidence": float}
        voice_emotion: {"emotion": str, "confidence": float}
        alpha: Weight for text signal (0-1). 1.0 = text only, 0.0 = voice only
        
    Returns:
        Dictionary with:
        - emotion: Final fused emotion
        - confidence: Combined confidence
        - source: Which signal dominated ("text", "voice", "agreement")
        - conflict: Boolean indicating disagreement
    """
    text_emo = text_emotion.get("emotion", "neutral")
    text_conf = float(text_emotion.get("confidence", 0.5))
    voice_emo = voice_emotion.get("emotion", "neutral")
    voice_conf = float(voice_emotion.get("confidence", 0.0))
    
    # If voice confidence is too low, just use text
    if voice_conf < 0.3:
        return {
            "emotion": text_emo,
            "confidence": text_conf,
            "source": "text",
            "conflict": False,
            "text_emotion": text_emo,
            "voice_emotion": voice_emo
        }
    
    # If both agree, boost confidence
    if text_emo == voice_emo:
        combined_conf = min(0.95, text_conf * 0.7 + voice_conf * 0.3 + 0.1)
        return {
            "emotion": text_emo,
            "confidence": round(combined_conf, 3),
            "source": "agreement",
            "conflict": False,
            "text_emotion": text_emo,
            "voice_emotion": voice_emo
        }
    
    # Disagreement: use confidence-weighted selection
    text_weighted = text_conf * alpha
    voice_weighted = voice_conf * (1 - alpha)
    
    if text_weighted >= voice_weighted:
        final_emotion = text_emo
        final_conf = text_conf * 0.8  # Reduce confidence due to conflict
        source = "text"
    else:
        final_emotion = voice_emo
        final_conf = voice_conf * 0.8
        source = "voice"
    
    print(f"[VOICE] Fusion conflict: text={text_emo}({text_conf:.2f}) vs voice={voice_emo}({voice_conf:.2f}) → {final_emotion} (source: {source})")
    
    return {
        "emotion": final_emotion,
        "confidence": round(final_conf, 3),
        "source": source,
        "conflict": True,
        "text_emotion": text_emo,
        "voice_emotion": voice_emo
    }


# ============================================
# ASR / TRANSCRIPTION
# ============================================

def transcribe_audio(audio_path: str) -> str:
    """
    Transcribe audio to text using ASR.
    Loads audio with scipy/librosa to avoid ffmpeg dependency in transformers.
    
    Args:
        audio_path: Path to audio file
        
    Returns:
        Transcribed text string or empty string if failed
    """
    asr = _get_asr_pipeline()
    
    if asr == "unavailable":
        return ""
        
    try:
        # Check if file exists
        if not os.path.exists(audio_path):
            print(f"[VOICE] ⚠️ Audio file not found for transcription: {audio_path}")
            return ""
            
        # Load audio into numpy array using scipy (preferred for WAV) or librosa
        # This bypasses the need for ffmpeg in the pipeline
        import numpy as np
        speech = None
        
        # 1. Try scipy.io.wavfile (fastest, no deps)
        try:
            import scipy.io.wavfile as wavfile
            from scipy import signal
            
            # Suppress scipy warnings if possible
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                sr, data = wavfile.read(audio_path)
            
            # Convert to float32 normalized to [-1, 1] if int
            if data.dtype == np.int16:
                data = data.astype(np.float32) / 32768.0
            elif data.dtype == np.int32:
                data = data.astype(np.float32) / 2147483648.0
            elif data.dtype == np.uint8:
                data = (data.astype(np.float32) - 128.0) / 128.0
                
            # If stereo, convert to mono
            if len(data.shape) > 1:
                data = data.mean(axis=1)
                
            # Resample to 16k if needed (Whisper expects 16k)
            if sr != 16000:
                samples = int(len(data) * 16000 / sr)
                # usage of signal.resample might be slow for large files, but for voice msgs ok
                data = signal.resample(data, samples)
                
            speech = data
            # print("[VOICE] ✅ Audio loaded for ASR using scipy")
            
        except Exception as e_scipy:
            print(f"[VOICE] ⚠️ scipy load failed: {e_scipy}")
            speech = None

        # 2. Fallback to librosa if scipy failed (e.g. not a WAV)
        if speech is None:
            try:
                import librosa
                speech, _ = librosa.load(audio_path, sr=16000, mono=True)
                print("[VOICE] ✅ Audio loaded for ASR using librosa")
            except Exception as e_librosa:
                print(f"[VOICE] ❌ Audio loading failed (scipy & librosa): {e_librosa}")
                return ""
        
        # Pass numpy array to pipeline
        # explicit sampling_rate is safer
        result = asr(speech)
        text = result.get("text", "").strip()
        
        if text:
            print(f"[VOICE] 📝 Transcription: \"{text}\"")
        else:
            print("[VOICE] ⚠️ Transcription resulted in empty text")
            
        return text
        
    except Exception as e:
        print(f"[VOICE] ❌ Transcription failed: {e}")
        return ""


# ============================================
# FULL VOICE ANALYSIS (convenience function)
# ============================================

def analyze_voice_full(audio_path: str) -> dict:
    """
    Run full voice analysis pipeline: feature extraction + emotion classification + ASR.
    
    Args:
        audio_path: Path to audio file
        
    Returns:
        Combined dict of acoustic features, emotion classification, and transcription
    """
    features = extract_acoustic_features(audio_path)
    emotion = classify_voice_emotion(audio_path)
    transcription = transcribe_audio(audio_path)
    
    return {
        "acoustic_features": features,
        "emotion": emotion.get("emotion", "neutral"),
        "confidence": emotion.get("confidence", 0.0),
        "arousal": features.get("arousal", 0.5),
        "valence": features.get("valence", 0.5),
        "all_scores": emotion.get("all_scores", {}),
        "extraction_method": features.get("extraction_method", "unknown"),
        "transcription": transcription
    }
