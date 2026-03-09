"""
Conversation Planner Node - Strategic decision-making for therapeutic approach

ARCHITECTURE NODE 3.0:
Purpose: Decide the optimal therapeutic STRATEGY before generating a response.
         This is the "brain" that determines whether to validate, ask questions,
         reframe thinking, suggest a technique, or encourage reflection.
Runs AFTER trend_analyzer, BEFORE technique_selector
No LLM call - pure deterministic decision matrix

STRATEGY OPTIONS:
  - "no_action"              → Casual/chitchat — respond conversationally only (FIX 3)
  - "validate_only"          → Just listen and validate feelings, no technique
  - "ask_question"           → Ask an open-ended question to deepen understanding
  - "encourage_reflection"   → Guide the user to reflect on their patterns
  - "reframe"               → Help user see situation from a different angle
  - "suggest_technique"      → Recommend a coping technique
  - "distract"              → Lighten the mood with positive redirection

CONVERSATION PHASE DETECTION:
  - NEUTRAL:     Casual or low-signal message — no therapeutic phase (FIX 3)
  - VENTING:     First 1-2 messages with negative emotion
  - REFLECTION:  User asks "why", "how", or expresses understanding
  - SOLUTION:    System suggests technique / user accepts
  - RECOVERY:    Positive shift detected (intensity drops significantly)

TECHNIQUE READINESS SCORE:
  0.0 → User not ready for technique (just venting, needs validation)
  1.0 → User very ready for technique (has been heard, intensity is manageable)
"""

from ..agent.state import MentalHealthState


# Reflection signal words in user messages
_REFLECTION_SIGNALS = {
    "why", "how", "what if", "i think", "i realize", "i wonder",
    "i notice", "maybe", "perhaps", "i should", "i could",
    "i understand", "makes sense", "that helps", "i see",
}

_RECOVERY_POSITIVE_EMOTIONS = {"joy", "surprise", "neutral"}

# Words indicating a direct request for a therapeutic technique
_TECHNIQUE_REQUEST_SIGNALS = {
    "breathing exercise", "breathing technique", "meditation",
    "relaxation technique", "coping technique", "cbt technique",
    "grounding exercise", "mindfulness exercise", "can you guide me",
    "walk me through", "help me with a technique", "suggest a technique",
    "do an exercise", "try an exercise", "practice an exercise",
    "calming exercise", "anxiety exercise", "stress relief",
}


def conversation_planner_node(state: MentalHealthState) -> dict:
    """
    CONVERSATION PLANNER NODE - Strategic therapeutic decision-maker.

    Process:
    1. Determine conversation phase (venting/reflection/solution/recovery)
    2. Calculate technique readiness score
    3. Select optimal strategy based on emotion, intensity, trend, and phase
    4. Output strategy + phase + readiness for downstream nodes

    No LLM call — pure deterministic Python.
    """

    # ============================================
    # EXTRACT DECISION INPUTS
    # ============================================
    emotion = state.get("fused_emotion", state.get("emotion", "neutral"))
    intensity = state.get("fused_intensity", state.get("intensity", 0.5))
    trend = state.get("emotional_trend", "stable")
    messages = state.get("messages", [])
    session_message_count = state.get("session_message_count", 0)
    crisis_detected = state.get("crisis_detected", False)

    # Count user messages in session (approximate from messages list)
    user_msg_count = max(
        session_message_count,
        sum(1 for m in messages if hasattr(m, "type") and m.type == "human")
    )
    current_message = messages[-1].content.lower() if messages else ""

    print(f"\n[NODE: PLANNER] 🧠 Planning strategy | Emotion: {emotion} | "
          f"Intensity: {intensity:.0%} | Trend: {trend} | Messages: {user_msg_count}")

    # ============================================
    # FIX 2: DIRECT TECHNIQUE REQUEST
    # If the user explicitly asks for an exercise, bypass normal readiness
    # logic and immediately grant it.
    # ============================================
    if any(signal in current_message for signal in _TECHNIQUE_REQUEST_SIGNALS):
        print(f"[NODE: PLANNER] 🎯 Direct technique request detected → suggest_technique")
        return {
            "conversation_strategy": "suggest_technique",
            "conversation_phase": state.get("conversation_phase", "venting"),
            "technique_readiness": 1.0,
            "session_message_count": user_msg_count,
        }

    # ============================================
    # FIX 3: CHITCHAT BYPASS GATE
    # If INTENT_CLASSIFIER flagged this as chitchat/skip_intervention,
    # or if emotion is neutral with intensity below threshold —
    # return no_action immediately. Never venting-phase a grocery list.
    # ============================================
    _NEUTRAL_INTENSITY_THRESHOLD = 0.25  # below this + neutral = definitely not therapeutic

    if state.get("skip_intervention", False):
        print(f"[NODE: PLANNER] ⏭️  skip_intervention=True — returning no_action (chitchat bypass)")
        return {
            "conversation_strategy": "no_action",
            "conversation_phase": "neutral",
            "technique_readiness": 0.0,
            "session_message_count": user_msg_count,
        }

    if emotion == "neutral" and intensity < _NEUTRAL_INTENSITY_THRESHOLD:
        print(f"[NODE: PLANNER] ⏭️  Neutral + low intensity ({intensity:.0%}) — returning no_action")
        return {
            "conversation_strategy": "no_action",
            "conversation_phase": "neutral",
            "technique_readiness": 0.0,
            "session_message_count": user_msg_count,
        }

    # ============================================
    # STEP 1: DETERMINE CONVERSATION PHASE
    # ============================================

    phase = _determine_phase(
        emotion=emotion,
        intensity=intensity,
        trend=trend,
        user_msg_count=user_msg_count,
        current_message=current_message,
        current_phase=state.get("conversation_phase", "venting"),
    )

    # ============================================
    # STEP 2: CALCULATE TECHNIQUE READINESS
    # ============================================

    readiness = _calculate_technique_readiness(
        intensity=intensity,
        user_msg_count=user_msg_count,
        trend=trend,
        phase=phase,
    )

    # ============================================
    # STEP 3: SELECT STRATEGY
    # ============================================

    # Crisis override — always suggest technique in crisis
    if crisis_detected:
        strategy = "suggest_technique"
        print(f"[NODE: PLANNER] 🚨 Crisis override → suggest_technique")
    else:
        strategy = _select_strategy(
            emotion=emotion,
            intensity=intensity,
            trend=trend,
            phase=phase,
            readiness=readiness,
            user_msg_count=user_msg_count,
            current_message=current_message,
        )

    print(f"[NODE: PLANNER] ✅ Strategy: {strategy.upper()} | "
          f"Phase: {phase.upper()} | Readiness: {readiness:.0%}")

    return {
        "conversation_strategy": strategy,
        "conversation_phase": phase,
        "technique_readiness": readiness,
        "session_message_count": user_msg_count,
    }


