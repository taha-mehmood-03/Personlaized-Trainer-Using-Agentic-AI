"""
Mood Analysis Tools - Gemini LLM-based emotion detection.

Uses the configured model_mood tier for fast emotion, sentiment, and
sub-emotion analysis. Falls back to keyword heuristics if the LLM call fails.
"""

import json
import re

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage

from ..techniques.emotion_metadata import (
    BEHAVIOR_TAGS,
    CANONICAL_SUB_EMOTIONS,
    PROJECT_STUDY_CONTEXTS,
    SUB_EMOTION_TO_CORE,
    SYMPTOM_TAGS,
)
from ..utils.turn_signals import is_polite_acknowledgement

# ============================================
# CONSTANTS
# ============================================

CORE_EMOTIONS = {
    "anger", "disgust", "fear", "joy", "neutral", "sadness", "surprise", "anxiety"
}

SUB_EMOTIONS = {
    "admiration", "amusement", "anger", "annoyance", "approval", "caring",
    "confusion", "curiosity", "desire", "disappointment", "disapproval",
    "disgust", "embarrassment", "excitement", "fear", "gratitude", "grief",
    "joy", "love", "nervousness", "optimism", "pride", "realization",
    "relief", "remorse", "sadness", "surprise", "neutral",
    "loneliness", "shame", "guilt", "overwhelm", "hopelessness",
    "insecurity", "rejection", "stress", "boredom", "burnout", "calm",
    *CANONICAL_SUB_EMOTIONS,
}

SENTIMENTS = {"positive", "negative", "neutral"}

CONTEXT_TAGS = {
    "general_settling", "nervous_system_regulation", "sleep_onset",
    "bedtime_wind_down", "acute_worry", "acute_pressure",
    "presentation_anxiety", "pre_presentation", "pre_performance",
    "social_re_engagement", "connection_practice", "task_starting",
    "low_energy_activation", "emotion_regulation", "self_compassion",
    "relationship_repair", "practical_problem_solving", "specific_negative_thought",
    "belief_challenge", "avoidance_breaking", "thought_unloading",
    "emotional_reflection", "meaning_and_values", "routine_rebuilding",
    "social_humiliation", "school_conflict", "teacher_conflict",
    "authority_conflict", "interpersonal_conflict",
    *PROJECT_STUDY_CONTEXTS,
}

GO_EMOTIONS_MAP = {
    "admiration": "joy", "amusement": "joy", "approval": "joy", "caring": "joy",
    "desire": "joy", "excitement": "joy", "gratitude": "joy", "joy": "joy",
    "love": "joy", "optimism": "joy", "pride": "joy", "relief": "joy",
    "surprise": "surprise", "realization": "surprise",
    "anger": "anger", "annoyance": "anger", "disapproval": "neutral", "disgust": "disgust",
    "sadness": "sadness", "disappointment": "sadness", "grief": "sadness",
    "remorse": "sadness", "embarrassment": "sadness", "shame": "sadness",
    "guilt": "sadness", "loneliness": "sadness", "hopelessness": "sadness",
    "rejection": "sadness", "insecurity": "sadness",
    "fear": "fear", "nervousness": "anxiety", "anxiety": "anxiety",
    "overwhelm": "anxiety", "stress": "anxiety", "burnout": "anxiety",
    "worry": "anxiety", "panic": "anxiety", "performance_anxiety": "anxiety",
    "social_anxiety": "anxiety", "racing_thoughts": "anxiety",
    "rumination": "anxiety", "avoidance": "anxiety", "tension": "anxiety",
    "restlessness": "anxiety", "procrastination": "anxiety",
    "indecision": "anxiety", "distress": "anxiety",
    "confusion": "neutral", "curiosity": "neutral", "neutral": "neutral",
    "boredom": "neutral", "calm": "neutral",
    "low_mood": "sadness", "emptiness": "sadness", "anhedonia": "sadness",
    "fatigue": "sadness", "self_criticism": "sadness", "regret": "sadness",
    "inadequacy": "sadness", "isolation": "sadness", "numbness": "sadness",
    "irritability": "anger", "frustration": "anger",
    "resentment": "anger", "feeling_disrespected": "anger",
    "people_pleasing": "sadness", "mood_swings": "anxiety",
}

