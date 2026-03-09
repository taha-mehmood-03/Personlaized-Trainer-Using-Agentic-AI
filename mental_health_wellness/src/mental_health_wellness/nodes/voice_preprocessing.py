"""
Voice Pre-Processing Node - Sequential audio processing

ARCHITECTURE NODE 0:
Purpose: Convert voice input to text and features
Runs BEFORE the main pipeline if audio is present

SEQUENTIAL STEPS:
1. Save Audio to Temp File - Receive blob, write to disk
2. Speech-to-Text (Transcription) - Convert audio → text using Whisper
3. Extract Voice Features - OpenSMILE/Wav2Vec2 → emotion + acoustics

ERROR HANDLING:
- If STT fails: Uses empty string + original message as fallback
- If feature extraction fails: Returns default neutral features
- All intermediate failures are logged, never crash the pipeline
- Graceful degradation at every step
"""

import tempfile
import os
from pathlib import Path
from typing import Optional, Dict, Any

from ..agent.state import MentalHealthState
from ..voice import analyze_voice_full


async def voice_preprocessing_node(state: MentalHealthState) -> dict:
    """
    Process voice input through sequential steps:
    1. Save audio blob to temporary file
    2. Transcribe audio to text (Speech-to-Text)
    3. Extract voice features (OpenSMILE/librosa + Emotion classification)
    
    Input State:
        - audio_file_path: Path to the audio file OR audio_bytes (from FormData)
        - message: Optional text message from user (fallback if STT fails)
    
    Output State:
        - voice_features: Dict with emotion, confidence, arousal, valence, acoustic_features
        - transcription: Text from speech-to-text
        - final_message: Transcription or fallback message
        - temp_audio_path: Path to saved temp file (for cleanup later)
        - voice_processed: Boolean flag indicating voice was processed
    """
    print(f"\n[NODE: VOICE_PREPROCESSING] 🎤 Starting voice processing")
    
    # Get audio input
    audio_file_path = state.get("audio_file_path", "")
    audio_bytes = state.get("audio_bytes", None)
    message = state.get("message", "")
    
    if not audio_file_path and not audio_bytes:
        print("[NODE: VOICE_PREPROCESSING] ⚠️ No audio input found - skipping voice processing")
        return {
            "voice_processed": False,
            "voice_features": None,
            "transcription": "",
            "final_message": message
        }
    
    temp_audio_path = None
    try:
        # ============================================
        # STEP 1: SAVE AUDIO TO TEMP FILE
        # ============================================
        
        print("[NODE: VOICE_PREPROCESSING] 💾 Step 1: Saving audio to temp file")
        
        if audio_bytes:
            # If raw bytes provided, save them
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_bytes)
                temp_audio_path = tmp.name
            print(f"[NODE: VOICE_PREPROCESSING] ✅ Saved audio bytes: {temp_audio_path}")
        else:
            # If file path provided, use it
            temp_audio_path = audio_file_path
            print(f"[NODE: VOICE_PREPROCESSING] ✅ Using provided audio file: {temp_audio_path}")
        
        if not os.path.exists(temp_audio_path):
            print(f"[NODE: VOICE_PREPROCESSING] ⚠️ Audio file not found: {temp_audio_path}")
            return {
                "voice_processed": False,
                "voice_features": None,
                "transcription": "",
                "final_message": message,
                "temp_audio_path": None
            }
        
        # ============================================
        # STEP 2: SPEECH-TO-TEXT (TRANSCRIPTION)
        # ============================================
        
        print("[NODE: VOICE_PREPROCESSING] 📝 Step 2: Transcribing audio to text")
        
        transcription = await _transcribe_audio(temp_audio_path)
        
        if not transcription:
            print("[NODE: VOICE_PREPROCESSING] ⚠️ Transcription returned empty/None")
            # Strict mode: fail if transcription fails
            raise ValueError("Speech-to-Text failed to transcribe audio")
        
        print(f"[NODE: VOICE_PREPROCESSING] ✅ Transcription: '{transcription[:100]}...'")
        
        # ============================================
        # STEP 3: EXTRACT VOICE FEATURES & EMOTION
        # ============================================
        
        print("[NODE: VOICE_PREPROCESSING] 🔊 Step 3: Extracting voice features & emotion")
        
        voice_features = await _extract_voice_features(temp_audio_path)
        
        if not voice_features:
            print("[NODE: VOICE_PREPROCESSING] ⚠️ Feature extraction failed")
            voice_features = _get_default_voice_features()
        
        print(f"[NODE: VOICE_PREPROCESSING] ✅ Voice emotion: {voice_features.get('emotion', 'unknown')} "
              f"(confidence: {voice_features.get('confidence', 0):.2f})")
        
        # ============================================
        # RETURN PROCESSED VOICE DATA
        # ============================================
        
        # Use transcription as the main message
        final_message = transcription if transcription else message
        
        return {
            "voice_processed": True,
            "voice_features": voice_features,
            "transcription": transcription,
            "final_message": final_message,
            "temp_audio_path": temp_audio_path,
            "message": final_message  # Override message with transcription
        }
    
    except Exception as e:
        print(f"[NODE: VOICE_PREPROCESSING] ❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return {
            "voice_processed": False,
            "voice_features": None,
            "transcription": "",
            "final_message": message,
            "temp_audio_path": temp_audio_path
        }


async def _transcribe_audio(audio_path: str) -> str:
    """
    Convert audio file to text using Speech-to-Text.
    
    Uses the existing transcribe_audio() from voice module which has
    fallback chains for multiple STT implementations.
    """
    try:
        from ..voice import transcribe_audio
        
        print("[VOICE_PREPROCESSING] 📝 Attempting transcription via voice module")
        
        # Note: transcribe_audio is NOT async, even though we're in async context
        # It's fine to call it directly since it doesn't do heavy I/O
        transcription = transcribe_audio(audio_path)
        
        if transcription:
            print(f"[VOICE_PREPROCESSING] ✅ Transcription success: '{transcription[:80]}...'")
            return transcription
        else:
            print("[VOICE_PREPROCESSING] ⚠️ Transcription returned empty string")
            return ""
    
    except Exception as e:
        print(f"[VOICE_PREPROCESSING] ❌ Transcription error: {str(e)}")
        # Propagate error in strict mode
        raise e


async def _extract_voice_features(audio_path: str) -> Optional[Dict[str, Any]]:
    """
    Extract voice features using OpenSMILE/librosa + Emotion classification.
    """
    try:
        # Call the full voice analysis function
        result = analyze_voice_full(audio_path)
        
        if not result:
            return None
        
        return {
            "emotion": result.get("emotion", "neutral"),
            "confidence": float(result.get("confidence", 0.0)),
            "arousal": float(result.get("arousal", 0.5)),
            "valence": float(result.get("valence", 0.5)),
            "acoustic_features": result.get("acoustic_features", {}),
            "all_scores": result.get("all_scores", {}),
            "extraction_method": result.get("extraction_method", "opensmile+wav2vec2")
        }
    
    except Exception as e:
        print(f"[VOICE_PREPROCESSING] ⚠️ Feature extraction error: {str(e)}")
        return None


def _get_default_voice_features() -> Dict[str, Any]:
    """
    Return default/neutral voice features when extraction fails.
    """
    return {
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
        "extraction_method": "fallback"
    }
