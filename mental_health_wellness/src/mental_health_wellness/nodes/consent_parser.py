"""
Consent & Suppression Parser — SentiMind v11.0

PURPOSE:
  Pure-Python, zero-LLM node that scans the current user message for:
    1. Exercise/intervention DENIAL signals
       → exercise_consent = "denied", solution_preference = "listen_only"
    2. Exercise/intervention ACCEPTANCE signals (only when a technique was pending)
       → exercise_consent = "allowed", solution_preference = "exercise_requested"
    3. "Just want to talk / advice only" signals
       → solution_preference = "listen_only" or "advice_allowed"
    4. Topic CORRECTION signals ("that's not the reason", "not because of X")
       → appends to suppressed_topics, sets active_issue_source

DESIGN:
  - Runs inside run_analysis_and_planning() between emotion fusion and the planner.
  - Returns only the fields that actually changed (sparse update).
  - Session-scoped: consent & suppression live in state only; NOT persisted to DB.
  - Strong language like "I never want exercises" triggers a persistent UserPreference
    write via an optional background task.

OUTPUTS (partial state dict — only changed fields):
  exercise_consent    : str   ("unknown" | "denied" | "allowed")
  solution_preference : str   ("unknown" | "listen_only" | "advice_allowed" | "exercise_requested")
  suppressed_topics   : list  (appended, not overwritten)
  active_issue_source : str | None
"""

import re
from ..agent.state import MentalHealthState
from ..utils.turn_signals import (
    has_negative_feedback_signal,
    has_positive_outcome_signal,
    is_no_thanks,
    is_technique_acceptance_reply,
)

# ============================================
# DENIAL SIGNALS — user refuses exercises
# ============================================
_EXERCISE_DENIAL_PHRASES = {
    # Direct refusals
    "don't want exercises", "dont want exercises",
    "no exercises", "not exercises",
    "no breathing exercise", "not breathing",
    "no meditation", "don't want meditation", "dont want meditation",
    "no coping techniques", "don't want techniques", "dont want techniques",
    "no therapy exercises", "no cbt",
    "don't want to do exercises", "dont want to do exercises",
    "not interested in exercises", "not interested in techniques",
    "i don't want that", "i dont want that",
    "skip the exercises", "skip exercises",
    "no exercise please", "not today for exercises",
    "pass on the exercises", "pass on exercises",
    # Just want to talk / vent
    "just want to talk", "just wanna talk",
    "just want to vent", "just wanna vent",
    "just want to be heard", "just wanna be heard",
    "just listen", "just listen to me",
    "just want you to listen", "just wanna hear",
    "don't give me advice", "dont give me advice",
    "no advice", "not looking for advice",
    "i'm not looking for solutions", "im not looking for solutions",
    "don't want solutions", "dont want solutions",
    "i just need to talk", "i just need someone to listen",
    "not ready for exercises", "not ready for techniques",
    "don't push me", "dont push me",
}

# ============================================
# SOFT AND HARD DENIAL PHRASES (for granular consent checks)
# ============================================
_SOFT_DENIAL_PHRASES = {
    "not now", "just for now", "not ready", "not ready for exercises", "not ready for techniques",
    "not today", "pass on the exercises", "pass on exercises", "skip the exercises", "skip exercises",
    "maybe later", "later", "not right now", "just listen for now", "skip exercises for now",
    "no thanks", "no thank you", "nah thanks", "no thx",
}

_EXERCISE_CONTEXT_TERMS = {
    "exercise", "exercises", "technique", "techniques", "breathing", "meditation",
    "grounding", "relaxation", "practice", "cbt", "coping", "solution", "solutions",
}

_HARD_DENIAL_PHRASES = {
    "never want exercises", "never want to do exercises", "never suggest", "dont suggest", "don't suggest",
    "i hate exercises", "hate exercises", "no exercises", "stop pushing", "no therapy exercises", "no cbt",
    "don't want exercises", "dont want exercises", "don't want to do exercises", "dont want to do exercises",
    "never exercises", "don't suggest anything", "dont suggest anything",
}


# ============================================
# EXPLICIT ACCEPTANCE SIGNALS
# ============================================
_EXERCISE_ACCEPTANCE_PHRASES = {
    "yes", "yeah", "yep",
    "yes please", "yes, please",
    "yes sure", "sure", "sure, let's try", "sure let's try",
    "let's try", "lets try",
    "i'd like to try", "id like to try",
    "let's do this", "lets do this",
    "guide me", "walk me through",
    "teach me", "show me",
    "yes i want to try", "yes, i want to try",
    "ok let's do it", "ok lets do it",
    "alright let's try", "alright lets try",
    "go ahead", "please share it",
    "yes, share it", "yes share it",
    "yes, guide me", "yes guide me",
}

