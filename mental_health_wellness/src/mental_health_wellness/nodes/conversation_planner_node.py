"""
Conversation Planner Node - Strategic decision-making for therapeutic approach

ARCHITECTURE NODE 3.0:
Purpose: Decide the optimal therapeutic STRATEGY before generating a response.
         This is the "brain" that determines whether to validate, ask questions,
         reframe thinking, suggest a technique, or encourage reflection.
Runs AFTER trend_analyzer, BEFORE technique_selector
No LLM call - pure deterministic decision matrix

STRATEGY OPTIONS:
  - "no_action"               Casual/chitchat  respond conversationally only (FIX 3)
  - "validate_only"           Just listen and validate feelings, no technique
  - "ask_question"            Ask an open-ended question to deepen understanding
  - "encourage_reflection"    Guide the user to reflect on their patterns
  - "reframe"                Help user see situation from a different angle
  - "suggest_technique"       Recommend a coping technique
  - "distract"               Lighten the mood with positive redirection

CONVERSATION PHASE DETECTION:
  - NEUTRAL:     Casual or low-signal message  no therapeutic phase (FIX 3)
  - VENTING:     First 1-2 messages with negative emotion
  - REFLECTION:  User asks "why", "how", or expresses understanding
  - SOLUTION:    System suggests technique / user accepts
  - RECOVERY:    Positive shift detected (intensity drops significantly)

TECHNIQUE READINESS SCORE:
  0.0  User not ready for technique (just venting, needs validation)
  1.0  User very ready for technique (has been heard, intensity is manageable)
"""

from ..agent.state import MentalHealthState
from ..llm.llm_classifier import llm_intent_check


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


