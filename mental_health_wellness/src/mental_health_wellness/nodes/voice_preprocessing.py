"""
Voice Pre-Processing Node - Sequential audio processing

ARCHITECTURE NODE 0:
Purpose: Convert voice input to text and features
Runs BEFORE the main pipeline if audio is present

SEQUENTIAL STEPS:
1. Save Audio to Temp File - Receive blob, write to disk
2. Speech-to-Text (Transcription) - REUSED from analyze_voice_full (zero double-ASR overhead)
3. Extract Voice Features - OpenSMILE/Wav2Vec2/torchaudio → emotion + acoustics

NEW IN THIS VERSION:
- Uses the transcription from analyze_voice_full() — no second Whisper call
- Passes distress_index, pause_density, mfcc_vector into state
- Writes voice_distress_index and voice_pause_density to state for emotion_fusion_node

ERROR HANDLING:
- If STT fails: Uses empty string + original message as fallback
- If feature extraction fails: Returns neutral default features
- All intermediate failures are logged, never crash the pipeline
"""

import tempfile
import os
from typing import Optional, Dict, Any

from ..agent.state import MentalHealthState
from ..voice import analyze_voice_full


async def preprocess_voice_input(state: MentalHealthState) -> dict:
    """
    Process voice input through sequential steps:
    1. Save audio blob to temporary file (if raw bytes provided)
    2. Run full voice analysis in ONE call (acoustics + emotion + ASR)
    3. Return all voice features including new psychoacoustic signals

    Input State:
        - audio_file_path: Path to the audio file
        - audio_bytes: Raw audio bytes (FormData upload)
        - message: Optional text message from user (fallback if STT fails)

    Output State:
        - voice_features:        Dict with emotion, confidence, arousal, valence,
                                 distress_index, pause_density, mfcc_vector, acoustic_features
        - voice_distress_index:  float  psychoacoustic composite stress score
        - voice_pause_density:   float  silence / hesitancy proportion
        - voice_mfcc_vector:     list   13-dim MFCC mean vector
        - transcription:         str    Whisper ASR output (reused from analyze_voice_full)
        - final_message:         str    Transcription or fallback message
        - voice_processed:       bool   True if voice was successfully analyzed
        - temp_audio_path:       str    Path to saved temp file (for cleanup later)
    """
    print(f"\n[NODE: VOICE_PREPROCESSING] 🎤 Starting voice processing")

    audio_file_path = state.get("audio_file_path", "")
    audio_bytes     = state.get("audio_bytes", None)
    message         = state.get("message", "")

    if not audio_file_path and not audio_bytes:
        print("[NODE: VOICE_PREPROCESSING] ⚠️ No audio input — skipping voice processing")
        return {
            "voice_processed": False,
            "voice_features":  None,
            "transcription":   "",
            "final_message":   message,
        }

    temp_audio_path = None
    try:
        # ============================================
        # STEP 1: SAVE AUDIO TO TEMP FILE
        # ============================================
        print("[NODE: VOICE_PREPROCESSING] 💾 Step 1: Saving audio to temp file")

        if audio_bytes:
            suffix = ".wav"
            # Detect WebM magic bytes
            if isinstance(audio_bytes, (bytes, bytearray)) and audio_bytes[:4] == b'\x1a\x45\xdf\xa3':
                suffix = ".webm"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(audio_bytes)
                temp_audio_path = tmp.name
            print(f"[NODE: VOICE_PREPROCESSING] ✅ Saved audio bytes: {temp_audio_path}")
        else:
            temp_audio_path = audio_file_path
            print(f"[NODE: VOICE_PREPROCESSING] ✅ Using provided audio file: {temp_audio_path}")

        if not os.path.exists(temp_audio_path):
            print(f"[NODE: VOICE_PREPROCESSING] ⚠️ Audio file not found: {temp_audio_path}")
            return {
                "voice_processed": False,
                "voice_features":  None,
                "transcription":   "",
                "final_message":   message,
                "temp_audio_path": None,
            }

        # ============================================
        # STEP 2 + 3: FULL VOICE ANALYSIS (one pass)
        # analyze_voice_full() runs:
        #   a) Acoustic feature extraction (OpenSMILE → torchaudio → librosa)
        #   b) Emotion classification (wav2vec2)
        #   c) ASR transcription (Whisper-tiny)
        # We reuse the transcription — NO second ASR call needed.
        # ============================================
        print("[NODE: VOICE_PREPROCESSING] 🔊 Step 2+3: Running full voice analysis (one pass)")

        full_result = analyze_voice_full(temp_audio_path)

        # ── Extract transcription (from shared ASR call) ──
        transcription = full_result.get("transcription", "")
        if transcription:
            print(f"[NODE: VOICE_PREPROCESSING] ✅ Transcription: '{transcription[:100]}'")
        else:
            print("[NODE: VOICE_PREPROCESSING] ⚠️ Transcription returned empty — using original message as fallback")

        # ── Build voice_features dict (what emotion_fusion_node expects) ──
        acoustic = full_result.get("acoustic_features", {})
        voice_features = {
            "emotion":           full_result.get("emotion", "neutral"),
            "confidence":        float(full_result.get("confidence", 0.0)),
            "arousal":           float(full_result.get("arousal", 0.5)),
            "valence":           float(full_result.get("valence", 0.5)),
            "distress_index":    float(full_result.get("distress_index", 0.0)),
            "pause_density":     float(full_result.get("pause_density", 0.25)),
            "mfcc_vector":       full_result.get("mfcc_vector", [0.0] * 13),
            "acoustic_features": acoustic,
            "all_scores":        full_result.get("all_scores", {}),
            "extraction_method": full_result.get("extraction_method", "unknown"),
        }

        distress_index = voice_features["distress_index"]
        pause_density  = voice_features["pause_density"]
        print(
            f"[NODE: VOICE_PREPROCESSING] ✅ Voice emotion: {voice_features['emotion']} "
            f"(conf={voice_features['confidence']:.2f}) | "
            f"distress_index={distress_index:.2f} | "
            f"pause_density={pause_density:.2f}"
        )

        # Use transcription as the main message if available
        final_message = transcription if transcription else message

        return {
            "voice_processed":       True,
            "voice_features":        voice_features,
            "voice_distress_index":  distress_index,
            "voice_pause_density":   pause_density,
            "voice_mfcc_vector":     voice_features["mfcc_vector"],
            "transcription":         transcription,
            "final_message":         final_message,
            "temp_audio_path":       temp_audio_path,
            "message":               final_message,   # Override message with transcription
            "has_voice":             True,
        }

    except Exception as e:
        print(f"[NODE: VOICE_PREPROCESSING] ❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()

        return {
            "voice_processed":   False,
            "voice_features":    None,
            "transcription":     "",
            "final_message":     message,
            "temp_audio_path":   temp_audio_path,
        }


def _get_default_voice_features() -> Dict[str, Any]:
    """Return neutral default voice features when extraction fails."""
    return {
        "emotion":        "neutral",
        "confidence":     0.0,
        "arousal":        0.5,
        "valence":        0.5,
        "distress_index": 0.0,
        "pause_density":  0.25,
        "mfcc_vector":    [0.0] * 13,
        "acoustic_features": {
            "pitch_mean": 0, "pitch_std": 0,
            "loudness_mean": 0, "jitter": 0, "shimmer": 0,
        },
        "all_scores":        {},
        "extraction_method": "fallback",
    }
