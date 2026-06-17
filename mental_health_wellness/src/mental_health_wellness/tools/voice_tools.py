"""
LangChain tool wrapper for Gemini voice emotion analysis.

Gemini provides transcript, core emotion, sub-emotions, sentiment, confidence,
and a holistic distress/arousal/valence judgment from listening to the audio.
`acoustic_features` and `mfcc_vector` are real measurements computed by
voice/acoustic_features.py (librosa + parselmouth/Praat) -- an LLM cannot
measure jitter, shimmer, HNR, or MFCCs, only estimate higher-level impressions,
so those numbers are never asked of Gemini.
"""
from langchain_core.tools import tool


@tool
def analyze_voice(audio_path: str) -> dict:
    """
    Analyze voice/speech audio with Gemini for emotional signals and distress.

    Gemini uses both the transcript and a holistic listen for tone, pace,
    pauses, energy, strain, and hesitation. `acoustic_features` and
    `mfcc_vector` are real DSP measurements (librosa + parselmouth), not
    Gemini estimates -- see voice/acoustic_features.py.

    Args:
        audio_path: Absolute path to the audio file (WAV, WebM, MP3).
                    MUST be a real file path  not a placeholder string.

    Returns:
        Dictionary with:
        {
            "emotion":        str     mapped emotion label (anger, sadness, joy ...)
            "confidence":     float   model confidence 0-1
            "arousal":        float   activation level 0-1
            "valence":        float   positivity/negativity 0-1
            "distress_index": float   composite psychoacoustic distress 0-1
            "pause_density":  float   silent frame proportion 0-1
            "mfcc_vector":    list    compatibility vector
            "acoustic_features": dict  compatibility acoustic fields
            "all_scores":     dict    all emotion label scores
            "primary_sub_emotion": str nuanced emotion label
            "secondary_sub_emotions": list extra nuanced labels
            "detected_symptoms": list physical/cognitive signals
            "detected_behaviors": list behavioral patterns
            "detected_contexts": list situational contexts
            "sentiment":      str     positive | negative | neutral
            "intensity":      float   emotion intensity 0-1
            "transcription":  str     Gemini audio transcription
            "extraction_method": str  gemini_audio
        }

    CRITICAL: Must receive an actual file path, not a placeholder!
    """
    #  Default error response 
    default_response = {
        "emotion":        "neutral",
        "confidence":     0.0,
        "arousal":        0.5,
        "valence":        0.5,
        "distress_index": 0.0,
        "pause_density":  0.25,
        "mfcc_vector":    [0.0] * 13,
        "acoustic_features": {
            "pitch_mean": 0, "pitch_std": 0,
            "loudness_mean": 0, "jitter": 0, "shimmer": 0, "hnr": 0,
        },
        "all_scores":        {},
        "emotion_scores":     {},
        "primary_sub_emotion": "neutral",
        "secondary_sub_emotions": [],
        "detected_symptoms":  [],
        "detected_behaviors": [],
        "detected_contexts":  [],
        "sentiment":         "neutral",
        "intensity":         0.5,
        "emotion_reasoning": "",
        "extraction_method": "error",
        "transcription":     "",
        "error":             "Invalid audio path",
    }

    #  Validate audio_path 
    if not audio_path:
        print("[VOICE_TOOL]  ERROR: No audio path provided!")
        return default_response

    # Reject placeholder strings injected by prompt mis-formatting
    _PLACEHOLDERS = [
        "/path/to/your/voice/message.wav",
        "path_to_your_audio_file.wav",
        "path_to_audio",
        "audio_path",
        "(voice message)",
        "your_voice_message",
    ]
    if any(p in audio_path.lower() for p in _PLACEHOLDERS):
        print(f"[VOICE_TOOL]  ERROR: Placeholder string received: {audio_path}")
        return {**default_response, "error": "Placeholder string  check system prompt"}

    #  File existence / size check 
    import os
    if not os.path.exists(audio_path):
        print(f"[VOICE_TOOL]  ERROR: Audio file not found: {audio_path}")
        return {**default_response, "error": f"File not found: {audio_path}"}

    try:
        file_size = os.path.getsize(audio_path)
        if file_size < 1000:
            print(f"[VOICE_TOOL]  WARNING: Audio file very small ({file_size} bytes)  may be corrupt")
    except Exception as e:
        print(f"[VOICE_TOOL]  ERROR: Could not check file: {e}")
        return {**default_response, "error": f"Cannot read file: {str(e)}"}

    #  Run full voice analysis 
    try:
        print(f"[VOICE_TOOL]  Analyzing audio: {audio_path}")

        from ..voice import analyze_voice_full

        result = analyze_voice_full(audio_path)

        if not result:
            print("[VOICE_TOOL]  analyze_voice_full returned None")
            return default_response

        acoustic = result.get("acoustic_features", {})

        formatted_result = {
            "emotion":        result.get("emotion", "neutral"),
            "confidence":     float(result.get("confidence", 0.0)),
            "arousal":        float(result.get("arousal", 0.5)),
            "valence":        float(result.get("valence", 0.5)),
            #  New psychoacoustic fields 
            "distress_index": float(result.get("distress_index", 0.0)),
            "pause_density":  float(result.get("pause_density", 0.25)),
            "mfcc_vector":    result.get("mfcc_vector", [0.0] * 13),
            #  Raw acoustic features 
            "acoustic_features": {
                "pitch_mean":    float(acoustic.get("pitch_mean", 0)),
                "pitch_std":     float(acoustic.get("pitch_std", 0)),
                "loudness_mean": float(acoustic.get("loudness_mean", 0)),
                "jitter":        float(acoustic.get("jitter", 0)),
                "shimmer":       float(acoustic.get("shimmer", 0)),
                "hnr":           float(acoustic.get("hnr", 0)),
                "speech_rate":   float(acoustic.get("speech_rate", 0)),
                "spectral_flux": float(acoustic.get("spectral_flux", 0)),
            },
            # Real (librosa + parselmouth) DSP cross-check -- see
            # voice/acoustic_features.py for what this measures.
            "acoustic_distress_proxy": result.get("acoustic_distress_proxy"),
            "dsp_extraction_method": result.get("dsp_extraction_method", "dsp_failed"),
            "all_scores":        result.get("all_scores", {}),
            "emotion_scores":     result.get("emotion_scores", result.get("all_scores", {})),
            "primary_sub_emotion": result.get("primary_sub_emotion", "neutral"),
            "secondary_sub_emotions": result.get("secondary_sub_emotions", []),
            "detected_symptoms":  result.get("detected_symptoms", []),
            "detected_behaviors": result.get("detected_behaviors", []),
            "detected_contexts":  result.get("detected_contexts", []),
            "sentiment":         result.get("sentiment", "neutral"),
            "intensity":         float(result.get("intensity", 0.5)),
            "emotion_reasoning": result.get("emotion_reasoning", ""),
            "extraction_method": result.get("extraction_method", "gemini_audio"),
            "transcription":     result.get("transcription", ""),
        }

        distress = formatted_result["distress_index"]
        pause    = formatted_result["pause_density"]
        print(
            f"[VOICE_TOOL]  Analysis complete: "
            f"emotion={formatted_result['emotion']}, "
            f"confidence={formatted_result['confidence']:.2f}, "
            f"distress_index={distress:.2f}, "
            f"pause_density={pause:.2f}"
        )
        if distress > 0.60:
            print(f"[VOICE_TOOL]  HIGH distress index ({distress:.2f})  user may be masking emotion")
        if formatted_result["emotion"] != "neutral":
            text_hint = result.get("transcription", "")
            if text_hint:
                print(f"[VOICE_TOOL]  Transcription preview: '{text_hint[:80]}'")

        return formatted_result

    except Exception as e:
        print(f"[VOICE_TOOL]  Error analyzing voice: {str(e)}")
        import traceback
        traceback.print_exc()
        return {**default_response, "error": f"Analysis failed: {str(e)}"}
