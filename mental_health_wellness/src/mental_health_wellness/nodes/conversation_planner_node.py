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

import re

from ..agent.state import MentalHealthState
from ..llm.llm_classifier import llm_intent_check
from ..techniques.emotion_metadata import EMPATHY_FIRST_SUB_EMOTIONS, NO_TECHNIQUE_BY_DEFAULT_SUB_EMOTIONS
from .consent_parser import get_suppressed_topic_labels


# Reflection signal words in user messages
_REFLECTION_SIGNALS = {
    "why", "how", "what if", "i think", "i realize", "i wonder",
    "i notice", "maybe", "perhaps", "i should", "i could",
    "i understand", "makes sense", "that helps", "i see",
}

_RECOVERY_POSITIVE_EMOTIONS = {"joy", "surprise", "neutral"}
_LOW_SIGNAL_EMOTIONS = {"neutral", "joy", "surprise"}
_ACTIONABLE_DISTRESS_EMOTIONS = {"anxiety", "fear", "sadness", "anger", "disgust"}
_ACTIONABLE_EMOTIONAL_REGISTERS = {"distress", "crisis"}
_THERAPEUTIC_CONCERN_TERMS = {
    "anxiety", "anxious", "stress", "stressed", "panic", "fear", "worried",
    "worry", "sad", "sadness", "depression", "depressed", "low", "empty",
    "hopeless", "grief", "anger", "angry", "trauma", "sleep", "insomnia",
    "lonely", "loneliness", "alone", "isolated", "isolation", "left out",
    "exam", "presentation", "fyp", "viva", "project demonstration",
}
_SLOW_PACED_CONCERN_TERMS = {
    "lonely", "loneliness", "alone", "isolated", "isolation", "left out",
    "no friends", "no one", "nobody", "disconnected",
}

# Words indicating a direct request for a therapeutic technique
_TECHNIQUE_REQUEST_SIGNALS = {
    "breathing exercise", "breathing technique", "meditation",
    "relaxation technique", "coping technique", "cbt technique",
    "grounding exercise", "mindfulness exercise", "can you guide me",
    "walk me through", "help me with a technique", "suggest a technique",
    "do an exercise", "try an exercise", "practice an exercise",
    "calming exercise", "anxiety exercise", "stress relief",
}

_STAGE_TO_PHASE = {
    "DISCOVERY": "venting",
    "UNDERSTANDING": "reflection",
    "INTERVENTION": "solution",
    "FOLLOW_UP": "solution",
    "RECOVERY": "recovery",
    "CRISIS": "venting",
    "CHITCHAT": "neutral",
}

MAX_CONTEXT_QUESTIONS_BEFORE_ACTION = 2
MAX_SLOW_PACED_CONTEXT_QUESTIONS_BEFORE_ACTION = 3


def _plain(text: str) -> str:
    return re.sub(r"[^\w\s]", "", (text or "").lower()).strip()


def _looks_like_no_more_details(text: str) -> bool:
    clean = _plain(text)
    if clean in {
        "no nothing more",
        "nothing more",
        "nothing else",
        "no more",
        "nope nothing else",
        "nah nothing else",
        "thats all",
        "that is all",
        "thats it",
        "that is it",
        "no thats all",
        "no that is all",
        "no thats it",
        "no that is it",
        "i shared everything",
        "i have shared everything",
        "ive shared everything",
        "i told you everything",
        "i dont know what else",
        "i do not know what else",
        "nothing specific",
    }:
        return True
    return any(
        marker in clean
        for marker in (
            "shared everything with you",
            "shared everything with u",
            "told you everything",
            "dont have any other details",
            "do not have any other details",
            "no other details",
            "nothing else to add",
            "nothing more to add",
        )
    )


def _message_text(message) -> str:
    return (getattr(message, "content", "") or "").strip()


def _is_short_incomplete(text: str) -> bool:
    words = text.strip().split()
    return 0 < len(words) <= 5 and not text.strip().endswith("?")


def _classify_contextual_intent(current_message: str, messages: list, base_intent: str) -> tuple[str, list[str], str | None]:
    """Deterministic in-session intent refinement for short follow-ups."""
    text = (current_message or "").strip()
    lower = text.lower()
    clean = re.sub(r"[^\w\s]", "", lower).strip()
    flags: list[str] = []
    referenced: str | None = None
    has_prior_turn = any(getattr(m, "type", "") in {"human", "ai"} for m in messages[:-1])

    if has_prior_turn and _is_short_incomplete(text):
        flags.append("continuation")

    if has_prior_turn and re.search(r"\b(about\s+)?\d+\s*(day|days|week|weeks|month|months|year|years)\b", lower):
        return "contextual_followup", flags + ["duration_answer", "answering_previous_question"], text

    if has_prior_turn and clean in {"math", "maths", "mathematics", "english", "physics", "chemistry", "biology", "history", "computer science", "cs"}:
        return "contextual_followup", flags + ["subject_answer", "answering_previous_question"], text

    if any(sig in lower for sig in ("didn't like", "did not like", "didn't help", "did not help", "not helpful", "not working", "i hated that exercise", "doesn't suit me", "does not suit me", "style suits me", "not for me", "didn't land", "did not land", "my mind argued with it")):
        return "reject_technique", flags + ["reject_technique", "technique_rejection"], "latest_recommended_technique"

    if has_prior_turn and _looks_like_no_more_details(text):
        return "contextual_followup", flags + ["answering_previous_question", "no_more_details", "context_complete"], "active_concern"

    if any(sig in lower for sig in ("helped me more", "worked better", "that one helped", "i prefer", "i liked that one")):
        return "technique_preference_update", flags + ["preference_update"], "latest_recommended_technique"

    if any(sig in lower for sig in ("what was", "what's its name", "what was its name", "first breathing exercise", "which technique", "what technique", "what was that called", "what was it called", "remind me what", "name of that")):
        return "memory_query", flags + ["memory_query", "technique_name_query", "refers_to_previous_technique"], "technique"

    if any(sig in lower for sig in ("what do you think", "your opinion", "what do you make of", "what do you think about it", "your read", "read on this", "read on that")):
        return "contextual_followup", flags + ["asking_opinion", "refers_to_previous_topic"], "active_concern"

    if any(sig in lower for sig in ("suggest something", "something to help", "what should i do", "what can i do", "how can i handle", "how do i deal", "any advice", "can you help", "give me something", "can you suggest")):
        return "advice_seeking", flags + ["help_request"], "active_concern"

    if has_prior_turn and any(sig in lower for sig in ("at night", "before studying", "during studying", "during the exam", "before the exam")):
        return "contextual_followup", flags + ["trigger_answer", "answering_previous_question"], text

    if has_prior_turn and _is_short_incomplete(text):
        return "contextual_followup", flags + ["short_followup"], text

    return base_intent or "therapeutic", flags, referenced