_NEUTRAL_RESULT = {
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
    "emotion_reasoning": "fallback neutral",
}


def _format_allowed_sub_emotions(per_line: int = 8) -> str:
    """Render CANONICAL_SUB_EMOTIONS as a closed-vocabulary block for the prompt.

    The voice prompt (voice/__init__.py) already constrains Gemini to this
    same taxonomy with a hard "MUST be exactly one value" rule. The text
    prompt below previously only gave loose examples, which let Gemini
    return plausible-but-unlisted labels (e.g. "exhaustion") that then failed
    validation and silently collapsed back to the bare core emotion, losing
    nuance. Constraining both prompts to the same closed taxonomy also keeps
    primary_sub_emotion meaningful downstream (technique matching, the
    empathy-first gate, NO_TECHNIQUE_BY_DEFAULT_SUB_EMOTIONS, etc. all speak
    this same vocabulary) instead of accepting valid-but-inert GoEmotions-only
    labels like "admiration" or "approval" that nothing else understands.
    """
    labels = sorted(CANONICAL_SUB_EMOTIONS)
    rows = [
        "  - " + ", ".join(labels[index:index + per_line])
        for index in range(0, len(labels), per_line)
    ]
    return "\n".join(rows)


def _fmt_list(values, limit: int = 5) -> str:
    cleaned = [str(v) for v in (values or []) if v]
    if not cleaned:
        return "none"
    suffix = f", +{len(cleaned) - limit}" if len(cleaned) > limit else ""
    return ", ".join(cleaned[:limit]) + suffix