# ============================================
# LISTEN-ONLY / ADVICE SIGNALS
# ============================================
_LISTEN_ONLY_PHRASES = {
    "just listen", "just want to talk", "just wanna talk",
    "only want to talk", "i only want to talk",
    "just want to vent", "just wanna vent",
    "just need to talk", "just need someone to listen",
    "just want to be heard", "just wanna be heard",
    "only want you to listen", "i only want you to listen",
    "please just listen",
    "don't give me advice", "dont give me advice",
    "no advice please", "not looking for advice",
    "don't need advice", "dont need advice",
    "i don't need solutions", "i dont need solutions",
}

_ADVICE_ALLOWED_PHRASES = {
    "what should i do", "what can i do",
    "any advice", "any suggestions",
    "can you help me", "what do you suggest",
    "give me advice", "tell me what to do",
    "what do you recommend", "how do i handle",
}

# ============================================
# NEVER / PERMANENT DENIAL — triggers DB write
# ============================================
_PERMANENT_DENIAL_PHRASES = {
    "i never want exercises", "i never want to do exercises",
    "i always hate exercises", "exercises never help me",
    "i hate all exercises", "exercises don't work for me",
    "exercises never work", "i'm against exercises",
}

# ============================================
# TOPIC CORRECTION SIGNALS
# ============================================
_TOPIC_CORRECTION_PHRASES = [
    "that's not the reason",
    "thats not the reason",
    "not because of",
    "nothing to do with",
    "has nothing to do with",
    "have nothing to do with",
    "not about my",
    "it's not about",
    "its not about",
    "this is different",
    "that was different",
    "i told you before",
    "i already said",
    "i corrected you",
    "stop bringing up",
    "forget about",
    "not related to",
    "unrelated to",
    "different from what",
    "not what i said",
    "misunderstood",
    "not what i meant",
]

# Patterns that follow a correction — capture the new topic
_NEW_TOPIC_PATTERNS = [
    r"it['']?s (?:about|because of|due to) (.+?)(?:\.|$)",
    r"this is (?:about|because of|due to) (.+?)(?:\.|$)",
    r"the reason is (.+?)(?:\.|$)",
    r"actually (?:it['']?s |this is )(.+?)(?:\.|$)",
    r"the real (?:reason|issue|problem) is (.+?)(?:\.|$)",
    r"it has (?:to do with|everything to do with) (.+?)(?:\.|$)",
]


def _plain(text: str) -> str:
    """Lowercase + strip punctuation for phrase matching."""
    return re.sub(r"[^\w\s]", " ", (text or "").lower()).strip()


def _contains_any(text_lower: str, phrases: set) -> bool:
    return any(phrase in text_lower for phrase in phrases)


def _has_exercise_context(text_lower: str) -> bool:
    """True when a short refusal is clearly about interventions/exercises."""
    words = set(text_lower.split())
    return bool(words & _EXERCISE_CONTEXT_TERMS)


def _extract_new_topic(text_lower: str) -> str | None:
    """Try to extract what the user says IS the real issue after a correction."""
    for pattern in _NEW_TOPIC_PATTERNS:
        m = re.search(pattern, text_lower)
        if m:
            topic = m.group(1).strip()
            if topic:
                return topic[:120]  # cap length
    return None