def _derive_context_updates(intent: str, current_message: str, state: MentalHealthState) -> dict:
    """Extract compact concern fields from the latest turn without a new LLM call."""
    text = (current_message or "").strip()
    lower = text.lower()
    updates = {
        "primary_concern": state.get("primary_concern"),
        "concern_duration": state.get("concern_duration"),
        "triggering_subject": state.get("triggering_subject"),
        "triggering_context": state.get("triggering_context"),
        "functional_impact": state.get("functional_impact"),
        "core_belief": state.get("core_belief"),
    }

    if not updates["primary_concern"] and any(k in lower for k in ("exam", "test", "study", "studying")):
        updates["primary_concern"] = "exam anxiety"
    elif not updates["primary_concern"] and any(k in lower for k in ("fyp", "capstone", "presentation", "viva", "defense", "defence")):
        updates["primary_concern"] = "presentation anxiety"
    elif not updates["primary_concern"] and any(k in lower for k in ("project", "final demonstration", "demo", "supervisor", "supervisors")):
        updates["primary_concern"] = "project demonstration anxiety"
    elif not updates["primary_concern"] and any(k in lower for k in ("anxious", "anxiety", "worried", "stress", "stressed")):
        updates["primary_concern"] = "anxiety"
    elif not updates["primary_concern"] and any(k in lower for k in ("lonely", "loneliness", "alone", "isolated", "left out", "disconnected")):
        updates["primary_concern"] = "loneliness"

    clean = re.sub(r"[^\w\s]", "", lower).strip()

    if intent == "duration_answer" or re.search(r"\b(about\s+)?\d+\s*(day|days|week|weeks|month|months|year|years)\b", lower):
        updates["concern_duration"] = text
    elif intent == "subject_answer" or clean in {"math", "maths", "mathematics", "english", "physics", "chemistry", "biology", "history", "computer science", "cs"}:
        updates["triggering_subject"] = text
    elif intent == "trigger_answer" or any(sig in lower for sig in ("at night", "before studying", "during studying", "during the exam", "before the exam", "final demonstration", "demo", "presentation", "viva", "defense", "defence", "teacher", "teachers", "panel", "asking questions", "supervisor", "supervisors")):
        updates["triggering_context"] = text

    if any(sig in lower for sig in ("can't focus", "cant focus", "blank", "forget", "panic", "avoid", "not studying", "shut down", "nothing gets done", "wasting time", "drained", "tired")):
        updates["functional_impact"] = text
    if any(sig in lower for sig in ("i will fail", "i'll fail", "ill fail", "i'm going to fail", "im going to fail", "not good enough", "i can't do", "disappoint", "wasn't enough", "wasnt enough", "should be fine", "should be doing", "guilty", "guilt", "all my work")):
        updates["core_belief"] = text

    # If compact state was not available (for example after a server restart or
    # DB-only hydration), recover the active thread from same-session messages.
    # This keeps continuity in the existing broad intent system instead of
    # inventing narrow intents for every short reply.
    prior_human_messages = [
        _message_text(m)
        for m in (state.get("messages") or [])[:-1]
        if getattr(m, "type", "") == "human" and _message_text(m)
    ]
    for prior_text in prior_human_messages[-6:]:
        prior_lower = prior_text.lower()
        prior_clean = re.sub(r"[^\w\s]", "", prior_lower).strip()

        if not updates["primary_concern"]:
            if any(k in prior_lower for k in ("exam", "test", "study", "studying")):
                updates["primary_concern"] = "exam anxiety"
            elif any(k in prior_lower for k in ("fyp", "capstone", "presentation", "viva", "defense", "defence")):
                updates["primary_concern"] = "presentation anxiety"
            elif any(k in prior_lower for k in ("project", "final demonstration", "demo", "supervisor", "supervisors")):
                updates["primary_concern"] = "project demonstration anxiety"
            elif any(k in prior_lower for k in ("presentation", "public speaking", "speech")):
                updates["primary_concern"] = "presentation anxiety"
            elif any(k in prior_lower for k in ("anxious", "anxiety", "worried", "stress", "stressed")):
                updates["primary_concern"] = "anxiety"
            elif any(k in prior_lower for k in ("lonely", "loneliness", "alone", "isolated", "left out", "disconnected")):
                updates["primary_concern"] = "loneliness"

        if not updates["concern_duration"] and re.search(r"\b(about\s+)?\d+\s*(day|days|week|weeks|month|months|year|years)\b", prior_lower):
            updates["concern_duration"] = prior_text

        if not updates["triggering_subject"] and prior_clean in {"math", "maths", "mathematics", "english", "physics", "chemistry", "biology", "history", "computer science", "cs"}:
            updates["triggering_subject"] = prior_text

        if not updates["triggering_context"] and any(sig in prior_lower for sig in ("rehearse alone", "at night", "before studying", "during studying", "during the exam", "before the exam", "during meetings", "final demonstration", "demo", "presentation", "viva", "defense", "defence", "teacher", "teachers", "panel", "asking questions", "supervisor", "supervisors")):
            updates["triggering_context"] = prior_text

        if not updates["functional_impact"] and any(sig in prior_lower for sig in ("can't focus", "cant focus", "blank", "forget", "panic", "avoid", "not studying", "shut down", "nothing gets done", "wasting time", "drained", "tired")):
            updates["functional_impact"] = prior_text

        if not updates["core_belief"] and any(sig in prior_lower for sig in ("i will fail", "i'll fail", "ill fail", "i'm going to fail", "im going to fail", "not good enough", "i can't do", "disappoint", "wasn't enough", "wasnt enough", "should be fine", "should be doing", "guilty", "guilt", "all my work")):
            updates["core_belief"] = prior_text

    return updates