def _clamp(value, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return default


def _safe_list(value, allowed: set) -> list:
    if not isinstance(value, list):
        return []
    return [str(v).lower().strip() for v in value if str(v).lower().strip() in allowed][:4]


def _derive_structured_tags(message: str) -> tuple[list, list, list, list]:
    """
    Deterministically derive sub-emotions, symptoms, behaviors, and contexts
    from keyword patterns. Used by parallel_intake.py as a lightweight enrichment
    pass that runs alongside the Gemini mood call.
    """
    text = (message or "").lower()
    sub_emotions: list[str] = []
    symptoms: list[str] = []
    behaviors: list[str] = []
    contexts: list[str] = []

    has_exam = any(t in text for t in ("exam", "exams", "test", "quiz", "final", "midterm", "paper"))
    has_sleep = any(t in text for t in ("sleep", "bed", "bedtime", "night", "trying to sleep"))
    has_thought_loop = any(t in text for t in ("thought", "thoughts", "mind", "worry", "overthinking", "racing", "ruminat"))
    has_failure = any(t in text for t in ("fail", "drop out", "dropout", "not pass"))

    if has_exam:
        sub_emotions.append("academic_pressure")
        contexts.extend(["exam_pressure", "academic_anxiety"])
        if any(t in text for t in ("coming week", "next week", "this week", "tomorrow", "soon", "upcoming")):
            contexts.append("exam_week")
    if has_sleep and (has_thought_loop or has_exam):
        sub_emotions.extend(["bedtime_rumination", "worry", "racing_thoughts"])
        symptoms.extend(["sleep_difficulty", "bedtime_racing_thoughts"])
        behaviors.append("rumination")
        contexts.extend(["sleep_difficulty", "bedtime_rumination", "nighttime_worry"])
    if has_failure:
        sub_emotions.extend(["fear_of_failure", "future_threat", "catastrophizing"])
        contexts.extend(["academic_risk", "specific_exam_failure_belief"])
    if any(t in text for t in ("panic", "panicky", "can't breathe", "cant breathe", "heart racing")):
        sub_emotions.append("panic")
        symptoms.append("shortness_of_breath")
    if any(t in text for t in ("all alone", "feel alone", "lonely", "no one", "nobody", "no friends", "left out", "isolated")):
        sub_emotions.extend(["loneliness", "isolation"])
        behaviors.append("isolation")
    if any(t in text for t in ("insulted", "humiliated", "embarrassed", "shamed", "mocked", "laughed at", "bullied", "scolded", "rejected")):
        sub_emotions.extend(["shame", "embarrassment", "rejection"])
        contexts.append("social_humiliation")
        if any(t in text for t in ("principal", "teacher", "class", "classmate", "school")):
            contexts.append("school_conflict")
        if any(t in text for t in ("principal", "teacher")):
            contexts.extend(["teacher_conflict", "authority_conflict"])
    if any(t in text for t in ("worthless", "useless", "not good enough", "i'm a failure", "im a failure")):
        sub_emotions.extend(["self_criticism", "inadequacy", "hopelessness"])
    if any(t in text for t in ("overwhelmed", "overwhelming", "too much", "can't handle", "cant handle")):
        sub_emotions.extend(["overwhelm", "stress"])
    if any(t in text for t in ("procrastinat", "avoid", "putting it off")):
        behaviors.append("procrastination")

    return (
        [s for s in sub_emotions if s in SUB_EMOTIONS],
        [s for s in symptoms if s in SYMPTOM_TAGS],
        [b for b in behaviors if b in BEHAVIOR_TAGS],
        [c for c in contexts if c in CONTEXT_TAGS],
    )


# ============================================
# KEYWORD FALLBACK (used when Gemini fails)
# ============================================

def _keyword_fallback(message: str) -> dict:
    """Fast keyword-based heuristic when Gemini is unavailable."""
    text = message.lower()

    if is_polite_acknowledgement(message):
        return {**_NEUTRAL_RESULT, "emotion_reasoning": "keyword: polite acknowledgement"}

    emotion = "neutral"
    primary_sub = "neutral"
    intensity = 0.45
    sentiment = "neutral"

    if any(w in text for w in ("anxious", "anxiety", "panic", "nervous", "overwhelmed", "stress")):
        emotion, primary_sub, sentiment, intensity = "anxiety", "stress", "negative", 0.70
    elif any(w in text for w in ("sad", "lonely", "hopeless", "empty", "tired of pretending", "exhausted", "depressed")):
        emotion, primary_sub, sentiment, intensity = "sadness", "sadness", "negative", 0.68
    elif any(w in text for w in ("angry", "angry", "frustrated", "furious", "mad", "irritated")):
        emotion, primary_sub, sentiment, intensity = "anger", "frustration", "negative", 0.65
    elif any(w in text for w in ("scared", "afraid", "fear", "terrified")):
        emotion, primary_sub, sentiment, intensity = "fear", "fear", "negative", 0.65
    elif any(w in text for w in ("happy", "excited", "grateful", "proud", "glad")):
        emotion, primary_sub, sentiment, intensity = "joy", "joy", "positive", 0.55

    return {
        "emotion": emotion,
        "sentiment": sentiment,
        "intensity": intensity,
        "confidence": 0.4,
        "raw_emotion_label": primary_sub,
        "primary_sub_emotion": primary_sub,
        "secondary_sub_emotions": [],
        "detected_symptoms": [],
        "detected_behaviors": [],
        "detected_contexts": [],
        "emotion_scores": {emotion: intensity},
        "emotion_reasoning": "keyword heuristic fallback",
    }


# ============================================
# GEMINI LLM MOOD ANALYSIS
# ============================================

_MOOD_SYSTEM_PROMPT_TEMPLATE = """\
You are an expert clinical psychologist specializing in emotion recognition.

You will receive:
1. CONVERSATION HISTORY — the last few turns of this therapy session (for context)
2. CURRENT USER MESSAGE — the message to classify NOW

IMPORTANT: The current message may be a short follow-up reply (e.g. "mostly around my family").
Use the conversation history to understand the full emotional picture before classifying.

ALLOWED PRIMARY/SUB-EMOTIONS (primary_sub_emotion and every entry in
secondary_sub_emotions MUST be exactly one of these values — this is the same
closed taxonomy used everywhere else in the system, including technique
matching):
{allowed_sub_emotions}

Return a JSON object with EXACTLY these fields:

{{
  "emotion": <one of: anger|disgust|fear|joy|neutral|sadness|surprise|anxiety>,
  "primary_sub_emotion": <one value from ALLOWED PRIMARY/SUB-EMOTIONS above, the most specific label supported by evidence>,
  "secondary_sub_emotions": [<up to 3 additional values from ALLOWED PRIMARY/SUB-EMOTIONS, derived from BOTH current message AND conversation history>],
  "sentiment": <one of: positive|negative|neutral>,
  "intensity": <float 0.0-1.0 reflecting overall distress level across the conversation>,
  "confidence": <float 0.0-1.0, your confidence in this classification>,
  "detected_symptoms": [<physical/cognitive signals visible across the conversation, e.g. sleep_difficulty|racing_thoughts|fatigue|numbness>],
  "detected_behaviors": [<behavioral patterns, e.g. isolation|procrastination|rumination|people_pleasing|avoidance>],
  "detected_contexts": [<situational contexts e.g. family_conflict|work_stress|relationship_conflict|academic_pressure|social_isolation>],
  "emotion_scores": {{"anger": 0.0, "disgust": 0.0, "fear": 0.0, "joy": 0.0, "neutral": 0.0, "sadness": 0.0, "surprise": 0.0, "anxiety": 0.0}},
  "reasoning": <one sentence explaining your classification using context>
}}

Rules:
- emotion MUST be one of the 8 core emotions exactly as listed.
- primary_sub_emotion and secondary_sub_emotions MUST be exactly values from ALLOWED PRIMARY/SUB-EMOTIONS. Never invent a label outside that list, even if it seems descriptive — pick the closest allowed match instead (e.g. use "fatigue" instead of "exhaustion").
- Prefer the most specific sub-emotion supported by evidence (for example performance_anxiety, rejection, shame, burnout, bedtime_rumination) instead of a generic label when possible.
- intensity for neutral/joy must be ≤ 0.45. For negative emotions 0.5–0.95.
- If the user is masking distress with positive language, detect the underlying emotion.
- secondary_sub_emotions, detected_symptoms, detected_behaviors, detected_contexts MUST reflect patterns from both the current message AND conversation history.
- Respond ONLY with valid JSON. No markdown, no explanation outside the JSON.
"""

_MOOD_SYSTEM_PROMPT = _MOOD_SYSTEM_PROMPT_TEMPLATE.format(
    allowed_sub_emotions=_format_allowed_sub_emotions()
)


async def _gemini_analyze_mood(message: str, context: str = "") -> dict:
    """Call Gemini LLM to classify mood/sentiment with optional conversation context."""
    from ..llm.groq_llm import get_llm_manager, message_content_to_text

    manager = get_llm_manager()
    model = manager.model_mood

    # Build the user turn: include conversation history if provided
    if context.strip():
        user_content = (
            f"CONVERSATION HISTORY (last few turns):\n{context.strip()}\n\n"
            f"CURRENT USER MESSAGE TO CLASSIFY:\n{message[:600]}"
        )
    else:
        user_content = f"CURRENT USER MESSAGE TO CLASSIFY:\n{message[:600]}"

    llm_messages = [
        SystemMessage(content=_MOOD_SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]

    response = await manager.ainvoke_gemini_with_rotation(
        llm_messages,
        model=model,
        max_tokens=600,
        temperature=0.1,
    )
    raw_text = message_content_to_text(response.content if hasattr(response, "content") else response)

    # Strip markdown fences if present
    raw_text = re.sub(r"```(?:json)?", "", raw_text).strip().strip("`").strip()

    parsed = json.loads(raw_text)
    return parsed


def _validate_gemini_result(parsed: dict, message: str) -> dict:
    """Validate and normalise the Gemini JSON output into the standard schema."""
    emotion = str(parsed.get("emotion", "neutral")).lower().strip()
    if emotion not in CORE_EMOTIONS:
        emotion = GO_EMOTIONS_MAP.get(emotion, "neutral")

    primary_sub = str(parsed.get("primary_sub_emotion", emotion)).lower().strip()
    if primary_sub not in SUB_EMOTIONS:
        primary_sub = emotion

    secondary = [
        s.lower().strip()
        for s in (parsed.get("secondary_sub_emotions") or [])
        if s and s.lower().strip() in SUB_EMOTIONS
    ][:3]

    sentiment = str(parsed.get("sentiment", "neutral")).lower().strip()
    if sentiment not in SENTIMENTS:
        sentiment = "negative" if emotion in {"anger", "sadness", "fear", "anxiety", "disgust"} else (
            "positive" if emotion in {"joy", "surprise"} else "neutral"
        )

    intensity = _clamp(parsed.get("intensity", 0.5))
    confidence = _clamp(parsed.get("confidence", 0.75))

    raw_scores = parsed.get("emotion_scores") or {}
    emotion_scores = {e: _clamp(raw_scores.get(e, 0.0)) for e in CORE_EMOTIONS}
    if not any(emotion_scores.values()):
        emotion_scores[emotion] = confidence

    detected_symptoms = _safe_list(parsed.get("detected_symptoms"), SYMPTOM_TAGS)
    detected_behaviors = _safe_list(parsed.get("detected_behaviors"), BEHAVIOR_TAGS)
    detected_contexts = _safe_list(parsed.get("detected_contexts"), CONTEXT_TAGS)

    # Post-processing overrides
    if is_polite_acknowledgement(message):
        emotion = "neutral"
        primary_sub = "acknowledgement"
        secondary = []
        intensity = min(intensity, 0.20)
        sentiment = "neutral"

    return {
        "emotion": emotion,
        "sentiment": sentiment,
        "intensity": round(intensity, 2),
        "confidence": round(confidence, 2),
        "raw_emotion_label": primary_sub,
        "primary_sub_emotion": primary_sub,
        "secondary_sub_emotions": secondary,
        "detected_symptoms": detected_symptoms,
        "detected_behaviors": detected_behaviors,
        "detected_contexts": detected_contexts,
        "emotion_scores": emotion_scores,
        "emotion_reasoning": f"Gemini: {str(parsed.get('reasoning', ''))[:120]}",
    }


# ============================================
# PUBLIC TOOL
# ============================================

@tool
def analyze_mood(message: str) -> dict:
    """
    Analyze the emotional state of a message using Gemini LLM (v8.0).

    Args:
        message: The user's message to analyze

    Returns:
        Dictionary with emotion, sentiment, intensity, confidence, sub-emotions,
        detected symptoms/behaviors/contexts, and emotion_scores.
    """
    import asyncio

    if not message or not isinstance(message, str):
        return {**_NEUTRAL_RESULT, "emotion_reasoning": "invalid input"}

    async def _run():
        print(f"[MOOD_TOOLS] 🤖 Gemini mood analysis: '{message[:60]}...'")
        parsed = await _gemini_analyze_mood(message)
        result = _validate_gemini_result(parsed, message)
        print(
            f"[MOOD_TOOLS] ✅ Gemini result | "
            f"core={result['emotion'].upper()} | sub={result['primary_sub_emotion']} | "
            f"sentiment={result['sentiment']} | intensity={result['intensity']:.0%} | "
            f"confidence={result['confidence']:.0%}"
        )
        return result

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're inside an async context (normal server path) — use run_coroutine_threadsafe
            import concurrent.futures
            future = asyncio.ensure_future(_run())
            # For sync tool call from LangChain, schedule in existing loop
            return loop.run_until_complete(_run())
        else:
            return loop.run_until_complete(_run())
    except RuntimeError:
        # No event loop — create one
        return asyncio.run(_run())


async def analyze_mood_async(message: str, context: str = "") -> dict:
    """
    Async Gemini mood analysis — preferred for use inside async agent nodes.

    Args:
        message: The current user message to classify.
        context: Optional formatted conversation history string (last N turns).
                 When provided, Gemini uses it to enrich secondary emotions,
                 symptoms, behaviors and contexts for short follow-up replies.
    """
    if not message or not isinstance(message, str):
        return {**_NEUTRAL_RESULT, "emotion_reasoning": "invalid input"}
    
    ctx_label = f"{len(context.splitlines())} ctx lines" if context.strip() else "no ctx"
    print(f"[MOOD_TOOLS] 🤖 Gemini mood | {ctx_label} | msg='{message[:50]}...'")
    parsed = await _gemini_analyze_mood(message, context=context)
    result = _validate_gemini_result(parsed, message)
    print(
        f"[MOOD_TOOLS] ✅ core={result['emotion'].upper()} | sub={result['primary_sub_emotion']} | "
        f"2nd={result['secondary_sub_emotions']} | sentiment={result['sentiment']} | "
        f"intensity={result['intensity']:.0%} | symptoms={result['detected_symptoms']}"
    )
    return result


def preload_emotion_model():
    """No-op: Gemini v8.0 has no local model to preload."""
    print("[MOOD_TOOLS] ℹ️ v8.0: No local model to preload (Gemini LLM backend)")