async def conversation_planner_node(state: MentalHealthState) -> dict:
    """
    CONVERSATION PLANNER NODE - Strategic therapeutic decision-maker.

    Process:
    1. Determine conversation phase (venting/reflection/solution/recovery)
    2. Calculate technique readiness score
    3. Select optimal strategy based on emotion, intensity, trend, and phase
    4. Output strategy + phase + readiness for downstream nodes

    No LLM call  pure deterministic Python.
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

    recent_context = ""
    if len(messages) > 1:
        ctx_msgs = messages[-4:-1]
        lines = []
        for m in ctx_msgs:
            role = "User" if getattr(m, "type", "") == "human" else "System"
            content = getattr(m, "content", "")
            lines.append(f"{role}: {content}")
        recent_context = "\n".join(lines)

    print(f"\n[NODE: PLANNER]  Planning strategy | Emotion: {emotion} | "
          f"Intensity: {intensity:.0%} | Trend: {trend} | Messages: {user_msg_count}")

    # ============================================
    # v5.2 FIX: TECHNIQUE REQUEST PRE-CHECK
    # Must run BEFORE chitchat bypass  DistilBERT often classifies
    # "help me calm down" as neutral, causing a false no_action bypass.
    # ============================================


    # ============================================
    # CHITCHAT BYPASS GATE
    # Runs AFTER technique pre-check to avoid false no_action on requests.
    # If emotion is neutral with low intensity  return no_action immediately.
    # ============================================

    # ============================================
    # INTENT RETRIEVAL (Prefetch or Evaluate)
    # ============================================
    prefetched_intent = state.get("prefetched_intent")
    intent_result = None
    _gate_is_authoritative = (
        isinstance(prefetched_intent, dict)
        and prefetched_intent.get("source") == "smart_gate"
    )

    if prefetched_intent and isinstance(prefetched_intent, dict) and prefetched_intent.get("intent"):
        intent_result = prefetched_intent
        src_label = "[GATE ✓ authoritative]" if _gate_is_authoritative else "[prefetched]"
        print(f"[NODE: PLANNER]  Using {src_label} intent  skipping LLM call: "
              f"{intent_result['intent']} ({intent_result.get('confidence', 0):.0%}) [saves ~800-1500ms]")
    else:
        # Fallback: gate didn’t run or failed — call llm_intent_check
        from ..llm.llm_classifier import llm_intent_check
        print(f"[NODE: PLANNER]  No prefetch  calling LLM intent classifier...")
        intent_result = await llm_intent_check(current_message, recent_context)

    intent = intent_result.get("intent", "venting")
    intent_confidence = intent_result.get("confidence", 0.0)

    # ============================================
    # CHITCHAT BYPASS GATE
    # ============================================
    # Messages below this intensity + neutral emotion are definitively non-therapeutic.
    _NEUTRAL_INTENSITY_THRESHOLD = 0.25

    if intent == "chitchat":
        if _gate_is_authoritative:
            # Gate already classified this as chitchat and is the authoritative source.
            # Honor it immediately — no confidence threshold check needed.
            # (Gate threshold was already applied in graph.py before reaching here.)
            print(f"[NODE: PLANNER] ✔ Gate is authoritative chitchat — no_action fast-path "
                  f"(gate_conf={intent_confidence:.0%}, emotion override: {emotion})")
            return {
                "conversation_strategy": "no_action",
                "conversation_phase": "neutral",
                "technique_readiness": 0.0,
                "crisis_detected": False,
                "session_message_count": user_msg_count,
                "recommended_techniques_by_category": {},
            }
        # High-confidence chitchat from internal llm_intent_check — apply threshold
        # DistilBERT often misclassifies short factual corrections ('im not taram', 'no thanks')
        # as 'anger'/'fear'. The LLM intent signal is far more reliable for these cases.
        if intent_confidence >= 0.70 or (emotion == "neutral" and intensity < _NEUTRAL_INTENSITY_THRESHOLD):
            print(f"[NODE: PLANNER]  ⭐ Chitchat intent ({intent_confidence:.0%})  no_action fast-path (emotion override: {emotion})")
            return {
                "conversation_strategy": "no_action",
                "conversation_phase": "neutral",
                "technique_readiness": 0.0,
                "crisis_detected": False,
                "session_message_count": user_msg_count,
                "recommended_techniques_by_category": {},
            }

    # ============================================
    # High-confidence intent overrides
    # ============================================
    if intent == "technique_request" and intent_confidence >= 0.65:
        print(f"[NODE: PLANNER]  LLM detected technique request ({intent_confidence:.0%})  suggest_technique")
        return {
            "conversation_strategy": "suggest_technique",
            "conversation_phase": state.get("conversation_phase", "venting"),
            "technique_readiness": 1.0,
            "crisis_detected": False,
            "session_message_count": user_msg_count,
        }

    # Advice-seeking: user wants guidance, not an exercise  validate and advise conversationally
    if intent == "advice_seeking" and intent_confidence >= 0.60:
        print(f"[NODE: PLANNER]  LLM detected advice_seeking ({intent_confidence:.0%})  ask_question (understand before acting)")
        return {
            "conversation_strategy": "ask_question",
            "conversation_phase": state.get("conversation_phase", "venting"),
            "technique_readiness": 0.3,
            "crisis_detected": False,
            "session_message_count": user_msg_count,
        }

    # High-confidence crisis signal from intent  flag for router
    if intent == "crisis_signal" and intent_confidence >= 0.65:
        print(f"[NODE: PLANNER]  LLM detected crisis signal in planner ({intent_confidence:.0%})")
        return {
            "conversation_strategy": "suggest_technique",
            "conversation_phase": state.get("conversation_phase", "venting"),
            "technique_readiness": 1.0,
            "crisis_detected": True,
            "session_message_count": user_msg_count,
        }

    # Use LLM intent as reflection hint for phase detection
    llm_detected_reflection = (intent == "reflection" and intent_confidence >= 0.65)

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
        llm_reflection_hint=llm_detected_reflection,
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

    # Crisis override  always suggest technique in crisis
    if crisis_detected:
        strategy = "suggest_technique"
        print(f"[NODE: PLANNER]  Crisis override  suggest_technique")

    # Reflection override  user is reporting back on a technique they tried
    # This is explicitly a follow-up to a technique, so guide them further through it.
    elif llm_detected_reflection and intent_confidence >= 0.7:
        strategy = "encourage_reflection"
        print(f"[NODE: PLANNER]  Reflection override ({intent_confidence:.0%})  encourage_reflection (user is practicing/reporting a technique)")

    else:
        # ============================================
        # v9.0: CLINICAL SEVERITY OVERRIDES
        # Run BEFORE default strategy selection to enforce safety boundaries.
        # ============================================
        clinical_severity = state.get("clinical_severity", "minimal")

        # SEVERE → always suggest technique + professional referral hint in response
        if clinical_severity == "severe":
            strategy = "suggest_technique"
            print(f"[NODE: PLANNER] 🏥 Clinical override: SEVERE severity → suggest_technique (with professional referral)")

        # MODERATELY SEVERE + moderate+ intensity → push technique earlier
        elif clinical_severity == "moderately_severe" and intensity >= 0.5:
            strategy = "suggest_technique"
            print(f"[NODE: PLANNER] 🏥 Clinical override: MODERATELY_SEVERE + intensity={intensity:.0%} → suggest_technique")

        # MINIMAL + low intensity → don't push, just validate
        elif clinical_severity == "minimal" and intensity < 0.3 and emotion not in _RECOVERY_POSITIVE_EMOTIONS:
            strategy = "validate_only"
            print(f"[NODE: PLANNER] 🏥 Clinical override: MINIMAL severity + low intensity → validate_only")

        else:
            psych_profile = state.get("psych_profile", {})
            strategy = _select_strategy(
                emotion=emotion,
                intensity=intensity,
                trend=trend,
                phase=phase,
                readiness=readiness,
                user_msg_count=user_msg_count,
                current_message=current_message,
                psych_profile=psych_profile,
            )

    print(f"[NODE: PLANNER]  Strategy: {strategy.upper()} | "
          f"Phase: {phase.upper()} | Readiness: {readiness:.0%}")

    return {
        "conversation_strategy": strategy,
        "conversation_phase": phase,
        "technique_readiness": readiness,
        "crisis_detected": crisis_detected, # Pass through existing state or overrides
        "session_message_count": user_msg_count,
    }


def _determine_phase(
    emotion: str,
    intensity: float,
    trend: str,
    user_msg_count: int,
    current_message: str,
    current_phase: str,
    llm_reflection_hint: bool = False,
) -> str:
    """
    Detect conversation phase using emotional signals and message patterns.
    Phases only progress forward (venting  reflection  solution  recovery).
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
            return "venting"  # Intensity spike  back to venting

    # Reflection: user shows reflective language (keyword OR LLM hint)
    has_reflection = (
        any(signal in current_message for signal in _REFLECTION_SIGNALS)
        or llm_reflection_hint
    )
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
    psych_profile: dict = None,
) -> str:
    """
    Select therapeutic strategy based on the full context.
    This is the core decision matrix of SentiMind's intelligence.

    v5.1: Now profile-aware  uses psych_profile to adapt strategy
    based on coping style, resilience, and technique acceptance rate.
    """
    psych_profile = psych_profile or {}
    coping_style = psych_profile.get("copingStyle", "mixed")
    resilience = psych_profile.get("resilienceScore", 0.5)
    acceptance_rate = psych_profile.get("techniqueAccRate", 0.5)

    # ============================================
    # PROFILE-AWARE OVERRIDES (v5.1)
    # Run BEFORE the default rules to adapt to user patterns.
    # ============================================

    # Avoidant coping + moderate distress  don't push techniques, just validate
    # These users historically reject techniques; pushing causes disengagement.
    if coping_style == "avoidant" and 0.3 <= intensity < 0.7 and readiness < 0.7:
        print(f"[NODE: PLANNER]  Profile override: avoidant coping  validate_only (skip technique push)")
        return "validate_only"

    # High resilience + low distress  encourage reflection (they can handle it)
    if resilience > 0.7 and intensity < 0.5 and user_msg_count >= 2:
        print(f"[NODE: PLANNER]  Profile override: high resilience ({resilience:.0%})  encourage_reflection")
        return "encourage_reflection"

    # Low technique acceptance rate + worsening trend  reframe instead of technique
    # If they never accept techniques, stop suggesting and try reframing instead.
    if acceptance_rate < 0.3 and trend == "worsening" and intensity >= 0.5:
        print(f"[NODE: PLANNER]  Profile override: low acceptance ({acceptance_rate:.0%}) + worsening  reframe")
        return "reframe"

    # Proactive coping + high distress  go straight to technique (they want action)
    if coping_style == "proactive" and intensity >= 0.5 and user_msg_count >= 2:
        print(f"[NODE: PLANNER]  Profile override: proactive coping  suggest_technique (action-oriented user)")
        return "suggest_technique"

    # ============================================
    # DEFAULT STRATEGY RULES (unchanged from v5.0)
    # ============================================

    # Positive emotions  validate only (don't over-therapize)
    if emotion in _RECOVERY_POSITIVE_EMOTIONS and intensity < 0.4:
        return "validate_only"

    # Very low intensity  just listen
    if intensity < 0.3:
        return "validate_only"

    # First message with moderate intensity  ask to understand more
    if user_msg_count <= 1 and intensity < 0.6:
        return "ask_question"

    # Early conversation with moderate distress  ask before acting
    if user_msg_count <= 2 and intensity < 0.5:
        return "ask_question"

    # Reflection phase  encourage deeper thinking
    if phase == "reflection":
        return "encourage_reflection"

    # Moderate intensity with enough rapport  reframe
    if 0.5 <= intensity < 0.7 and user_msg_count >= 2 and readiness < 0.6:
        return "reframe"

    # High readiness OR worsening trend  suggest technique
    if readiness >= 0.6 or trend == "worsening":
        return "suggest_technique"

    # High intensity  suggest technique (urgent support needed)
    if intensity >= 0.7:
        return "suggest_technique"

    # Default for moderate cases
    if user_msg_count >= 3:
        return "encourage_reflection"

    return "validate_only"