def _count_context_slots(state_like: dict) -> int:
    return sum(1 for key in ("primary_concern", "concern_duration", "triggering_subject", "triggering_context", "functional_impact", "core_belief") if state_like.get(key))


def _has_therapeutic_concern_context(state_like: dict) -> bool:
    """Return true when structured context describes an emotional/clinical concern."""
    context_text = " ".join(
        str(state_like.get(key) or "")
        for key in (
            "current_topic",
            "primary_concern",
            "triggering_context",
            "functional_impact",
            "core_belief",
        )
    ).lower()
    return any(term in context_text for term in _THERAPEUTIC_CONCERN_TERMS)


def _has_slow_paced_concern_context(state_like: dict) -> bool:
    """Concerns like loneliness need a little more relational understanding."""
    primary_sub = str(state_like.get("primary_sub_emotion") or "").lower()
    secondary_subs = {
        str(item).lower()
        for item in (state_like.get("secondary_sub_emotions") or [])
        if item
    }
    if primary_sub in EMPATHY_FIRST_SUB_EMOTIONS or secondary_subs & EMPATHY_FIRST_SUB_EMOTIONS:
        return True

    context_text = " ".join(
        str(state_like.get(key) or "")
        for key in (
            "current_topic",
            "primary_concern",
            "triggering_context",
            "functional_impact",
            "core_belief",
        )
    ).lower()
    return any(term in context_text for term in _SLOW_PACED_CONCERN_TERMS)


def _has_actionable_therapy_signal(
    *,
    emotion: str,
    intensity: float,
    emotional_register: str,
    context_state: dict,
    crisis_detected: bool,
) -> bool:
    """
    Context-complete means stop gathering background, not automatically select
    an exercise. This signal says whether the completed context is actually
    therapeutic enough to move into intervention.
    """
    if crisis_detected:
        return True

    normalized_emotion = (emotion or "neutral").lower()
    normalized_register = (emotional_register or "neutral").lower()

    if normalized_register in _ACTIONABLE_EMOTIONAL_REGISTERS:
        return True

    if normalized_emotion in _ACTIONABLE_DISTRESS_EMOTIONS and intensity >= 0.35:
        return True

    if normalized_register == "concern" and _has_therapeutic_concern_context(context_state):
        return True

    # Mood analysis is intentionally skipped for many contextual follow-ups, so
    # a neutral current turn can still be therapy-ready when the structured
    # thread is clearly about anxiety, stress, low mood, sleep, etc.
    return _has_therapeutic_concern_context(context_state)


def _stage_from_context(intent: str, state: MentalHealthState, context_updates: dict, crisis_detected: bool) -> str:
    if crisis_detected or intent == "crisis":
        return "CRISIS"
    if intent == "chitchat":
        return "CHITCHAT"
    if intent == "positive_feedback":
        return "RECOVERY"
    if intent in {"accept_technique", "reject_technique", "technique_follow_up", "memory_query"}:
        return "FOLLOW_UP"
    if intent == "technique_preference_update":
        return "RECOVERY"
    flags = state.get("gate_context_flags") or []
    if intent in {"advice_seeking", "technique_request"} and "help_request" in flags:
        return "INTERVENTION"

    slots = _count_context_slots({**state, **context_updates})
    has_prior_stage = state.get("conversation_stage") in {"UNDERSTANDING", "INTERVENTION", "FOLLOW_UP", "RECOVERY"}
    if intent == "contextual_followup" or any(flag in flags for flag in ("asking_opinion", "answering_previous_question", "duration_answer", "subject_answer", "trigger_answer", "short_followup")):
        return "UNDERSTANDING"
    if slots >= 3 or has_prior_stage:
        return "UNDERSTANDING"
    return "DISCOVERY"


def _strategy_for_stage(intent: str, stage: str, needs_technique: bool, current_flags: list[str] | None = None) -> tuple[str, float]:
    current_flags = current_flags or []
    if stage == "CHITCHAT":
        return "no_action", 0.0
    if stage == "CRISIS":
        return "suggest_technique", 0.0
    if (
        intent in {"memory_query", "reject_technique", "technique_preference_update", "positive_feedback"}
        or any(flag in current_flags for flag in ("memory_query", "reject_technique", "preference_update", "positive_feedback"))
    ):
        return "encourage_reflection", 0.0
    if "asking_opinion" in current_flags:
        return "reframe", 0.0
    if intent == "accept_technique":
        return "suggest_technique", 1.0
    if needs_technique:
        return "suggest_technique", 1.0
    if any(flag in current_flags for flag in ("context_complete", "no_more_details", "followup_limit_reached")):
        return "encourage_reflection", 0.0
    if stage in {"DISCOVERY", "UNDERSTANDING"}:
        return "ask_question", 0.0
    if stage == "RECOVERY":
        return "encourage_reflection", 0.2
    return "validate_only", 0.0


