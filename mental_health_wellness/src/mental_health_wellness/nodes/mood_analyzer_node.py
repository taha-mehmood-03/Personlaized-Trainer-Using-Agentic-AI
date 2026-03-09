"""
Mood Analyzer Node - Deterministic Python-based emotion detection

ARCHITECTURE NODE 2.5:
Purpose: Analyze user emotion using DistilBERT without LLM
Runs AFTER intake node, BEFORE technique selector
No LLM call - pure Python processing
"""

from ..agent.state import MentalHealthState
from ..tools.mood_tools import analyze_mood
import time


async def mood_analyzer_node(state: MentalHealthState) -> dict:
    """
    MOOD ANALYZER NODE - Deterministic emotion detection using DistilBERT.
    
    Process:
    1. Extract user message
    2. Call analyze_mood (DistilBERT emotion model)
    3. Parse results into structured format
    4. Update state with emotion, sentiment, intensity, confidence
    
    No LLM involved - pure Python/PyTorch inference
    
    Input State:
        - messages: Current user message
    
    Output State:
        - emotion: Detected emotion (anger, fear, sadness, joy, neutral, surprise, disgust, anxiety)
        - sentiment: positive, negative, neutral
        - intensity: 0.0-1.0
        - confidence: 0.0-1.0
    """
    
    try:
        messages = state.get("messages", [])

        if not messages:
            return {"emotion": "neutral", "sentiment": "neutral", "intensity": 0.5, "confidence": 0.0}

        current_message = messages[-1].content if messages else ""

        # ---- Quick chitchat gate: skip DistilBERT for obvious non-emotional messages ----
        # Short messages with no emotional markers can safely be classified as neutral
        # This saves ~400ms of unnecessary ML inference
        _EMOTIONAL_MARKERS = {
            "feel", "feeling", "sad", "happy", "angry", "anxious", "scared",
            "depressed", "nervous", "stressed", "overwhelmed", "cry", "hurt",
            "pain", "lonely", "hopeless", "afraid", "worried", "panic"
        }
        words = current_message.lower().split()
        is_chitchat = (
            len(words) <= 5
            and not any(marker in words for marker in _EMOTIONAL_MARKERS)
            and not any(c in current_message for c in ['!', '?', '...'])
        )
        if is_chitchat:
            print(f"[NODE:MOOD] ⏩ Short chitchat detected — skipping DistilBERT (neutral default)")
            return {"emotion": "neutral", "sentiment": "neutral", "intensity": 0.2, "confidence": 0.0}

        print(f"[NODE:MOOD] 🎤 Analyzing: '{current_message[:60]}...'")
        start_time = time.time()

        mood_result = await analyze_mood.ainvoke({"message": current_message})

        elapsed_ms = int((time.time() - start_time) * 1000)

        emotion = mood_result.get("emotion", "neutral")
        sentiment = mood_result.get("sentiment", "neutral")
        intensity = mood_result.get("intensity", 0.5)
        confidence = mood_result.get("confidence", 0.0)

        print(f"[NODE:MOOD] ✅ {emotion.upper()} | Intensity: {intensity:.0%} | Confidence: {confidence:.0%} | Time: {elapsed_ms}ms")

        return {"emotion": emotion, "sentiment": sentiment, "intensity": intensity, "confidence": confidence}

    except Exception as e:
        print(f"[NODE:MOOD] ❌ Error: {str(e)[:80]}")
        return {"emotion": "neutral", "sentiment": "neutral", "intensity": 0.5, "confidence": 0.0}
