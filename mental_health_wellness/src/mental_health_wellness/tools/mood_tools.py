"""
Mood Analysis Tools - Emotion detection and analysis
"""

from langchain_core.tools import tool

# Lazy load emotion model
_emotion_pipeline = None


def _get_emotion_pipeline():
    """Lazy load emotion model. Raises if model cannot be loaded."""
    global _emotion_pipeline
    if _emotion_pipeline is None:
        from transformers import pipeline
        print("[TOOLS] 🔄 Loading emotion model (SamLowe/roberta-base-go_emotions)...")
        _emotion_pipeline = pipeline(
            "text-classification",
            model="SamLowe/roberta-base-go_emotions",
            device=-1
        )
        print("[TOOLS] ✅ Emotion model loaded")
    return _emotion_pipeline


def preload_emotion_model():
    """Eagerly preload emotion model on startup."""
    _get_emotion_pipeline()


@tool
def analyze_mood(message: str) -> dict:
    """
    Analyze the emotional state of a message.
    Use this tool when the user shares their feelings or seems emotional.
    
    Args:
        message: The user's message to analyze
        
    Returns:
        Dictionary with emotion, sentiment, intensity, and confidence
    """
    try:
        if not message or not isinstance(message, str):
            print("[MOOD_TOOLS] ⚠️ Invalid input - returning neutral")
            return {
                "emotion": "neutral",
                "sentiment": "neutral",
                "intensity": 0.5,
                "confidence": 0.0
            }
        
        pipe = _get_emotion_pipeline()
        
        results = pipe(message[:512])
        if not results:
            print("[MOOD_TOOLS] ⚠️ Model returned no results - returning neutral")
            return {
                "emotion": "neutral",
                "sentiment": "neutral",
                "intensity": 0.5,
                "confidence": 0.0
            }
        
        top_result = results[0]
        raw_emotion = top_result['label'].lower()
        confidence = round(top_result['score'], 2)
        
        # GoEmotions (28 labels) -> SentiMind Core Emotions (6 labels)
        go_emotions_map = {
            # Joy / Positive cluster
            'admiration': 'joy', 'amusement': 'joy', 'approval': 'joy', 'caring': 'joy',
            'desire': 'joy', 'excitement': 'joy', 'gratitude': 'joy', 'joy': 'joy',
            'love': 'joy', 'optimism': 'joy', 'pride': 'joy', 'relief': 'joy',
            # Surprise cluster
            'surprise': 'surprise', 'realization': 'surprise',
            # Anger / Disgust cluster
            'anger': 'anger', 'annoyance': 'anger', 'disapproval': 'anger', 'disgust': 'disgust',
            # Sadness cluster
            'sadness': 'sadness', 'disappointment': 'sadness', 'grief': 'sadness', 'remorse': 'sadness',
            # Fear / Anxiety cluster
            'fear': 'fear', 'nervousness': 'anxiety',
            # Neutral / Ambiguous
            'confusion': 'neutral', 'curiosity': 'neutral', 'neutral': 'neutral'
        }
        
        # Map to core emotion
        emotion = go_emotions_map.get(raw_emotion, "neutral")
        
        # Context-aware correction for commonly misinterpreted phrases
        message_lower = message.lower()
        
        # Negative context phrases that indicate the emotion is NOT positive
        mocking_context_indicators = [
            "laughed at me", "laughing at me", "made fun of me", "mocked me",
            "laughed at my", "laughing at my", "everyone laughed",
            "they laughed", "he laughed", "she laughed", "people laughed"
        ]
        
        failure_context_indicators = [
            "good at nothing", "im a failure", "i'm a failure", "fail at everything",
            "good for nothing", "so stupid", "useless", "pointless"
        ]
        
        # If model detected joy/surprise but message has negative context, correct it
        if emotion in ['joy', 'surprise']:
            if any(phrase in message_lower for phrase in mocking_context_indicators):
                print(f"[MOOD_TOOLS] ✅ Context correction: '{emotion}' → 'sadness' (detected mocking context)")
                emotion = 'sadness'
                confidence = 0.80
            elif any(phrase in message_lower for phrase in failure_context_indicators):
                print(f"[MOOD_TOOLS] ✅ Context correction: '{emotion}' → 'sadness' (detected failure/worthlessness context)")
                emotion = 'sadness'
                confidence = 0.85
        
        sentiment_map = {
            'anger': 'negative', 'disgust': 'negative', 'fear': 'negative',
            'sadness': 'negative', 'anxiety': 'negative',
            'joy': 'positive', 'surprise': 'positive',
            'neutral': 'neutral'
        }
        
        # Calculate therapeutic intensity based on emotion type
        if emotion == 'neutral':
            # Neutral statements shouldn't trigger high-intensity interventions
            intensity = round(0.1 + (confidence * 0.15), 2)  # Max 0.25
        elif emotion in ['joy', 'surprise']:
            # Positive emotions shouldn't trigger crisis/distress protocols
            intensity = round(0.15 + (confidence * 0.2), 2) # Max 0.35
        else:
            # Negative emotions: high confidence = high distress intensity
            intensity = round(confidence * 0.9 + 0.1, 2)
        
        return {
            "emotion": emotion,
            "sentiment": sentiment_map.get(emotion, "neutral"),
            "intensity": intensity,
            "confidence": confidence
        }
    
    except Exception as e:
        print(f"[MOOD_TOOLS] ❌ Error analyzing mood: {str(e)[:100]}")
        print(f"[MOOD_TOOLS] 🛡️ Returning neutral fallback")
        return {
            "emotion": "neutral",
            "sentiment": "neutral",
            "intensity": 0.5,
            "confidence": 0.0
        }