def _final_response_task(intent: str, strategy: str, needs_technique: bool, resolver_task: str | None = None, exercise_consent: str = "unknown") -> str:
    """Single response contract consumed by the generator."""
    if resolver_task == "acknowledge_and_pause":
        return "acknowledge_and_pause"
    if intent == "memory_query":
        return "answer_memory_query"
    if intent == "reject_technique":
        return "handle_technique_rejection"
    if intent == "technique_preference_update":
        return "record_preference"
    if intent == "positive_feedback":
        return "positive_feedback"
    if intent == "accept_technique":
        return "continue_active_technique"
    if resolver_task == "give_reflective_opinion":
        return "give_reflective_opinion"
    if needs_technique or strategy == "suggest_technique":
        # v11.0: If consent is unknown and user has not yet accepted, ask permission first
        if exercise_consent == "unknown" and intent not in {"accept_technique", "technique_request"}:
            return "ask_permission_before_technique"
        return "offer_one_technique"
    if resolver_task == "formulate_and_offer_help":
        return "summarize_known_context"
    if strategy == "reframe":
        return resolver_task or "give_reflective_opinion"
    if strategy == "no_action":
        return "chitchat"
    return resolver_task or "ask_next_context_question"


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

    # ============================================
    # v11.0: CONSENT GATE (runs before EVERYTHING else)
    # If the user has denied exercise consent, enforce listen-only mode
    # immediately  no planner logic should override this.
    # Exception: crisis always bypasses consent.
    # ============================================
    exercise_consent = state.get("exercise_consent", "unknown")
    solution_preference = state.get("solution_preference", "unknown")
    _listen_only_mode = (
        (exercise_consent in ("denied_soft", "denied_hard") or solution_preference == "listen_only")
        and not crisis_detected
    )
    if _listen_only_mode:
        print(f"[NODE: PLANNER]  CONSENT GATE  listen-only mode active (exercise_consent={exercise_consent})")

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
            content_text = getattr(m, "content", "")
            lines.append(f"{role}: {content_text}")
        recent_context = "\n".join(lines)

    print(f"\n[NODE: PLANNER]  Planning strategy | Emotion: {emotion} | "
          f"Intensity: {intensity:.0%} | Trend: {trend} | Messages: {user_msg_count}")

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
        src_label = "[GATE authoritative]" if _gate_is_authoritative else "[prefetched]"
        print(f"[NODE: PLANNER]  Using {src_label} intent  skipping LLM call: "
              f"{intent_result['intent']} ({intent_result.get('confidence', 0):.0%}) [saves ~800-1500ms]")
    else:
        # Fallback: gate didn’t run or failed — call llm_intent_check
        from ..llm.llm_classifier import llm_intent_check
        print(f"[NODE: PLANNER]  No prefetch  calling LLM intent classifier...")
        intent_result = await llm_intent_check(current_message, recent_context)

    intent = intent_result.get("intent", "venting")
    intent_confidence = intent_result.get("confidence", 0.0)
    resolver = state.get("resolved_user_act") if isinstance(state.get("resolved_user_act"), dict) else {}
    response_task = state.get("response_task") or ""

    if resolver:
        refined_intent = resolver.get("intent") or intent
        context_flags = list(resolver.get("context_flags") or [])
        referenced_entity = resolver.get("referent") or state.get("latest_referenced_entity")
        slot_updates = resolver.get("slot_updates") or {}
        context_updates = {
            "primary_concern": state.get("primary_concern"),
            "concern_duration": state.get("concern_duration"),
            "triggering_subject": state.get("triggering_subject"),
            "triggering_context": state.get("triggering_context"),
            "functional_impact": state.get("functional_impact"),
            "core_belief": state.get("core_belief"),
        }
        context_updates.update(slot_updates)
        if refined_intent != intent:
            print(f"[NODE: PLANNER]  Resolver intent refinement: {intent} -> {refined_intent}")
        intent = refined_intent
        response_task = resolver.get("response_task") or response_task
    else:
        refined_intent, context_flags, referenced_entity = _classify_contextual_intent(
            current_message, messages, intent
        )
        if refined_intent != intent:
            print(f"[NODE: PLANNER]  Contextual intent refinement: {intent} -> {refined_intent}")
        intent = refined_intent
        context_updates = _derive_context_updates(intent, current_message, state)

    gate_flags = list(state.get("gate_context_flags") or [])
    if not state.get("gate_route") and not resolver:
        # In the production graph, current gate flags arrive with gate_route.
        # Some tests and legacy callers persist old flags in compact context;
        # ignoring them here prevents an old opinion/memory/rejection flag from
        # shaping a later unrelated turn.
        gate_flags = []
    for flag in gate_flags:
        if flag and flag not in context_flags:
            context_flags.append(flag)

    if intent == "technique_follow_up":
        if "reject_technique" in context_flags or "technique_rejection" in context_flags:
            intent = "reject_technique"
            response_task = "handle_technique_rejection"
        elif "accept_technique" in context_flags:
            intent = "accept_technique"
            response_task = "continue_active_technique"
        elif "positive_feedback" in context_flags:
            intent = "positive_feedback"
            response_task = "positive_feedback"
    elif intent == "therapeutic":
        # Keep the public high-level label while letting older deterministic
        # planning rules treat it like the former venting category.
        pass

    # Keep context flags scoped to this turn. Persistent continuity belongs in
    # structured fields such as primary_concern/core_belief, not accumulated
    # flags; stale flags can otherwise make later turns look like old memory
    # queries, opinion asks, or help requests.
    gate_emotional_register = str(state.get("gate_emotional_register") or emotion or "neutral").lower()
    help_requested = "help_request" in context_flags or intent == "technique_request"
    explicit_technique_request = intent == "technique_request" or any(
        signal in current_message for signal in _TECHNIQUE_REQUEST_SIGNALS
    )
    technique_offer_deferred = "technique_offer_deferred" in context_flags
    pending_technique_exists = any(
        isinstance(candidate, dict) and candidate.get("name")
        for candidate in (
            state.get("pending_recommended_technique"),
            state.get("latest_recommended_technique"),
            state.get("active_technique"),
        )
    )
    context_state = {**state, **context_updates}
    primary_sub_emotion = str(context_state.get("primary_sub_emotion") or "").lower()
    context_slots = _count_context_slots(context_state)
    sufficient_context = context_slots >= 2
    explicit_acceptance = intent == "accept_technique"
    expected_answer_type = state.get("expected_answer_type") or resolver.get("expected_answer_type") if resolver else state.get("expected_answer_type")
    question_count_since_technique = int(state.get("question_count_since_technique") or 0)
    context_complete = any(flag in context_flags for flag in ("no_more_details", "context_complete"))
    is_answering_narrow_context_question = any(
        flag in context_flags
        for flag in ("duration_answer", "subject_answer", "trigger_answer", "duration_answer", "subject_or_focus_answer", "body_sensation_answer")
    ) or (expected_answer_type in {"duration", "subject_or_focus", "body_sensation"} and not context_complete)
    is_short_confirmation_or_followup = (
        "short_followup" in context_flags
        and "answering_previous_question" not in context_flags
    )
    has_formulation = bool(context_state.get("core_belief") or context_state.get("functional_impact"))
    enough_dialogue_for_action = (
        user_msg_count >= 3
        and not is_answering_narrow_context_question
        and not is_short_confirmation_or_followup
    )
    slow_paced_concern = _has_slow_paced_concern_context(context_state)
    context_question_limit = (
        MAX_SLOW_PACED_CONTEXT_QUESTIONS_BEFORE_ACTION
        if slow_paced_concern and not explicit_technique_request
        else MAX_CONTEXT_QUESTIONS_BEFORE_ACTION
    )
    followup_limit_reached = (
        question_count_since_technique >= context_question_limit
        and intent == "contextual_followup"
        and not any(flag in context_flags for flag in ("asking_opinion", "memory_query", "reject_technique", "technique_rejection", "positive_feedback", "preference_update"))
        and not is_answering_narrow_context_question
        and not is_short_confirmation_or_followup
        and (sufficient_context or has_formulation)
    )
    should_stop_context_questions = bool(context_complete or followup_limit_reached)
    if followup_limit_reached and "followup_limit_reached" not in context_flags:
        context_flags.append("followup_limit_reached")
    if should_stop_context_questions and "context_complete" not in context_flags:
        context_flags.append("context_complete")

    blocked_for_technique = (
        intent in {"memory_query", "reject_technique", "technique_preference_update", "positive_feedback"}
        or (intent == "contextual_followup" and not should_stop_context_questions and not (help_requested or explicit_technique_request or technique_offer_deferred))
        or any(flag in context_flags for flag in ("asking_opinion", "memory_query", "reject_technique", "technique_rejection", "preference_update", "positive_feedback"))
    )
    earned_intervention = bool(
        enough_dialogue_for_action
        and (question_count_since_technique >= 2 or not resolver)
        and (sufficient_context or has_formulation)
        and not blocked_for_technique
    )
    therapy_action_ready = _has_actionable_therapy_signal(
        emotion=emotion,
        intensity=float(intensity),
        emotional_register=gate_emotional_register,
        context_state=context_state,
        crisis_detected=crisis_detected,
    )
    slow_paced_needs_more_exploration = bool(
        slow_paced_concern
        and not explicit_acceptance
        and not explicit_technique_request
        and not technique_offer_deferred
        and not crisis_detected
        and question_count_since_technique < MAX_SLOW_PACED_CONTEXT_QUESTIONS_BEFORE_ACTION
    )
    needs_technique = bool(
        explicit_acceptance
        or (explicit_technique_request and not blocked_for_technique)
        or (
            therapy_action_ready
            and not slow_paced_needs_more_exploration
            and not (
                primary_sub_emotion in NO_TECHNIQUE_BY_DEFAULT_SUB_EMOTIONS
                and not (help_requested or explicit_technique_request)
            )
            and (
                (help_requested and (sufficient_context or enough_dialogue_for_action))
                or (should_stop_context_questions and (sufficient_context or has_formulation or enough_dialogue_for_action))
                or earned_intervention
            )
            and not blocked_for_technique
        )
    )
    if (
        technique_offer_deferred
        and therapy_action_ready
        and (sufficient_context or has_formulation or pending_technique_exists)
        and exercise_consent != "denied_hard"
        and solution_preference != "listen_only"
    ):
        print("[NODE: PLANNER]  Deferred technique offer: re-asking permission from preserved context")
        needs_technique = True
        response_task = "ask_permission_before_technique"

    # ============================================
    # v11.0: CONTEXT SUFFICIENCY SCORING
    # Blocks technique if we don't have enough formulation yet.
    # Gate: context_sufficiency < 0.6 unless user explicitly requested.
    # slots_found = primary_concern + concern_duration + triggering_context
    # ============================================
    _slots_found = sum(
        1
        for key in ("primary_concern", "concern_duration", "triggering_context")
        if context_updates.get(key) or state.get(key)
    )
    context_sufficiency = min(1.0, round(_slots_found / 3.0, 2))
    if (
        context_sufficiency < 0.6
        and not explicit_acceptance
        and not explicit_technique_request
        and not technique_offer_deferred
        and not should_stop_context_questions
        and not crisis_detected
    ):
        # Not enough context yet — block technique even if therapy_action_ready
        needs_technique = False
        if context_sufficiency < 0.35:
            print(f"[NODE: PLANNER]  context_sufficiency={context_sufficiency:.2f} < 0.35 — needs_technique blocked (not enough formulation)")

    # ============================================
    # v11.0: STALE TOPIC SUPPRESSION (fixed carry-forward bug)
    # Remove any context_update values that the user has flagged as wrong.
    # Also clears from existing state so LangGraph does not carry stale data forward.
    # ============================================
    suppressed_labels = get_suppressed_topic_labels(state)
    if suppressed_labels:
        _ctx_keys_to_guard = (
            "primary_concern", "triggering_subject", "triggering_context",
            "core_belief", "concern_duration", "functional_impact",
        )
        for ctx_key in _ctx_keys_to_guard:
            # Check what the planner computed THIS turn for this key
            new_val = context_updates.get(ctx_key) or ""
            # ALSO check what is already in state (carry-forward from prior turns)
            existing_val = state.get(ctx_key) or ""  # type: ignore[arg-type]

            new_matches = new_val and any(label.lower() in new_val.lower() for label in suppressed_labels)
            existing_matches = existing_val and any(label.lower() in existing_val.lower() for label in suppressed_labels)

            if new_matches:
                print(
                    f"[NODE: PLANNER]  Suppressing NEW stale context '{ctx_key}': "
                    f"'{new_val}' (matches suppressed label)"
                )
                context_updates[ctx_key] = None

            elif existing_matches:
                # The planner didn't touch this key this turn, but the state still
                # holds a stale value.  Force-clear it so LangGraph overwrites it.
                print(
                    f"[NODE: PLANNER]  Clearing EXISTING stale state '{ctx_key}': "
                    f"'{existing_val}' (matches suppressed label)"
                )
                context_updates[ctx_key] = None

    # v11.0: Dialogue readiness recheck gate
    dialogue_solution_turn_count = state.get("dialogue_solution_turn_count", 0)
    user_distress_still_present = (emotion not in ("neutral", "positive", "happy") and intensity >= 0.4)
    recheck_triggered = False

    if (
        dialogue_solution_turn_count >= 3
        and exercise_consent != "denied_hard"
        and solution_preference != "listen_only"
        and context_sufficiency >= 0.65
        and user_distress_still_present
        and not crisis_detected
    ):
        print(
            f"[NODE: PLANNER]  Consent recheck triggered: "
            f"dialogue_solution_turn_count={dialogue_solution_turn_count}, "
            f"context_sufficiency={context_sufficiency:.2f}"
        )
        response_task = "ask_permission_before_technique"
        needs_technique = True
        recheck_triggered = True

    if _listen_only_mode and not recheck_triggered:
        if needs_technique:
            print(f"[NODE: PLANNER]  CONSENT GATE  forcing needs_technique=False (exercise_consent={exercise_consent})")
            needs_technique = False
        
        # v11.0: Dialogue-based Solutions Routing
        # If the user has denied formal exercises but seeks advice, or they have vented enough
        # (context_sufficiency >= 0.6), transition them to conversational solutions / reframings
        # instead of asking yet another context gathering question.
        if (solution_preference == "advice_allowed" or context_sufficiency >= 0.6) and response_task == "ask_next_context_question":
            print(
                f"[NODE: PLANNER]  CONSENT GATE  exercises blocked but context is sufficient ({context_sufficiency}) "
                f"or advice is allowed ({solution_preference}) → routing response_task to 'give_reflective_opinion' (verbal solution)"
            )
            response_task = "give_reflective_opinion"

    if explicit_technique_request and "explicit_technique_request" not in context_flags:
        context_flags.append("explicit_technique_request")
    if slow_paced_needs_more_exploration and "slow_paced_concern" not in context_flags:
        context_flags.append("slow_paced_concern")
    if therapy_action_ready and needs_technique and "therapeutic_action_ready" not in context_flags:
        context_flags.append("therapeutic_action_ready")

    if should_stop_context_questions and not needs_technique and response_task == "ask_next_context_question":
        response_task = "summarize_known_context"
    elif should_stop_context_questions and not response_task:
        response_task = "formulate_and_offer_help"

    merged_flags = []
    for flag in context_flags:
        if flag and flag not in merged_flags:
            merged_flags.append(flag)

    # Stage decisions should use this turn's flags. Accumulated flags are kept
    # for memory/debugging only; using them here makes stale events like an old
    # memory query or help request affect unrelated later turns.
    stage = _stage_from_context(intent, {**state, "gate_context_flags": context_flags}, context_updates, crisis_detected)
    if help_requested and not needs_technique and stage == "INTERVENTION":
        stage = "UNDERSTANDING"
    if should_stop_context_questions and needs_technique:
        stage = "INTERVENTION"
    elif needs_technique and stage not in {"FOLLOW_UP", "CRISIS"}:
        stage = "INTERVENTION"

    if _listen_only_mode:
        if needs_technique:
            print("[NODE: PLANNER]  CONSENT GATE  final guard cleared needs_technique")
        needs_technique = False
        if stage == "INTERVENTION":
            stage = "UNDERSTANDING"
        if solution_preference == "listen_only":
            response_task = "listen_only"
        elif solution_preference == "advice_allowed" or should_stop_context_questions:
            response_task = "give_reflective_opinion"

    compact_analysis = {
        "intent": intent,
        "conversation_stage": stage.lower(),
        "emotion": emotion,
        "intensity": float(intensity),
        "strategy": (
            "handle_rejection" if intent == "reject_technique"
            else "answer_context" if response_task == "give_reflective_opinion"
            else "continue_technique" if intent == "accept_technique"
            else "summarize" if should_stop_context_questions and not needs_technique
            else "summarize" if intent == "positive_feedback"
            else "suggest_technique" if needs_technique
            else "ask_context_question"
        ),
        "needs_technique": needs_technique,
        "role": "coach",
        "context_flags": merged_flags,
        "referenced_entity": referenced_entity,
        "memory_reference": "technique" if intent == "memory_query" else None,
        "response_task": response_task,
        "expected_answer_type": expected_answer_type,
        # v11.0: consent governance fields
        "exercise_consent": exercise_consent,
        "solution_preference": solution_preference,
        "suppressed_topics": suppressed_labels if suppressed_labels else [],
        "context_sufficiency": context_sufficiency,
    }
    print(f"[NODE: PLANNER]  Compact analysis: {compact_analysis}")

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
            print(f"[NODE: PLANNER] Gate is authoritative chitchat - no_action fast-path "
                  f"(gate_conf={intent_confidence:.0%}, emotion override: {emotion})")
            return {
                "conversation_strategy": "no_action",
                "conversation_phase": "neutral",
                "conversation_stage": "CHITCHAT",
                "needs_technique": False,
                "intent": intent,
                "gate_context_flags": merged_flags,
                "gate_emotional_register": gate_emotional_register,
                "gate_intensity_hint": float(intensity),
                "latest_referenced_entity": referenced_entity,
                "response_task": "chitchat",
                "resolved_user_act": resolver or None,
                "compact_analysis": compact_analysis,
                "technique_readiness": 0.0,
                "crisis_detected": False,
                "session_message_count": user_msg_count,
                "recommended_techniques_by_category": {},
                **context_updates,
            }
        # High-confidence chitchat from internal llm_intent_check — apply threshold
        # Emotion models can misread short factual corrections ('im not taram', 'no thanks')
        # as distress. The LLM intent signal is far more reliable for these cases.
        if intent_confidence >= 0.70 or (emotion == "neutral" and intensity < _NEUTRAL_INTENSITY_THRESHOLD):
            print(f"[NODE: PLANNER]  Chitchat intent ({intent_confidence:.0%})  no_action fast-path (emotion override: {emotion})")
            return {
                "conversation_strategy": "no_action",
                "conversation_phase": "neutral",
                "conversation_stage": "CHITCHAT",
                "needs_technique": False,
                "intent": intent,
                "gate_context_flags": merged_flags,
                "gate_emotional_register": gate_emotional_register,
                "gate_intensity_hint": float(intensity),
                "latest_referenced_entity": referenced_entity,
                "response_task": "chitchat",
                "resolved_user_act": resolver or None,
                "compact_analysis": compact_analysis,
                "technique_readiness": 0.0,
                "crisis_detected": False,
                "session_message_count": user_msg_count,
                "recommended_techniques_by_category": {},
                **context_updates,
            }

    if context_flags or needs_technique or intent in {
        "memory_query", "reject_technique", "technique_preference_update", "accept_technique",
    }:
        strategy, readiness = _strategy_for_stage(intent, stage, needs_technique, context_flags)
        phase = _STAGE_TO_PHASE.get(stage, "venting")
        print(f"[NODE: PLANNER]  Stage machine override | Stage={stage} | Intent={intent} | Strategy={strategy} | needs_technique={needs_technique}")
        return {
            "conversation_strategy": strategy,
            "conversation_phase": phase,
            "conversation_stage": stage,
            "technique_readiness": readiness,
            "needs_technique": needs_technique,
            "intent": intent,
            "crisis_detected": crisis_detected,
            "session_message_count": user_msg_count,
            "gate_context_flags": merged_flags,
            "gate_emotional_register": gate_emotional_register,
            "gate_intensity_hint": float(intensity),
            "latest_referenced_entity": referenced_entity,
            "response_task": _final_response_task(intent, strategy, needs_technique, response_task, exercise_consent=exercise_consent),
            "resolved_user_act": resolver or None,
            "compact_analysis": compact_analysis,
            "context_sufficiency": context_sufficiency,
            **context_updates,
        }

    # ============================================
    # High-confidence intent overrides
    # ============================================
    if intent == "technique_request" and intent_confidence >= 0.65:
        if not needs_technique:
            print(f"[NODE: PLANNER]  LLM detected technique request ({intent_confidence:.0%})  ask_question first (insufficient formulation)")
            return {
                "conversation_strategy": "ask_question",
                "conversation_phase": state.get("conversation_phase", "venting"),
                "conversation_stage": "UNDERSTANDING",
                "technique_readiness": 0.3,
                "needs_technique": False,
                "intent": "technique_request",
                "crisis_detected": False,
                "session_message_count": user_msg_count,
                "gate_context_flags": merged_flags,
                "gate_emotional_register": gate_emotional_register,
                "gate_intensity_hint": float(intensity),
                "latest_referenced_entity": referenced_entity,
                "response_task": _final_response_task("technique_request", "ask_question", False, response_task),
                "resolved_user_act": resolver or None,
                "compact_analysis": compact_analysis,
                **context_updates,
            }

        print(f"[NODE: PLANNER]  LLM detected technique request ({intent_confidence:.0%})  suggest_technique")
        return {
            "conversation_strategy": "suggest_technique",
            "conversation_phase": state.get("conversation_phase", "venting"),
            "conversation_stage": "INTERVENTION",
            "technique_readiness": 1.0,
            "needs_technique": True,
            "intent": "technique_request",
            "crisis_detected": False,
            "session_message_count": user_msg_count,
            "gate_context_flags": merged_flags,
            "gate_emotional_register": gate_emotional_register,
            "gate_intensity_hint": float(intensity),
            "latest_referenced_entity": referenced_entity,
            "response_task": "offer_one_technique",
                "resolved_user_act": resolver or None,
                "compact_analysis": compact_analysis,
            **context_updates,
        }

    # Advice-seeking: user wants guidance, not an exercise  validate and advise conversationally
    if intent == "advice_seeking" and intent_confidence >= 0.60:
        print(f"[NODE: PLANNER]  LLM detected advice_seeking ({intent_confidence:.0%})  ask_question (understand before acting)")
        return {
            "conversation_strategy": "ask_question",
            "conversation_phase": state.get("conversation_phase", "venting"),
            "conversation_stage": "UNDERSTANDING",
            "technique_readiness": 0.3,
            "needs_technique": False,
            "intent": intent,
            "crisis_detected": False,
            "session_message_count": user_msg_count,
            "gate_context_flags": merged_flags,
                "gate_emotional_register": gate_emotional_register,
            "gate_intensity_hint": float(intensity),
            "latest_referenced_entity": referenced_entity,
            "response_task": _final_response_task(intent, "ask_question", False, response_task),
            "resolved_user_act": resolver or None,
            "compact_analysis": compact_analysis,
            **context_updates,
        }

    # High-confidence crisis signal from intent  flag for router
    if intent == "crisis_signal" and intent_confidence >= 0.65:
        print(f"[NODE: PLANNER]  LLM detected crisis signal in planner ({intent_confidence:.0%})")
        return {
            "conversation_strategy": "suggest_technique",
            "conversation_phase": state.get("conversation_phase", "venting"),
            "conversation_stage": "CRISIS",
            "technique_readiness": 1.0,
            "needs_technique": False,
            "intent": "crisis",
            "crisis_detected": True,
            "session_message_count": user_msg_count,
            "gate_context_flags": merged_flags,
            "gate_emotional_register": gate_emotional_register,
            "gate_intensity_hint": float(intensity),
            "latest_referenced_entity": referenced_entity,
            "response_task": "crisis_support",
            "resolved_user_act": resolver or None,
            "compact_analysis": compact_analysis,
            **context_updates,
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
            print(f"[NODE: PLANNER] Clinical override: SEVERE severity -> suggest_technique (with professional referral)")

        # MODERATELY SEVERE + moderate+ intensity → push technique earlier
        elif clinical_severity == "moderately_severe" and intensity >= 0.5:
            strategy = "suggest_technique"
            print(f"[NODE: PLANNER] Clinical override: MODERATELY_SEVERE + intensity={intensity:.0%} -> suggest_technique")

        # MINIMAL + low intensity → don't push, just validate
        elif clinical_severity == "minimal" and intensity < 0.3 and emotion not in _RECOVERY_POSITIVE_EMOTIONS:
            strategy = "validate_only"
            print(f"[NODE: PLANNER] Clinical override: MINIMAL severity + low intensity -> validate_only")

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
    stage = _stage_from_context(intent, {**state, "gate_context_flags": context_flags}, context_updates, crisis_detected)
    if help_requested and not needs_technique and stage == "INTERVENTION":
        stage = "UNDERSTANDING"
    if strategy == "suggest_technique":
        if explicit_acceptance or explicit_technique_request or (help_requested and (sufficient_context or enough_dialogue_for_action)) or earned_intervention:
            needs_technique = True
            stage = "INTERVENTION" if stage not in {"CRISIS", "FOLLOW_UP"} else stage
        else:
            strategy = "ask_question" if stage in {"DISCOVERY", "UNDERSTANDING"} else "encourage_reflection"
            needs_technique = False
            print("[NODE: PLANNER]  Technique readiness deferred - no explicit request/acceptance yet")
    elif stage in {"DISCOVERY", "UNDERSTANDING"}:
        needs_technique = False

    if _listen_only_mode:
        if needs_technique or strategy == "suggest_technique":
            print("[NODE: PLANNER]  CONSENT GATE  legacy final guard blocked technique strategy")
        needs_technique = False
        if strategy == "suggest_technique":
            strategy = "reframe" if solution_preference == "advice_allowed" else "validate_only"
        if stage == "INTERVENTION":
            stage = "UNDERSTANDING"
        if solution_preference == "listen_only":
            response_task = "listen_only"
        elif solution_preference == "advice_allowed" or response_task == "ask_next_context_question":
            response_task = "give_reflective_opinion"

    return {
        "conversation_strategy": strategy,
        "conversation_phase": phase,
        "conversation_stage": stage,
        "technique_readiness": readiness,
        "needs_technique": needs_technique,
        "intent": intent,
        "crisis_detected": crisis_detected, # Pass through existing state or overrides
        "session_message_count": user_msg_count,
        "gate_context_flags": merged_flags,
        "gate_emotional_register": gate_emotional_register,
        "gate_intensity_hint": float(intensity),
        "latest_referenced_entity": referenced_entity,
        "response_task": _final_response_task(intent, strategy, needs_technique, response_task, exercise_consent=exercise_consent),
        "resolved_user_act": resolver or None,
        "compact_analysis": compact_analysis,
        **context_updates,
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
