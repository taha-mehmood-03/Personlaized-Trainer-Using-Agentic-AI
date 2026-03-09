""" Voice Tools - LangChain tool wrapper for voice emotion analysis """
from langchain_core.tools import tool

@tool
def analyze_voice(audio_path: str) -> dict:
    """
    Analyze voice/speech audio for emotional signals.
    Extracts acoustic features (pitch, loudness, jitter, shimmer) and 
    classifies the speaker's emotion using deep learning.
    
    Args:
        audio_path: Path to the audio file (WAV, MP3, WebM)
    
    Returns:
        Dictionary with emotion, confidence, arousal, valence, and acoustic features
    
    CRITICAL: Must receive an actual file path, not a placeholder!
    """
    # Default error response structure
    default_response = {
        "emotion": "neutral",
        "confidence": 0.0,
        "arousal": 0.5,
        "valence": 0.5,
        "acoustic_features": {
            "pitch_mean": 0,
            "pitch_std": 0,
            "loudness_mean": 0,
            "jitter": 0,
            "shimmer": 0,
        },
        "all_scores": {},
        "extraction_method": "error",
        "error": "Invalid audio path"
    }
    
    # Validate audio_path
    if not audio_path:
        print("[VOICE_TOOL] ❌ ERROR: No audio path provided!")
        return default_response
    
    # Check for placeholder strings (common mistake from prompt injection)
    placeholder_strings = [
        "/path/to/your/voice/message.wav",
        "path_to_your_audio_file.wav",
        "path_to_audio",
        "audio_path",
        "(voice message)",
        "your_voice_message"
    ]
    
    if any(p in audio_path.lower() for p in placeholder_strings):
        print(f"[VOICE_TOOL] ❌ ERROR: Placeholder string received: {audio_path}")
        print("[VOICE_TOOL] This means the system prompt is injecting dummy data!")
        return {**default_response, "error": "Placeholder string - check system prompt"}
    
    # Check if file exists
    import os
    if not os.path.exists(audio_path):
        print(f"[VOICE_TOOL] ❌ ERROR: Audio file not found: {audio_path}")
        return {**default_response, "error": f"File not found: {audio_path}"}
    
    # Check file is readable and has content
    try:
        file_size = os.path.getsize(audio_path)
        if file_size < 1000:  # Less than 1KB is probably broken
            print(f"[VOICE_TOOL] ⚠️ WARNING: Audio file very small ({file_size} bytes)")
    except Exception as e:
        print(f"[VOICE_TOOL] ❌ ERROR: Could not check file: {e}")
        return {**default_response, "error": f"Cannot read file: {str(e)}"}
    
    try:
        print(f"[VOICE_TOOL] 📊 Analyzing audio: {audio_path}")
        
        # Import and run voice analysis
        from ..voice import analyze_voice_full
        
        result = analyze_voice_full(audio_path)
        
        if not result:
            print("[VOICE_TOOL] ❌ analyze_voice_full returned None")
            return default_response
        
        # Extract and format the response
        formatted_result = {
            "emotion": result.get("emotion", "neutral"),
            "confidence": float(result.get("confidence", 0.0)),
            "arousal": float(result.get("arousal", 0.5)),
            "valence": float(result.get("valence", 0.5)),
            "acoustic_features": {
                "pitch_mean": float(result.get("acoustic_features", {}).get("pitch_mean", 0)),
                "pitch_std": float(result.get("acoustic_features", {}).get("pitch_std", 0)),
                "loudness_mean": float(result.get("acoustic_features", {}).get("loudness_mean", 0)),
                "jitter": float(result.get("acoustic_features", {}).get("jitter", 0)),
                "shimmer": float(result.get("acoustic_features", {}).get("shimmer", 0)),
            },
            "all_scores": result.get("all_scores", {}),
            "extraction_method": result.get("extraction_method", "opensmile+wav2vec2"),
            "transcription": result.get("transcription", "")
        }
        
        print(f"[VOICE_TOOL] ✅ Analysis complete: emotion={formatted_result['emotion']}, "
              f"confidence={formatted_result['confidence']:.2f}")
        
        return formatted_result
        
    except Exception as e:
        print(f"[VOICE_TOOL] ❌ Error analyzing voice: {str(e)}")
        import traceback
        traceback.print_exc()
        return {**default_response, "error": f"Analysis failed: {str(e)}"}
