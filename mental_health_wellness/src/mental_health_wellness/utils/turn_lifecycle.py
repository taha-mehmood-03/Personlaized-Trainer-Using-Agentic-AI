"""Deterministic turn lifecycle tagging helpers.

The lifecycle tag is deliberately rule-based. The smart gate makes a cheap
initial guess from route/history, then the planner refines it once fused
emotion signals are available.
"""

from __future__ import annotations

from typing import Any

from .turn_signals import (
    assistant_likely_gave_steps,
    assistant_offered_technique,
    is_polite_acknowledgement,
    words,
)


DISCLOSURE_TURN_TYPES = {
    "INITIAL_DISCLOSURE",
    "FOLLOW_UP_DISCLOSURE",
    "CRISIS_DISCLOSURE",
}

RESOLUTION_TURN_TYPES = {
    "FOLLOW_UP_DISCLOSURE",
    "POST_RECOMMENDATION_REACTION",
}

NON_DISCLOSURE_ROUTES = {
    "chitchat",
    "memory_query",
    "list_techniques",
    "rejection",
}

OLD_TURN_TYPE_ALIASES = {
    "POST_RECOMMENDATION": "POST_RECOMMENDATION_REACTION",
}


def normalize_turn_type(value: Any, default: str | None = "FOLLOW_UP_DISCLOSURE") -> str | None:
    if value is None:
        return default
    text = str(value).split(".")[-1].strip().upper()
    if not text:
        return default
    return OLD_TURN_TYPE_ALIASES.get(text, text)


def message_text(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("content") or "")
    return str(getattr(message, "content", "") or "")


def message_role(message: Any) -> str:
    if isinstance(message, dict):
        raw = message.get("role") or message.get("type") or ""
    else:
        raw = getattr(message, "role", None) or getattr(message, "type", "")
    raw = getattr(raw, "name", raw)
    text = str(raw).upper()
    if "ASSISTANT" in text or text == "AI":
        return "assistant"
    if "USER" in text or text == "HUMAN":
        return "user"
    return text.lower()


def last_assistant_text(messages: list[Any]) -> str:
    for message in reversed(messages or []):
        if message_role(message) == "assistant":
            return message_text(message)
    return ""


def prior_assistant_offered_technique(
    *,
    last_assistant_message: str,
    previous_context: dict | None = None,
    expected_answer_type: str | None = None,
    db_flag: bool = False,
) -> bool:
    if db_flag:
        return True
    previous_context = previous_context or {}
    active = previous_context.get("active_technique") or {}
    if isinstance(active, dict) and active.get("status") in {"offered", "active"} and active.get("id"):
        return True
    if assistant_offered_technique(last_assistant_message, expected_answer_type):
        return True
    return assistant_likely_gave_steps(last_assistant_message)


def initial_turn_type_guess(
    *,
    current_message: str,
    session_message_count: int,
    gate_route: str,
    gate_context_flags: list[str] | None = None,
    last_assistant_message: str = "",
    previous_context: dict | None = None,
    expected_answer_type: str | None = None,
    prior_technique_offered: bool = False,
) -> str:
    route = str(gate_route or "").lower()
    flags = {str(flag).lower() for flag in (gate_context_flags or [])}
    previous_context = previous_context or {}

    if route == "crisis" or "crisis" in flags:
        return "CRISIS_DISCLOSURE"

    if route in NON_DISCLOSURE_ROUTES:
        return "CONTEXT_GATHERING"

    if prior_assistant_offered_technique(
        last_assistant_message=last_assistant_message,
        previous_context=previous_context,
        expected_answer_type=expected_answer_type,
        db_flag=prior_technique_offered,
    ):
        return "POST_RECOMMENDATION_REACTION"

    first_user_message = session_message_count <= 1
    if first_user_message:
        if route in {"therapeutic", "contextual_followup", ""}:
            return "INITIAL_DISCLOSURE"
        return "CONTEXT_GATHERING"

    if route == "contextual_followup" or "answering_previous_question" in flags:
        return "CONTEXT_GATHERING"

    if last_assistant_message.strip().endswith("?") and len(words(current_message)) <= 18:
        return "CONTEXT_GATHERING"

    return "FOLLOW_UP_DISCLOSURE"


def _clean_signal_set(values: Any) -> set[str]:
    if not values:
        return set()
    if not isinstance(values, list):
        values = [values]
    return {str(value or "").strip().lower() for value in values if str(value or "").strip()}


def has_new_emotional_content(state: dict[str, Any], previous_context: dict | None = None) -> bool:
    previous_context = previous_context or {}
    current_signals = set()
    for key in ("primary_sub_emotion", "secondary_sub_emotions", "detected_symptoms", "detected_behaviors", "detected_contexts"):
        current_signals.update(_clean_signal_set(state.get(key)))

    previous_signals = set()
    for key in ("primary_sub_emotion", "secondary_sub_emotions", "detected_symptoms", "detected_behaviors", "detected_contexts"):
        previous_signals.update(_clean_signal_set(previous_context.get(key)))

    current_signals.discard("neutral")
    current_signals.discard("none")
    if current_signals - previous_signals:
        return True

    emotion = str(state.get("fused_emotion") or state.get("emotion") or "neutral").lower()
    try:
        intensity = float(state.get("fused_intensity", state.get("intensity", 0.0)) or 0.0)
    except (TypeError, ValueError):
        intensity = 0.0
    if emotion in {"sadness", "anxiety", "anger", "fear", "disgust"} and intensity >= 0.45:
        return True

    messages = state.get("messages") or []
    latest = message_text(messages[-1]) if messages else str(state.get("message") or "")
    return len(words(latest)) >= 16 and not is_polite_acknowledgement(latest)


def refine_turn_type(
    *,
    state: dict[str, Any],
    previous_context: dict | None = None,
) -> str:
    guess = normalize_turn_type(
        state.get("turn_type_guess") or state.get("turn_type"),
        default="FOLLOW_UP_DISCLOSURE",
    )
    route = str(state.get("gate_route") or "").lower()

    if state.get("crisis_detected") or route == "crisis":
        return "CRISIS_DISCLOSURE"

    if route in NON_DISCLOSURE_ROUTES:
        return "CONTEXT_GATHERING"

    if guess == "INITIAL_DISCLOSURE":
        return "INITIAL_DISCLOSURE" if has_new_emotional_content(state, previous_context) else "CONTEXT_GATHERING"

    if guess == "CONTEXT_GATHERING" and has_new_emotional_content(state, previous_context):
        return "FOLLOW_UP_DISCLOSURE"

    if guess == "POST_RECOMMENDATION_REACTION":
        return "POST_RECOMMENDATION_REACTION"

    return guess or "FOLLOW_UP_DISCLOSURE"

