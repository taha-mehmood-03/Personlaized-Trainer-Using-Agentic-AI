"""
Voice preprocessing and therapeutic voice feature extraction.

ARCHITECTURE:
1. Preprocessing only saves audio and gets a transcript through Gemini ASR.
   It does not analyze emotion, tone, acoustic cues, symptoms, or behaviors.
2. Rich voice features are extracted later only when the smart gate routes the
   turn to the therapeutic path.

ERROR HANDLING:
- Transcription failures fall back to the typed/browser message.
- Feature extraction failures fall back to text/gate-calibrated mood state.
- All intermediate failures are logged and do not crash the pipeline.
"""

import os
import tempfile
from typing import Any, Dict

from ..agent.state import MentalHealthState
from ..voice import analyze_voice_full_async, transcribe_voice_async


def _build_conversation_context(state: MentalHealthState) -> str:
    """
    Build a recent conversation context string from the last 6 messages in state.
    Mirrors the context window used by mood_analyzer_node so Gemini audio can
    correctly classify short or follow-up voice messages when feature extraction
    is allowed by the therapeutic route.
    """
    messages = state.get("messages", [])
    history_window = messages[-7:-1] if len(messages) > 1 else []
    lines = []
    for m in history_window:
        role = getattr(m, "type", "human")
        label = "User" if role == "human" else "Therapist"
        content = str(getattr(m, "content", "") or "")[:200]
        if content.strip():
            lines.append(f"{label}: {content}")
    return "\n".join(lines)


def _save_audio_to_temp_if_needed(state: MentalHealthState) -> str | None:
    audio_file_path = state.get("audio_file_path", "")
    audio_bytes = state.get("audio_bytes", None)

    if audio_bytes:
        suffix = ".wav"
        if isinstance(audio_bytes, (bytes, bytearray)) and audio_bytes[:4] == b"\x1a\x45\xdf\xa3":
            suffix = ".webm"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            return tmp.name

    return audio_file_path or None


async def preprocess_voice_input(state: MentalHealthState) -> dict:
    """
    Preprocess and extract ALL voice features in one pass.
    
    Gemini audio analysis performs both transcription and voice-feature
    extraction in this code path. The smart gate routes from the transcript;
    downstream nodes decide whether the extracted voice features should affect
    therapeutic emotion fusion.

    Output State:
        - voice_transcribed: bool, True if ASR returned text
        - voice_processed: bool, True if full Gemini audio feature extraction succeeded
        - voice_features: dict with emotion, distress, arousal, valence, etc. (or None if failed)
        - transcription: Gemini audio transcription
        - final_message: transcription or fallback message
        - temp_audio_path: path to saved temp file
    """
    print("\n[NODE: VOICE_PREPROCESSING]  Starting voice preprocessing")

    message = state.get("message", "")

    if not state.get("audio_file_path") and not state.get("audio_bytes"):
        print("[NODE: VOICE_PREPROCESSING]  No audio input  skipping")
        return {
            "voice_transcribed": False,
            "voice_processed": False,
            "voice_features": None,
            "transcription": "",
            "final_message": message,
        }

    temp_audio_path = None
    try:
        print("[NODE: VOICE_PREPROCESSING]  Step 1: Resolving audio file")
        temp_audio_path = _save_audio_to_temp_if_needed(state)

        if not temp_audio_path or not os.path.exists(temp_audio_path):
            print(f"[NODE: VOICE_PREPROCESSING]  Audio file not found: {temp_audio_path}")
            return {
                "voice_transcribed": False,
                "voice_processed": False,
                "voice_features": None,
                "transcription": "",
                "final_message": message,
                "temp_audio_path": None,
            }

        print("[NODE: VOICE_PREPROCESSING]  Step 2: Running Gemini audio analysis (transcription + features)")
        conversation_context = _build_conversation_context(state)
        full_result = await analyze_voice_full_async(
            temp_audio_path,
            conversation_context=conversation_context,
        )

        transcription = full_result.get("transcription", "")
        if transcription:
            print(f"[NODE: VOICE_PREPROCESSING]  Transcription: '{transcription[:100]}'")
        else:
            print("[NODE: VOICE_PREPROCESSING]  Transcription empty  using message fallback")

        # Extract voice features regardless of extraction method
        # If Gemini audio analysis succeeded, use it; otherwise fallback to defaults
        if full_result.get("extraction_method") == "gemini_audio":
            voice_features = _voice_features_from_full_result(full_result)
            voice_processed = True
            print(
                f"[NODE: VOICE_PREPROCESSING]  Voice features extracted: emotion={voice_features['emotion']} "
                f"(conf={voice_features['confidence']:.2f}) | distress={voice_features['distress_index']:.2f} | "
                f"arousal={voice_features['arousal']:.2f} | valence={voice_features['valence']:.2f}"
            )
        else:
            print("[NODE: VOICE_PREPROCESSING]  Audio analysis fallback  using default voice features")
            voice_features = _get_default_voice_features()
            voice_processed = False

        final_message = transcription if transcription else message

        return {
            "voice_transcribed": bool(transcription),
            "voice_processed": voice_processed,
            "voice_features": voice_features,
            "transcription_confidence": float(voice_features.get("confidence", 0.0)) if transcription else 0.0,
            "voice_distress_index": float(voice_features.get("distress_index", 0.0)),
            "voice_pause_density": float(voice_features.get("pause_density", 0.25)),
            "voice_mfcc_vector": voice_features.get("mfcc_vector", [0.0] * 13),
            "transcription": transcription,
            "final_message": final_message,
            "temp_audio_path": temp_audio_path,
            "message": final_message,
            "has_voice": True,
        }

    except Exception as e:
        print(f"[NODE: VOICE_PREPROCESSING]  Error: {str(e)}")
        import traceback

        traceback.print_exc()
        return {
            "voice_transcribed": False,
            "voice_processed": False,
            "voice_features": _get_default_voice_features(),
            "transcription": "",
            "final_message": message,
            "temp_audio_path": temp_audio_path,
        }