def parse_consent_and_suppression(state: MentalHealthState) -> dict:
    """
    Scan the latest user message for consent and correction signals.

    Returns a *sparse* dict with only the fields that changed.
    Merge this into the pipeline state before the planner runs.

    Does NOT overwrite already-decided values unless a new signal is found:
      - Once exercise_consent = "denied", it stays denied for the whole session.
      - Once exercise_consent = "allowed", it stays allowed unless the user later denies.
    """
    messages = state.get("messages", [])
    if not messages:
        return {}

    current_message = (getattr(messages[-1], "content", "") or "").strip()
    if not current_message:
        return {}

    lower = current_message.lower()
    plain_lower = _plain(current_message)

    # Current state values
    exercise_consent = state.get("exercise_consent", "unknown")
    solution_preference = state.get("solution_preference", "unknown")
    suppressed_topics: list = list(state.get("suppressed_topics") or [])
    active_issue_source = state.get("active_issue_source")
    session_msg_count = max(
        state.get("session_message_count", 0),
        sum(1 for m in messages if getattr(m, "type", "") == "human"),
    )

    # A technique offer is "pending" if the latest AI turn offered one or the
    # committed session state says the previous assistant question expected a
    # technique-acceptance answer.
    expected_answer_type = state.get("expected_answer_type")
    response_task = state.get("response_task")
    last_assistant_act = state.get("last_assistant_act")
    technique_was_offered = bool(
        expected_answer_type == "technique_acceptance"
        or response_task == "ask_permission_before_technique"
        or last_assistant_act == "ask_permission_before_technique"
    )
    for m in reversed(messages[:-1]):
        if getattr(m, "type", "") == "ai":
            ai_text = (getattr(m, "content", "") or "").lower()
            if any(kw in ai_text for kw in (
                "would you like to try", "shall we try", "want to give it a try",
                "would you like to give", "i can share something",
                "i'd like to share", "i have something that might help",
                "would you like me to share", "like me to share it",
            )):
                technique_was_offered = True
            break

    updates: dict = {}

    # Seed persistent preference "never_exercises" from database if current session consent is unknown
    user_prefs = state.get("user_preferences") or {}
    comm_style = user_prefs.get("communicationStyle") or ""
    if "never_exercises" in comm_style and exercise_consent == "unknown":
        print(f"[CONSENT_PARSER]  Persistent 'never_exercises' preference loaded from DB → setting exercise_consent=denied_hard")
        exercise_consent = "denied_hard"
        solution_preference = "listen_only"
        updates["exercise_consent"] = "denied_hard"
        updates["solution_preference"] = "listen_only"

    # -------------------------------------------------------
    # 1. PERMANENT / HARD DENIAL → also write to UserPreference (background)
    # -------------------------------------------------------
    if _contains_any(lower, _PERMANENT_DENIAL_PHRASES) or _contains_any(plain_lower, _HARD_DENIAL_PHRASES):
        print(f"[CONSENT_PARSER]  HARD/PERMANENT denial detected → exercise_consent=denied_hard")
        updates["exercise_consent"] = "denied_hard"
        updates["solution_preference"] = "listen_only"
        _schedule_preference_write(state, "never_exercises")

    # -------------------------------------------------------
    # 2. SESSION DENIAL (exercise refusal)
    # -------------------------------------------------------
    elif _contains_any(plain_lower, _EXERCISE_DENIAL_PHRASES) or (
        _contains_any(plain_lower, _SOFT_DENIAL_PHRASES)
        and (technique_was_offered or _has_exercise_context(plain_lower))
    ):
        if exercise_consent not in ("denied_soft", "denied_hard"):
            print(f"[CONSENT_PARSER]  Soft exercise denial detected → exercise_consent=denied_soft")
            updates["exercise_consent"] = "denied_soft"
        if solution_preference not in ("listen_only", "advice_allowed"):
            updates["solution_preference"] = (
                "advice_allowed"
                if _contains_any(plain_lower, _ADVICE_ALLOWED_PHRASES)
                and not _contains_any(plain_lower, _LISTEN_ONLY_PHRASES)
                else "listen_only"
            )

    # -------------------------------------------------------
    # 3. ACCEPTANCE (only when a technique offer was pending)
    # -------------------------------------------------------
    elif (
        technique_was_offered
        and is_technique_acceptance_reply(current_message)
        and not is_no_thanks(current_message)
        and not has_positive_outcome_signal(current_message)
        and not has_negative_feedback_signal(current_message)
    ):
        if exercise_consent != "allowed":
            print(f"[CONSENT_PARSER]  Exercise acceptance detected → exercise_consent=allowed")
            updates["exercise_consent"] = "allowed"
            updates["solution_preference"] = "exercise_requested"

    # -------------------------------------------------------
    # 4. LISTEN-ONLY (no explicit exercise denial, but "just listen")
    # -------------------------------------------------------
    if not updates.get("solution_preference"):
        if _contains_any(plain_lower, _LISTEN_ONLY_PHRASES):
            updates["solution_preference"] = "listen_only"
            if exercise_consent == "unknown":
                updates["exercise_consent"] = "denied_soft"
            print(f"[CONSENT_PARSER]  Listen-only signal detected → solution_preference=listen_only")

        elif _contains_any(plain_lower, _ADVICE_ALLOWED_PHRASES):
            if solution_preference == "unknown":
                updates["solution_preference"] = "advice_allowed"
                print(f"[CONSENT_PARSER]  Advice-seeking signal → solution_preference=advice_allowed")

    # -------------------------------------------------------
    # 5. TOPIC CORRECTION (stale memory suppression)
    # -------------------------------------------------------
    correction_found = _contains_any(lower, set(_TOPIC_CORRECTION_PHRASES))
    if correction_found:
        # Try to identify what topic is being corrected
        # Heuristic: find the person/thing being denied
        suppressed_label = _extract_suppressed_topic(lower)
        new_topic = _extract_new_topic(lower)

        if suppressed_label:
            existing_labels = {t.get("topic", "") for t in suppressed_topics}
            if suppressed_label not in existing_labels:
                suppressed_topics.append({
                    "topic": suppressed_label,
                    "reason": f"User said: \"{current_message[:120]}\"",
                    "turn": session_msg_count,
                })
                updates["suppressed_topics"] = suppressed_topics
                print(f"[CONSENT_PARSER]  Topic suppressed: '{suppressed_label}'")

        if new_topic and new_topic != active_issue_source:
            updates["active_issue_source"] = new_topic
            print(f"[CONSENT_PARSER]  Active issue source updated: '{new_topic}'")
        elif not new_topic and correction_found:
            print(f"[CONSENT_PARSER]  Correction detected but could not extract new topic — planner will re-ask")

    if updates:
        print(f"[CONSENT_PARSER]  Updates: {list(updates.keys())}")
    else:
        print(f"[CONSENT_PARSER]  No consent/suppression signals in this turn")

    return updates


