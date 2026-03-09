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
            return {
                "emotion": "neutral",
                "sentiment": "neutral",
                "intensity": 0.5,
                "confidence": 0.0
            }
        
        current_message = messages[-1].content if messages else ""
        
        print(f"[MOOD] 🎭 Analyzing emotion: '{current_message[:50]}...'")
        
        start_time = time.time()
        
        # Call mood analysis tool (DistilBERT)
        mood_result = await analyze_mood.ainvoke({"message": current_message})
        
        elapsed_ms = int((time.time() - start_time) * 1000)
        
        emotion = mood_result.get("emotion", "neutral")
        sentiment = mood_result.get("sentiment", "neutral")
        intensity = mood_result.get("intensity", 0.5)
        confidence = mood_result.get("confidence", 0.0)
        
        print(f"[MOOD] ✅ {emotion.upper()} | Intensity: {intensity:.0%} | Time: {elapsed_ms}ms")
        
        return {
            "emotion": emotion,
            "sentiment": sentiment,
            "intensity": intensity,
            "confidence": confidence
        }
        
    except Exception as e:
        print(f"[MOOD] ❌ Error: {str(e)[:80]}")
        return {
            "emotion": "neutral",
            "sentiment": "neutral",
            "intensity": 0.5,
            "confidence": 0.0
        }
