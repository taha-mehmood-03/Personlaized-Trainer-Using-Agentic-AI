"""
Mood Analyzer Node - Gemini LLM emotion detection (v8.0)

ARCHITECTURE NODE 2.5:
Purpose: Analyze user emotion using Gemini LLM with full conversation context.
Runs AFTER intake node, BEFORE technique selector.
Passes recent conversation history so follow-up messages are correctly classified.
"""

from ..agent.state import MentalHealthState
from ..tools.mood_tools import analyze_mood_async
from ..utils.distress_anchor import LOW_SIGNAL_EMOTIONS, NEGATIVE_EMOTIONS, has_active_therapeutic_thread
import time


_DISTRESS_CONTINUATION_MARKERS = (
    "worst",
    "worse",
    "at night",
    "night",
    "sleep",
    "can't sleep",
    "cannot sleep",
    "overthink",
    "overthinking",
    "racing thoughts",
    "stuck",
    "lonely",
    "alone",
    "isolated",
    "stress",
    "stressed",
    "anxious",
    "anxiety",
    "worry",
    "worried",
)


def _fmt_list(values, limit: int = 4) -> str:
    cleaned = [str(value) for value in (values or []) if value]
    if not cleaned:
        return "none"
    suffix = f", +{len(cleaned) - limit}" if len(cleaned) > limit else ""
    return ", ".join(cleaned[:limit]) + suffix


def _previous_negative_emotion(state: MentalHealthState) -> str | None:
    for key in ("last_detected_emotion", "fused_emotion", "emotion"):
        emotion = str(state.get(key) or "").lower()
        if emotion in NEGATIVE_EMOTIONS:
            return emotion
    return None


def _anchor_low_signal_followup(
    state: MentalHealthState,
    current_message: str,
    mood_result: dict,
) -> dict:
    """Prevent short distressed continuations from becoming joy/positive.

    The LLM sees recent assistant text too, so very short replies such as
    "It's worst at night" can drift toward the assistant's warm tone. If the
    session has an active concern and the current text still points at distress,
    preserve the distress family instead.
    """
    emotion = str(mood_result.get("emotion") or "neutral").lower()
    sentiment = str(mood_result.get("sentiment") or "neutral").lower()
    if emotion not in LOW_SIGNAL_EMOTIONS and sentiment != "positive":
        return mood_result
    if state.get("gate_route") == "positive_feedback" or "positive_feedback" in (state.get("gate_context_flags") or []):
        return mood_result

    active_thread = (
        has_active_therapeutic_thread(state)
        or state.get("gate_route") == "contextual_followup"
        or "answering_previous_question" in (state.get("gate_context_flags") or [])
    )
    if not active_thread:
        return mood_result

    combined = " ".join(
        str(value or "")
        for value in (
            current_message,
            state.get("active_thread_summary"),
            state.get("primary_concern"),
            state.get("triggering_context"),
            state.get("functional_impact"),
            state.get("core_belief"),
        )
    ).lower()
    if not any(marker in combined for marker in _DISTRESS_CONTINUATION_MARKERS):
        return mood_result

    anchored = _previous_negative_emotion(state)
    if not anchored:
        if any(marker in combined for marker in ("lonely", "alone", "isolated")):
            anchored = "sadness"
        else:
            anchored = "anxiety"

    result = dict(mood_result)
    result["emotion"] = anchored
    result["sentiment"] = "negative"
    result["raw_emotion_label"] = result.get("raw_emotion_label") or anchored
    current_primary = str(result.get("primary_sub_emotion") or "").lower()
    if current_primary in LOW_SIGNAL_EMOTIONS or current_primary in {"joy", "positive", "neutral", ""}:
        if any(marker in combined for marker in ("night", "sleep", "overthink", "racing thoughts")):
            result["primary_sub_emotion"] = "rumination"
        elif any(marker in combined for marker in ("lonely", "alone", "isolated")):
            result["primary_sub_emotion"] = "loneliness"
        else:
            result["primary_sub_emotion"] = anchored

    try:
        current_intensity = float(result.get("intensity") or 0.0)
    except Exception:
        current_intensity = 0.0
    try:
        anchor_intensity = max(
            float(state.get("last_detected_intensity") or 0.0),
            float(state.get("peak_distress_intensity") or 0.0),
            0.45,
        )
    except Exception:
        anchor_intensity = 0.45
    result["intensity"] = max(current_intensity, min(anchor_intensity, 0.75))
    result["emotion_reasoning"] = (
        str(result.get("emotion_reasoning") or "").strip()
        + " | anchored_low_signal_distress_followup"
    ).strip(" |")
    print(
        f"[NODE:MOOD] Anchored low-signal follow-up: {emotion}/{sentiment} "
        f"-> {anchored}/negative"
    )
    return result


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
            content = str(getattr(m, "content", "") or "")[:200]
            if role != "human":
                if "?" not in content:
                    continue
                label = "Assistant question"
            else:
                label = "User"
            if content.strip():
                conversation_context.append(f"{label}: {content}")
        context_str = "\n".join(conversation_context) if conversation_context else ""

        # ---- Gemini LLM mood analysis (v8.0) ----
        print(f"[NODE:MOOD] 🤖 Gemini analysis | ctx={len(conversation_context)} turns | msg='{current_message[:50]}...'")
        start_time = time.time()

        mood_result = await analyze_mood_async(current_message, context=context_str)
        mood_result = _anchor_low_signal_followup(state, current_message, mood_result)

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
