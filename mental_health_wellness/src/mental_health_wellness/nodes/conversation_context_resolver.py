"""
Conversation Context Resolver - same-session reference resolution.

This is the small architectural layer between intake and planning. It answers:

    "What does this user message mean in relation to the current thread?"

It does not add narrow topic-specific intents. Instead it uses the previous
assistant question, expected answer type, active concern, and technique state to
resolve short replies, pronouns, acceptances, rejections, and memory queries.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

from ..agent.state import MentalHealthState
from ..utils.turn_signals import (
    assistant_likely_gave_steps,
    assistant_offered_technique,
    has_negative_feedback_signal,
    has_positive_outcome_signal,
    is_bare_affirmation,
    is_no_thanks,
    is_polite_acknowledgement,
    is_technique_acceptance_reply,
)


_context_logger = logging.getLogger("sentimind.context")

_CONTEXT_KEYS = (
    "primary_concern",
    "concern_duration",
    "triggering_subject",
    "triggering_context",
    "functional_impact",
    "core_belief",
)


def _message_text(message) -> str:
    return (getattr(message, "content", "") or "").strip()


def _current_message(state: MentalHealthState) -> str:
    messages = state.get("messages") or []
    return _message_text(messages[-1]) if messages else ""


def _last_assistant_text(messages: list) -> str:
    for message in reversed(messages[:-1]):
        if getattr(message, "type", "") == "ai":
            return _message_text(message)
    return ""


def _short_text(text: str, max_words: int = 8) -> bool:
    words = re.findall(r"\w+", text or "")
    return 0 < len(words) <= max_words


def _normal(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _plain(text: str) -> str:
    return re.sub(r"[^\w\s]", "", _normal(text)).strip()


def _looks_like_no_more_details(text: str) -> bool:
    """Detect when the user is explicitly done adding context."""
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


def _debug_context_enabled() -> bool:
    return os.getenv("SENTIMIND_DEBUG_CONTEXT", "0").lower() in {"1", "true", "yes"}


def _clip(value, limit: int = 260) -> str:
    text = str(value or "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _debug_print_resolver_context(
    *,
    current: str,
    previous_question: Optional[str],
    expected_answer_type: Optional[str],
    active_thread: Optional[str],
    resolved: dict,
) -> None:
    if not _debug_context_enabled():
        return

    checks = {
        "previous_question_available": bool(previous_question),
        "expected_answer_type_available": bool(expected_answer_type),
        "active_thread_available": bool(active_thread or resolved.get("active_thread_summary")),
        "slot_updates_available": bool(resolved.get("slot_updates")),
        "response_task_available": bool(resolved.get("response_task")),
    }
    verdict = "PASS" if checks["response_task_available"] and (
        checks["previous_question_available"] or checks["active_thread_available"]
    ) else "WARN"

    _context_logger.info("Context Resolver | %s", verdict)
    _context_logger.info("  checks: %s", checks)
    _context_logger.info("  current_user: %s", _clip(current) or "none")
    _context_logger.info("  previous_question: %s", _clip(previous_question) or "none")
    _context_logger.info("  expected_answer_type: %s", expected_answer_type or "none")
    _context_logger.info("  active_thread: %s", _clip(active_thread) or "none")
    _context_logger.info(
        "  resolved: act=%s | intent=%s | task=%s",
        resolved.get("user_act"),
        resolved.get("intent"),
        resolved.get("response_task"),
    )
    _context_logger.info("  flags: %s", resolved.get("context_flags"))
    _context_logger.info("  slot_updates: %s", resolved.get("slot_updates"))


def extract_last_question(text: str) -> Optional[str]:
    """Return the final question in an assistant response, if one exists."""
    if not text or "?" not in text:
        return None
    compact = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
    question_end = compact.rfind("?")
    if question_end == -1:
        return None

    prefix = compact[: question_end + 1]
    starts = [prefix.rfind(mark) for mark in (". ", "! ", "? ")]
    start = max(starts)
    question = prefix[start + 2 :] if start != -1 else prefix
    question = question.strip()
    if len(question) > 300:
        question = question[-300:].lstrip()
    return question or None


def infer_expected_answer_type(question: Optional[str]) -> Optional[str]:
    """Infer the slot a future short answer is likely filling."""
    if not question:
        return None

    q = _normal(question)

    if any(p in q for p in ("would you like", "would you be open", "give it a try", "try it together", "explore that together")):
        return "technique_acceptance"
    if any(p in q for p in ("how long", "since when", "when did", "how many days", "how many weeks", "for how long")):
        return "duration"
    if any(p in q for p in ("what part", "which part", "feels most painful", "hurts the most", "hardest part")):
        return "pain_point"
    if any(p in q for p in ("what subject", "which subject", "what topic", "which topic", "what area", "which area")):
        return "subject_or_focus"
    if any(p in q for p in ("where do you feel", "in your body", "physically", "body feel", "feel it mostly")):
        return "body_sensation"
    if any(p in q for p in ("what happens", "what do you notice happens", "affect", "impact", "get done", "focus", "sleep", "study", "work")):
        return "functional_impact"
    if any(p in q for p in ("going through your mind", "what are you thinking", "tell yourself", "belief", "thought shows up")):
        return "core_belief"
    if any(p in q for p in ("what would help", "what do you need", "support you right now", "help right now")):
        return "support_need"
    if any(p in q for p in ("what would they appreciate", "what would you want", "what matters most", "what feels important")):
        return "meaning_or_evidence"

    return "context_detail"


def _latest_technique(state: MentalHealthState) -> dict:
    active = state.get("active_technique") or {}
    if isinstance(active, dict) and active.get("name"):
        return active
    latest = state.get("latest_recommended_technique") or {}
    return latest if isinstance(latest, dict) else {}


def _looks_like_distress(text: str) -> bool:
    lower = _normal(text)
    return any(
        marker in lower
        for marker in (
            "anxious", "anxiety", "worried", "stress", "stressed", "sad",
            "heavy", "tired", "drained", "overwhelmed", "not good",
            "not okay", "not ok", "panic", "fear", "scared", "guilty",
            "guilt", "shut down", "worthless", "hopeless",
        )
    )


def _compact_concern(text: str) -> str:
    clean = re.sub(r"\s+", " ", (text or "").strip())
    if len(clean) <= 120:
        return clean
    return clean[:117].rstrip() + "..."


def _recover_active_thread(state: MentalHealthState, current_message: str) -> Optional[str]:
    if state.get("active_thread_summary"):
        return state.get("active_thread_summary")
    if state.get("primary_concern"):
        return state.get("primary_concern")

    messages = state.get("messages") or []
    human_texts = [
        _message_text(m)
        for m in messages[:-1]
        if getattr(m, "type", "") == "human" and _message_text(m)
    ]
    for text in human_texts[-8:]:
        if _looks_like_distress(text):
            return _compact_concern(text)
    if _looks_like_distress(current_message):
        return _compact_concern(current_message)
    return None


def _detect_user_act(
    text: str,
    state: MentalHealthState,
    expected_answer_type: Optional[str],
    has_prior_assistant_question: bool,
) -> tuple[str, str, list[str], Optional[str], str]:
    lower = _normal(text)
    flags: list[str] = []
    referent: Optional[str] = None
    messages = state.get("messages") or []
    last_assistant = _last_assistant_text(messages)
    technique_offer_pending = assistant_offered_technique(last_assistant, expected_answer_type)
    prior_steps_given = assistant_likely_gave_steps(last_assistant)
    has_active_technique = bool(_latest_technique(state).get("name"))

    if has_prior_assistant_question or state.get("active_thread_summary") or state.get("primary_concern"):
        flags.append("continuation")

    gate_flags = set(state.get("gate_context_flags") or [])

    # Short positive words are not enough by themselves. Resolve them against
    # the immediately previous assistant turn before trusting the LLM gate.
    if is_no_thanks(text) and technique_offer_pending:
        return (
            "decline_technique_offer",
            "contextual_followup",
            flags + ["decline_technique_offer", "technique_declined"],
            "latest_recommended_technique",
            "listen_only",
        )
    if has_negative_feedback_signal(text):
        return "reject_technique", "reject_technique", flags + ["reject_technique", "technique_rejection"], "latest_recommended_technique", "handle_technique_rejection"
    if has_positive_outcome_signal(text) and (has_active_technique or prior_steps_given):
        return "positive_feedback", "positive_feedback", flags + ["positive_feedback", "outcome_feedback"], "latest_recommended_technique", "positive_feedback"
    if technique_offer_pending and is_technique_acceptance_reply(text):
        return "accept_technique", "accept_technique", flags + ["accept_technique", "technique_acceptance_answer"], "latest_recommended_technique", "continue_active_technique"
    if technique_offer_pending and not text.strip().endswith("?") and not is_polite_acknowledgement(text):
        return (
            "elaborating_after_technique_offer",
            "contextual_followup",
            flags + ["answering_previous_question", "technique_offer_deferred", "elaborating_after_technique_offer"],
            "active_concern",
            "ask_permission_before_technique",
        )
    if (
        has_prior_assistant_question
        and expected_answer_type != "technique_acceptance"
        and bool({"yes", "yeah", "yep", "yup"} & set(_plain(text).split()))
    ):
        answer_flag = f"{expected_answer_type}_answer" if expected_answer_type else "answering_previous_question"
        return "answering_previous_question", "contextual_followup", flags + ["answering_previous_question", answer_flag], "last_assistant_question", "ask_next_context_question"
    if is_polite_acknowledgement(text):
        return "acknowledgement", "chitchat", flags + ["acknowledgement", "gratitude_acknowledgement"], None, "acknowledge_and_pause"
    if is_bare_affirmation(text) and not technique_offer_pending and not has_prior_assistant_question:
        return "acknowledgement", "chitchat", flags + ["acknowledgement", "low_signal_affirmation"], None, "acknowledge_and_pause"

    if "reject_technique" in gate_flags or "technique_rejection" in gate_flags:
        return "reject_technique", "reject_technique", flags + ["reject_technique", "technique_rejection"], "latest_recommended_technique", "handle_technique_rejection"
    if state.get("gate_route") == "positive_feedback" or "positive_feedback" in gate_flags:
        return "positive_feedback", "positive_feedback", flags + ["positive_feedback"], "latest_recommended_technique", "positive_feedback"
    if "accept_technique" in gate_flags:
        return "accept_technique", "accept_technique", flags + ["accept_technique"], "latest_recommended_technique", "continue_active_technique"
    if "memory_query" in gate_flags or "technique_name_query" in gate_flags:
        return "memory_query", "memory_query", flags + ["memory_query", "technique_name_query", "refers_to_previous_technique"], "technique", "answer_memory_query"
    if "no_more_details" in gate_flags or "context_complete" in gate_flags:
        return (
            "no_more_details",
            "contextual_followup",
            flags + ["answering_previous_question", "no_more_details", "context_complete"],
            "active_concern",
            "formulate_and_offer_help",
        )

    if any(p in lower for p in ("what do you think", "your opinion", "what do you make of", "how do you see it", "your read", "read on this", "read on that")):
        return "asking_opinion", "contextual_followup", flags + ["asking_opinion", "refers_to_previous_topic"], "active_concern", "give_reflective_opinion"

    if any(p in lower for p in ("what was", "what's its name", "what was its name", "which technique", "which exercise", "first technique", "first exercise", "what was that called", "what was it called", "remind me what", "name of that")):
        return "memory_query", "memory_query", flags + ["memory_query", "technique_name_query", "refers_to_previous_technique"], "technique", "answer_memory_query"

    if any(p in lower for p in ("didn't like", "did not like", "didn't help", "did not help", "not helpful", "not working", "not useful", "that exercise was bad", "doesn't suit me", "does not suit me", "style suits me", "not for me", "didn't land", "did not land", "my mind argued with it")):
        return "reject_technique", "reject_technique", flags + ["reject_technique", "technique_rejection"], "latest_recommended_technique", "handle_technique_rejection"

    if (
        expected_answer_type != "technique_acceptance"
        and _looks_like_no_more_details(text)
        and (has_prior_assistant_question or state.get("active_thread_summary") or state.get("primary_concern"))
    ):
        return (
            "no_more_details",
            "contextual_followup",
            flags + ["answering_previous_question", "no_more_details", "context_complete"],
            "active_concern",
            "formulate_and_offer_help",
        )

    if any(p in lower for p in ("helped me more", "worked better", "that one helped", "i prefer", "i liked that one")):
        return "technique_preference_update", "technique_preference_update", flags + ["preference_update"], "latest_recommended_technique", "record_preference"

    if any(p in lower for p in ("suggest something", "something to help", "what can i do", "what should i do", "how can i handle", "how do i deal", "any advice", "can you help", "give me something", "need something practical")):
        return "help_request", "advice_seeking", flags + ["help_request"], "active_concern", "ask_next_context_question"

    if re.search(r"\b(?:about\s+|almost\s+|nearly\s+)?\d+\s*(?:day|days|week|weeks|month|months|year|years)\b", lower):
        return "answering_previous_question", "contextual_followup", flags + ["answering_previous_question", "duration_answer"], "last_assistant_question", "ask_next_context_question"

    subject_answers = {"math", "maths", "mathematics", "english", "physics", "chemistry", "biology", "history", "computer science", "cs"}
    if lower in subject_answers:
        return "answering_previous_question", "contextual_followup", flags + ["answering_previous_question", "subject_answer"], "last_assistant_question", "ask_next_context_question"

    if has_prior_assistant_question and not text.strip().endswith("?"):
        answer_flag = f"{expected_answer_type}_answer" if expected_answer_type else "answering_previous_question"
        answer_flags = ["answering_previous_question", answer_flag]
        if expected_answer_type == "subject_or_focus":
            answer_flags.append("subject_answer")
        return "answering_previous_question", "contextual_followup", flags + answer_flags, "last_assistant_question", "ask_next_context_question"

    if _short_text(text) and not text.strip().endswith("?") and flags:
        return "short_followup", "contextual_followup", flags + ["short_followup"], "active_concern", "ask_next_context_question"

    if _looks_like_distress(text):
        return "new_disclosure", "therapeutic", flags or ["new_emotional_disclosure"], "active_concern", "ask_next_context_question"

    return "current_turn", state.get("intent") or "venting", flags, referent, "ask_next_context_question"


def _apply_slot_updates(
    state: MentalHealthState,
    text: str,
    user_act: str,
    expected_answer_type: Optional[str],
    active_thread: Optional[str],
) -> dict:
    updates = {key: state.get(key) for key in _CONTEXT_KEYS}
    lower = _normal(text)

    if not updates.get("primary_concern") and active_thread:
        updates["primary_concern"] = active_thread
    if not updates.get("primary_concern") and _looks_like_distress(text):
        updates["primary_concern"] = _compact_concern(text)

    if user_act == "no_more_details":
        return updates

    duration_match = re.search(r"\b(?:about\s+|almost\s+|nearly\s+)?\d+\s*(?:day|days|week|weeks|month|months|year|years)\b", lower)
    if duration_match:
        updates["concern_duration"] = text

    if user_act in {"answering_previous_question", "short_followup"}:
        if expected_answer_type == "duration":
            updates["concern_duration"] = text
        elif expected_answer_type == "subject_or_focus":
            if _short_text(text, 6):
                updates["triggering_subject"] = text
            else:
                updates["triggering_context"] = text
        elif expected_answer_type in {"pain_point", "core_belief", "meaning_or_evidence"}:
            updates["core_belief"] = text
        elif expected_answer_type in {"body_sensation", "functional_impact"}:
            updates["functional_impact"] = text
        elif expected_answer_type in {"context_detail", "support_need"}:
            if not updates.get("triggering_context"):
                updates["triggering_context"] = text
            elif not updates.get("functional_impact"):
                updates["functional_impact"] = text

    if any(p in lower for p in ("can't focus", "cant focus", "blank", "forget", "avoid", "shut down", "nothing gets done", "wasting time", "drained", "tired", "can't sleep", "cant sleep")):
        updates["functional_impact"] = text

    if any(p in lower for p in ("fail", "not good enough", "can't do", "cant do", "disappoint", "wasn't enough", "wasnt enough", "should be fine", "should be doing", "guilty", "guilt", "all my work")):
        updates["core_belief"] = text

    return updates


def _build_active_thread_summary(slot_updates: dict, fallback: Optional[str]) -> Optional[str]:
    concern = slot_updates.get("primary_concern") or fallback
    parts = []
    if concern:
        parts.append(str(concern))
    if slot_updates.get("concern_duration"):
        parts.append(f"duration: {slot_updates['concern_duration']}")
    if slot_updates.get("triggering_subject"):
        parts.append(f"focus: {slot_updates['triggering_subject']}")
    if slot_updates.get("triggering_context"):
        parts.append(f"context: {slot_updates['triggering_context']}")
    if slot_updates.get("functional_impact"):
        parts.append(f"impact: {slot_updates['functional_impact']}")
    if slot_updates.get("core_belief"):
        parts.append(f"belief/detail: {slot_updates['core_belief']}")
    if not parts:
        return None
    return "; ".join(parts)[:500]


def resolve_conversation_context(state: MentalHealthState) -> dict:
    """Resolve the latest user message against the same-session thread."""
    messages = state.get("messages") or []
    current = _current_message(state)
    previous_question = state.get("last_assistant_question") or extract_last_question(_last_assistant_text(messages))
    expected_answer_type = state.get("expected_answer_type") or infer_expected_answer_type(previous_question)
    has_prior_question = bool(previous_question)
    active_thread = _recover_active_thread(state, current)

    user_act, intent, flags, referent, response_task = _detect_user_act(
        current,
        state,
        expected_answer_type,
        has_prior_question,
    )
    slot_updates = _apply_slot_updates(state, current, user_act, expected_answer_type, active_thread)
    active_thread_summary = _build_active_thread_summary(slot_updates, active_thread)

    resolved = {
        "user_act": user_act,
        "intent": intent,
        "is_continuation": bool(flags and "continuation" in flags),
        "referent": referent,
        "previous_question": previous_question,
        "expected_answer_type": expected_answer_type,
        "response_task": response_task,
        "context_flags": flags,
        "slot_updates": {k: v for k, v in slot_updates.items() if v not in (None, "", [])},
        "active_thread_summary": active_thread_summary,
    }

    _context_logger.info(
        "Resolver Summary | act=%s | intent=%s | expected=%s | task=%s | flags=%s",
        user_act,
        intent,
        expected_answer_type or "none",
        response_task,
        flags,
    )
    _debug_print_resolver_context(
        current=current,
        previous_question=previous_question,
        expected_answer_type=expected_answer_type,
        active_thread=active_thread,
        resolved=resolved,
    )

    return {
        "resolved_user_act": resolved,
        "intent": intent,
        "response_task": response_task,
        "gate_context_flags": flags,
        "latest_referenced_entity": referent,
        "last_assistant_question": previous_question,
        "expected_answer_type": expected_answer_type,
        "active_thread_summary": active_thread_summary,
        **resolved["slot_updates"],
    }


def commit_conversation_context(state: dict, previous_context: Optional[dict] = None) -> dict:
    """Build compact context updates after the assistant response is known."""
    previous_context = previous_context or {}
    response = state.get("final_response") or state.get("response") or ""
    intent = state.get("intent") or ""
    response_task = state.get("response_task") or ""
    technique = state.get("recommended_technique") or {}
    latest = state.get("latest_recommended_technique") or previous_context.get("latest_recommended_technique") or {}
    active = state.get("active_technique") or previous_context.get("active_technique") or {}

    updates = {}
    for key in (
        "active_thread_summary",
        "primary_concern",
        "concern_duration",
        "triggering_subject",
        "triggering_context",
        "functional_impact",
        "core_belief",
        "response_task",
        "resolved_user_act",
        "latest_referenced_entity",
    ):
        if state.get(key) not in (None, "", []):
            updates[key] = state.get(key)

    question = extract_last_question(response)
    if question:
        updates["last_assistant_question"] = question
        updates["expected_answer_type"] = infer_expected_answer_type(question)
        updates["last_assistant_act"] = response_task or state.get("conversation_strategy")
    else:
        updates["last_assistant_question"] = None
        updates["expected_answer_type"] = None
        updates["last_assistant_act"] = response_task or state.get("conversation_strategy")

    prior_count = int(previous_context.get("question_count_since_technique") or 0)
    asked_context_question = bool(question) and updates.get("expected_answer_type") != "technique_acceptance"
    updates["question_count_since_technique"] = prior_count + 1 if asked_context_question else prior_count

    # dialogue_solution_turn_count tracking
    dialogue_prior = int(previous_context.get("dialogue_solution_turn_count") or 0)
    if response_task == "give_reflective_opinion":
        updates["dialogue_solution_turn_count"] = dialogue_prior + 1
    else:
        updates["dialogue_solution_turn_count"] = dialogue_prior

    if technique and technique.get("name"):
        offered = {**technique, "status": "offered"}
        updates["latest_recommended_technique"] = technique
        updates["active_technique"] = offered
        updates["question_count_since_technique"] = 0
        updates["dialogue_solution_turn_count"] = 0
    elif latest and latest.get("name"):
        updates["latest_recommended_technique"] = latest

    if intent == "accept_technique" and latest and latest.get("name"):
        updates["active_technique"] = {**latest, "status": "active"}

    if intent == "reject_technique":
        rejected = latest or active
        if rejected and rejected.get("name"):
            updates["latest_rejected_technique"] = rejected
            updates["active_technique"] = {**rejected, "status": "rejected"}

    if intent == "technique_preference_update":
        preferred = list(previous_context.get("preferred_techniques") or [])
        preferred_candidate = latest or active
        if preferred_candidate and preferred_candidate.get("name"):
            if not any(
                isinstance(p, dict)
                and (p.get("name") or "").lower() == preferred_candidate["name"].lower()
                for p in preferred
            ):
                preferred.append(preferred_candidate)
        updates["preferred_techniques"] = preferred[-5:]

    if intent == "positive_feedback" and latest and latest.get("name"):
        updates["active_technique"] = {**latest, "status": "helpful"}

    if _debug_context_enabled():
        active_after = updates.get("active_technique") or active or {}
        _context_logger.info("Context Commit | compact session state")
        _context_logger.info(
            "  active_thread_summary: %s",
            _clip(updates.get("active_thread_summary") or previous_context.get("active_thread_summary"), 500) or "none",
        )
        _context_logger.info(
            "  last_assistant_question: %s",
            _clip(updates.get("last_assistant_question"), 300) or "none",
        )
        _context_logger.info("  expected_answer_type: %s", updates.get("expected_answer_type") or "none")
        _context_logger.info("  response_task: %s", updates.get("response_task") or "none")
        _context_logger.info("  question_count_since_technique: %s", updates.get("question_count_since_technique"))
        _context_logger.info(
            "  active_technique: %s",
            (active_after.get("name") if isinstance(active_after, dict) else None) or "none",
        )

    return updates
