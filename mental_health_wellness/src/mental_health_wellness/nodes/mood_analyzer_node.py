"""
Mood Analyzer Node - LLM-based emotion detection (v7.0)

ARCHITECTURE NODE 2.5:
Purpose: Analyze user emotion using LLM semantic understanding
Runs AFTER intake node, BEFORE technique selector
LLM-powered classification for nuanced emotion analysis
"""

from ..agent.state import MentalHealthState
from ..tools.mood_tools import analyze_mood as tool_analyze_mood
import time


async def analyze_mood(state: MentalHealthState) -> dict:
    """
    MOOD ANALYZER NODE - LLM-based emotion detection (v7.0).
    
    Process:
    1. Extract user message
    2. Call analyze_mood (LLM emotion classifier - replaced DistilBERT)
    3. Parse results into structured format
    4. Update state with emotion, sentiment, intensity, confidence
    
    v7.0: LLM provides better semantic understanding than DistilBERT ML model
    
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

        # ---- Always run DistilBERT  no keyword gate ----
        # v7.0 CHANGE: Removed keyword-based emotional markers check.
        # DistilBERT is accurate enough for all message types, including short messages.
        # This ensures consistent emotion detection regardless of message length or keywords.

        print(f"[NODE:MOOD]  Analyzing: '{current_message[:60]}...'")
        start_time = time.time()

        mood_result = await tool_analyze_mood.ainvoke({"message": current_message})

        elapsed_ms = int((time.time() - start_time) * 1000)

        emotion = mood_result.get("emotion", "neutral")
        sentiment = mood_result.get("sentiment", "neutral")
        intensity = mood_result.get("intensity", 0.5)
        confidence = mood_result.get("confidence", 0.0)

        print(f"[NODE:MOOD]  {emotion.upper()} | Intensity: {intensity:.0%} | Confidence: {confidence:.0%} | Time: {elapsed_ms}ms")

        return {"emotion": emotion, "sentiment": sentiment, "intensity": intensity, "confidence": confidence}

    except Exception as e:
        print(f"[NODE:MOOD]  Error: {str(e)[:80]}")
        return {"emotion": "neutral", "sentiment": "neutral", "intensity": 0.5, "confidence": 0.0}