def _extract_suppressed_topic(text_lower: str) -> str | None:
    """
    Try to extract the name/label of the topic being denied.
    Examples:
      "that has nothing to do with my brother" → "brother"
      "it's not because of the teacher" → "teacher"
      "not related to uncle" → "uncle"
    """
    patterns = [
        r"nothing to do with (?:my )?([\w\s]{2,30}?)(?:\.|,|$)",
        r"not because of (?:my )?([\w\s]{2,30}?)(?:\.|,|$)",
        r"not about (?:my )?([\w\s]{2,30}?)(?:\.|,|$)",
        r"has nothing to do with (?:my )?([\w\s]{2,30}?)(?:\.|,|$)",
        r"stop bringing up (?:my )?([\w\s]{2,30}?)(?:\.|,|$)",
        r"forget about (?:my )?([\w\s]{2,30}?)(?:\.|,|$)",
        r"not related to (?:my )?([\w\s]{2,30}?)(?:\.|,|$)",
        r"unrelated to (?:my )?([\w\s]{2,30}?)(?:\.|,|$)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text_lower)
        if m:
            label = m.group(1).strip().rstrip("., ")
            if label and len(label) >= 2:
                return label[:60]
    return None


def _schedule_preference_write(state: MentalHealthState, preference_key: str) -> None:
    """
    Optionally persist a strong permanent preference to UserPreference in the DB.
    Runs as a fire-and-forget background task — non-blocking.
    Only executes if the background LLM / DB pipeline is enabled.
    """
    import os
    import asyncio

    if os.getenv("SENTIMIND_BACKGROUND_LLM_ENABLED", "0").lower() not in {"1", "true", "yes", "on"}:
        return

    user_id = state.get("user_id", "")
    if not user_id:
        return

    async def _write():
        try:
            from ..db.client import get_prisma_client
            prisma = await get_prisma_client()
            # Store as a JSON blob in the existingPreferences or a simple notes field.
            # We use communicationStyle as a safe carrier field since no strict schema
            # change is needed — the string is prefixed for disambiguation.
            pref = await prisma.userpreference.find_unique(where={"userId": user_id})
            if pref:
                current_style = pref.communicationStyle or ""
                if "never_exercises" not in current_style:
                    await prisma.userpreference.update(
                        where={"userId": user_id},
                        data={"communicationStyle": f"{current_style};never_exercises".strip(";")},
                    )
                    print(f"[CONSENT_PARSER]  Persistent preference 'never_exercises' written for {user_id[:12]}...")
            else:
                await prisma.userpreference.create(data={
                    "userId": user_id,
                    "communicationStyle": "never_exercises",
                })
                print(f"[CONSENT_PARSER]  Created UserPreference with 'never_exercises' for {user_id[:12]}...")
        except Exception as e:
            print(f"[CONSENT_PARSER]  Preference DB write failed (non-fatal): {str(e)[:80]}")

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(_write())
    except Exception:
        pass


def get_suppressed_topic_labels(state: MentalHealthState) -> list[str]:
    """
    Returns a flat list of suppressed topic label strings.
    Used by the planner and response generator to filter stale context.
    """
    return [
        t.get("topic", "")
        for t in (state.get("suppressed_topics") or [])
        if t.get("topic")
    ]
