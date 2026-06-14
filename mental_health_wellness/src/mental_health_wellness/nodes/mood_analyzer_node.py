"""
Mood Analyzer Node - Gemini LLM emotion detection (v8.0)

ARCHITECTURE NODE 2.5:
Purpose: Analyze user emotion using Gemini LLM with full conversation context.
Runs AFTER intake node, BEFORE technique selector.
Passes recent conversation history so follow-up messages are correctly classified.
"""

from ..agent.state import MentalHealthState
from ..tools.mood_tools import analyze_mood_async
import time


def _fmt_list(values, limit: int = 4) -> str:
    cleaned = [str(value) for value in (values or []) if value]
    if not cleaned:
        return "none"
    suffix = f", +{len(cleaned) - limit}" if len(cleaned) > limit else ""
    return ", ".join(cleaned[:limit]) + suffix


async def analyze_mood(state: MentalHealthState) -> dict:
    """
    MOOD ANALYZER NODE - Gemini LLM emotion detection (v8.0).

    Process:
    1. Extract current user message + last 6 messages as context window
    2. Call analyze_mood_async with the configured Gemini mood model and full context
    3. Parse and validate structured JSON response
    4. Update state with emotion, sentiment, intensity, confidence, sub-emotions

    v8.0: Gemini receives the full recent conversation so follow-up short
    messages (e.g. 'mostly around my family') are classified correctly using
    the surrounding emotional context.

    Input State:
        - messages: Full message history (uses last 6 turns)

    Output State:
        - emotion: Core emotion (anger, fear, sadness, joy, neutral, surprise, disgust, anxiety)
        - primary_sub_emotion: Most nuanced feeling label (e.g. loneliness, shame, stress)
        - secondary_sub_emotions: Additional nuanced feeling labels
        - detected_symptoms: Body/cognitive signals relevant for technique safety
        - detected_behaviors: Action patterns relevant for technique matching
        - detected_contexts: Situational tags relevant for technique matching
        - emotion_scores: Per-core-emotion confidence scores
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
                "confidence": 0.0,
                "raw_emotion_label": "neutral",
                "primary_sub_emotion": "neutral",
                "secondary_sub_emotions": [],
                "detected_symptoms": [],
                "detected_behaviors": [],
                "detected_contexts": [],
                "emotion_scores": {"neutral": 1.0},
                "emotion_reasoning": "empty message fallback",
            }

        current_message = messages[-1].content if messages else ""

        # ---- Build conversation context window (last 6 messages) ----
        # Gives Gemini enough history to classify short follow-up replies correctly.
        history_window = messages[-7:-1] if len(messages) > 1 else []
        conversation_context = []
        for m in history_window:
            role = getattr(m, "type", "human")
            label = "User" if role == "human" else "Therapist"
            content = str(getattr(m, "content", "") or "")[:200]
            if content.strip():
                conversation_context.append(f"{label}: {content}")
        context_str = "\n".join(conversation_context) if conversation_context else ""

        # ---- Gemini LLM mood analysis (v8.0) ----
        print(f"[NODE:MOOD] 🤖 Gemini analysis | ctx={len(conversation_context)} turns | msg='{current_message[:50]}...'")
        start_time = time.time()

        mood_result = await analyze_mood_async(current_message, context=context_str)

        elapsed_ms = int((time.time() - start_time) * 1000)

        emotion = mood_result.get("emotion", "neutral")
        sentiment = mood_result.get("sentiment", "neutral")
        intensity = mood_result.get("intensity", 0.5)
        confidence = mood_result.get("confidence", 0.0)
        primary_sub_emotion = mood_result.get("primary_sub_emotion", emotion)
        secondary_sub_emotions = mood_result.get("secondary_sub_emotions", [])
        detected_symptoms = mood_result.get("detected_symptoms", [])
        detected_behaviors = mood_result.get("detected_behaviors", [])
        detected_contexts = mood_result.get("detected_contexts", [])

        print(
            "\n[NODE:MOOD] Complete"
            f"\n  emotion={emotion.upper()} | primary_sub={primary_sub_emotion} | sentiment={sentiment}"
            f"\n  intensity={intensity:.0%} | confidence={confidence:.0%} | time={elapsed_ms}ms"
            f"\n  secondary={_fmt_list(secondary_sub_emotions)}"
            f"\n  symptoms={_fmt_list(detected_symptoms)} | behaviors={_fmt_list(detected_behaviors)}"
            f"\n  contexts={_fmt_list(detected_contexts)}"
        )

        return {
            "emotion": emotion,
            "sentiment": sentiment,
            "intensity": intensity,
            "confidence": confidence,
            "raw_emotion_label": mood_result.get("raw_emotion_label", primary_sub_emotion),
            "primary_sub_emotion": primary_sub_emotion,
            "secondary_sub_emotions": secondary_sub_emotions,
            "detected_symptoms": detected_symptoms,
            "detected_behaviors": detected_behaviors,
            "detected_contexts": detected_contexts,
            "emotion_scores": mood_result.get("emotion_scores", {}),
            "emotion_reasoning": mood_result.get("emotion_reasoning", ""),
        }

    except Exception as e:
        print(f"[NODE:MOOD]  Error: {str(e)[:80]}")
        return {
            "emotion": "neutral",
            "sentiment": "neutral",
            "intensity": 0.5,
            "confidence": 0.0,
            "raw_emotion_label": "neutral",
            "primary_sub_emotion": "neutral",
            "secondary_sub_emotions": [],
            "detected_symptoms": [],
            "detected_behaviors": [],
            "detected_contexts": [],
            "emotion_scores": {"neutral": 1.0},
            "emotion_reasoning": "exception fallback",
        }