def _voice_features_from_full_result(full_result: dict[str, Any]) -> Dict[str, Any]:
    acoustic = full_result.get("acoustic_features", {})
    return {
        "emotion": full_result.get("emotion", "neutral"),
        "primary_sub_emotion": full_result.get("primary_sub_emotion"),
        "secondary_sub_emotions": full_result.get("secondary_sub_emotions", []),
        "detected_symptoms": full_result.get("detected_symptoms", []),
        "detected_behaviors": full_result.get("detected_behaviors", []),
        "detected_contexts": full_result.get("detected_contexts", []),
        "sentiment": full_result.get("sentiment", "neutral"),
        "intensity": float(full_result.get("intensity", full_result.get("arousal", 0.5))),
        "confidence": float(full_result.get("confidence", 0.0)),
        "arousal": float(full_result.get("arousal", 0.5)),
        "valence": float(full_result.get("valence", 0.5)),
        "distress_index": float(full_result.get("distress_index", 0.0)),
        "pause_density": float(full_result.get("pause_density", 0.25)),
        "mfcc_vector": full_result.get("mfcc_vector", [0.0] * 13),
        "acoustic_features": acoustic,
        # Real (librosa + parselmouth) DSP cross-check, separate from Gemini's
        # own holistic distress_index judgment above. See
        # voice/acoustic_features.py for what this measures and why it is
        # kept distinct rather than overwriting distress_index.
        "acoustic_distress_proxy": full_result.get("acoustic_distress_proxy"),
        "dsp_extraction_method": full_result.get("dsp_extraction_method", "dsp_failed"),
        "all_scores": full_result.get("all_scores", {}),
        "emotion_scores": full_result.get("emotion_scores", full_result.get("all_scores", {})),
        "emotion_reasoning": full_result.get("emotion_reasoning"),
        "extraction_method": full_result.get("extraction_method", "gemini_audio"),
    }



def _get_default_voice_features() -> Dict[str, Any]:
    """Return neutral default voice features when extraction fails."""
    return {
        "emotion": "neutral",
        "confidence": 0.0,
        "arousal": 0.5,
        "valence": 0.5,
        "distress_index": 0.0,
        "pause_density": 0.25,
        "mfcc_vector": [0.0] * 13,
        "acoustic_features": {
            "pitch_mean": 0,
            "pitch_std": 0,
            "loudness_mean": 0,
            "jitter": 0,
            "shimmer": 0,
        },
        "all_scores": {},
        "emotion_scores": {},
        "primary_sub_emotion": "neutral",
        "secondary_sub_emotions": [],
        "detected_symptoms": [],
        "detected_behaviors": [],
        "detected_contexts": [],
        "sentiment": "neutral",
        "intensity": 0.5,
        "emotion_reasoning": "",
        "extraction_method": "fallback",
    }