def _determine_phase(
    emotion: str,
    intensity: float,
    trend: str,
    user_msg_count: int,
    current_message: str,
    current_phase: str,
) -> str:
    """
    Detect conversation phase using emotional signals and message patterns.
    Phases only progress forward (venting → reflection → solution → recovery).
    """

    # Recovery: intensity dropped significantly + positive emotion
    if emotion in _RECOVERY_POSITIVE_EMOTIONS and intensity < 0.3:
        return "recovery"

    # Recovery: trend is improving and we were in solution phase
    if current_phase == "solution" and trend == "improving":
        return "recovery"

    # Solution: already past reflection, readiness high
    if current_phase in ("solution", "recovery"):
        # Don't regress from solution unless intensity spikes
        if intensity < 0.7:
            return current_phase
        else:
            return "venting"  # Intensity spike → back to venting

    # Reflection: user shows reflective language
    has_reflection = any(signal in current_message for signal in _REFLECTION_SIGNALS)
    if has_reflection and user_msg_count >= 2:
        return "reflection"

    # Reflection: enough messages exchanged and user is engaged
    if user_msg_count >= 4 and intensity < 0.6:
        return "reflection"

    # Solution: planner previously set reflection and intensity is moderate
    if current_phase == "reflection" and intensity < 0.5:
        return "solution"

    # Venting: early messages or high intensity
    if user_msg_count <= 2 or intensity >= 0.7:
        return "venting"

    # Default: maintain current phase
    return current_phase


def _calculate_technique_readiness(
    intensity: float,
    user_msg_count: int,
    trend: str,
    phase: str,
) -> float:
    """
    Calculate a 0.0-1.0 readiness score for suggesting a technique.
    Higher = user more receptive to technique suggestion.
    """
    readiness = 0.0

    # Intensity factor: moderate intensity = most ready
    if intensity >= 0.5:
        readiness += 0.3
    elif intensity >= 0.3:
        readiness += 0.15

    # Message count factor: more messages = more rapport built
    if user_msg_count >= 3:
        readiness += 0.3
    elif user_msg_count >= 2:
        readiness += 0.15

    # Trend factor: worsening = more urgently needs technique
    if trend == "worsening":
        readiness += 0.2

    # Phase factor: solution/recovery phases are ready
    if phase in ("solution", "recovery"):
        readiness += 0.2
    elif phase == "reflection":
        readiness += 0.1

    return min(1.0, readiness)


def _select_strategy(
    emotion: str,
    intensity: float,
    trend: str,
    phase: str,
    readiness: float,
    user_msg_count: int,
    current_message: str,
) -> str:
    """
    Select therapeutic strategy based on the full context.
    This is the core decision matrix of SentiMind's intelligence.
    """

    # Positive emotions → validate only (don't over-therapize)
    if emotion in _RECOVERY_POSITIVE_EMOTIONS and intensity < 0.4:
        return "validate_only"

    # Very low intensity → just listen
    if intensity < 0.3:
        return "validate_only"

    # First message with moderate intensity → ask to understand more
    if user_msg_count <= 1 and intensity < 0.6:
        return "ask_question"

    # Early conversation with moderate distress → ask before acting
    if user_msg_count <= 2 and intensity < 0.5:
        return "ask_question"

    # Reflection phase → encourage deeper thinking
    if phase == "reflection":
        return "encourage_reflection"

    # Moderate intensity with enough rapport → reframe
    if 0.5 <= intensity < 0.7 and user_msg_count >= 2 and readiness < 0.6:
        return "reframe"

    # High readiness OR worsening trend → suggest technique
    if readiness >= 0.6 or trend == "worsening":
        return "suggest_technique"

    # High intensity → suggest technique (urgent support needed)
    if intensity >= 0.7:
        return "suggest_technique"

    # Default for moderate cases
    if user_msg_count >= 3:
        return "encourage_reflection"

    return "validate_only"
