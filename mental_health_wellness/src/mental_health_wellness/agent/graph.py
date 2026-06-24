"""
Graph Builder - StateGraph construction and main entry points

ARCHITECTURE OVERVIEW (v6.0  SentiMind Latency-Optimized):
The graph implements a 5-node deterministic hybrid pipeline with pre-graph
short-circuits for crisis keywords and casual chitchat.

PRE-GRAPH SHORT-CIRCUITS (before the graph runs):
  - Crisis keywords  -> Hardcoded template (<300ms)
  - Casual chitchat   -> Single Groq 8b call (<1,500ms)

MAIN PIPELINE (LangGraph, 5 nodes):
  1. Parallel Intake (v5.3):         4-way concurrent:
                                        Crisis Pre-Screener (OpenRouter llama-3.3-70b)
                                        Therapist Agent     (OpenRouter llama-3.3-70b)
                                        Mood Analyzer       (OpenRouter claude-3-haiku)
                                        Intent Pre-Check    (OpenRouter claude-3-haiku async)
                                        Support Tools       (DuckDuckGo, Vector DB)
  2. Analysis & Planning [FUSED]:    emotion_fusion + parallel_analysis
                                     + conversation_planner + behavioral_activation
  3. Response Pipeline [FUSED]:      technique_selector + role_selector
  4. Response Generator:             Single async Groq LLM call
  5. Crisis Handler:                 Safety response with resources

POST-GRAPH (fire-and-forget):
  - Parallel Persist:  profile + saver + outcome (runs as background task)

v6.0 LATENCY FIXES:
  1. NO CHECKPOINTER  zero serialization overhead (was ~3-5s with MemorySaver)
  2. 5 graph nodes instead of 10 (4 fewer checkpoint events)
  3. parallel_persist runs as background task (user sees response immediately)
  4. ensure_user_exists cached (skips DB after first call)
  5. Batched Prisma writes in session_saver
  6. Pre-graph short-circuits for crisis keywords + chitchat
"""

import time
import uuid
import asyncio
import logging
import os
import re
from typing import Optional

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import StateGraph, START, END

from .state import MentalHealthState, get_initial_state
from ..nodes.crisis_handler import handle_crisis
from ..nodes.optimized_response_generator import generate_response, _build_complement_offer_line
from ..nodes.parallel_intake import run_parallel_intake
from ..nodes.parallel_persist import run_parallel_persist
from ..nodes.analysis_and_planning import run_analysis_and_planning  # v6.0: fused
from ..nodes.response_pipeline import run_response_pipeline          # v6.0: fused
from ..nodes.conversation_context_resolver import commit_conversation_context, extract_last_question
from ..db.client import ensure_user_exists_cached, create_new_session
from ..llm.llm_classifier import llm_crisis_check, smart_pipeline_gate, deterministic_crisis_safety_net
from ..utils.turn_signals import (
    has_negative_feedback_signal,
    has_positive_outcome_signal,
    is_explicit_exercise_request as _turn_signal_explicit_exercise_request,
    plain_text,
)
from ..utils.distress_anchor import anchor_write_policy
from ..utils.turn_lifecycle import initial_turn_type_guess, last_assistant_text

logger = logging.getLogger(__name__)


def _fmt_list(values, limit: int = 4) -> str:
    cleaned = [str(value) for value in (values or []) if value]
    if not cleaned:
        return "none"
    suffix = f", +{len(cleaned) - limit}" if len(cleaned) > limit else ""
    return ", ".join(cleaned[:limit]) + suffix


def _clean_metadata_label(value, default=None):
    if value is None:
        return default
    text = str(value).split(".")[-1].strip()
    if text.lower() in {"", "0", "none", "null", "undefined", "nan", "n/a", "unknown"}:
        return default
    try:
        float(text)
        return default
    except ValueError:
        pass
    return text


def _clean_metadata_list(values):
    if not isinstance(values, list):
        return []
    return [clean for item in values if (clean := _clean_metadata_label(item))]


def _emotion_label(emotion, primary_sub_emotion):
    core = _clean_metadata_label(emotion)
    sub = _clean_metadata_label(primary_sub_emotion)
    if core and sub and core.lower() != sub.lower():
        return f"{core} / {sub}"
    return core or sub


# ============================================
# v6.0 FIX 1: NO CHECKPOINTER  MANUAL MESSAGE STORE
# ============================================
# Instead of MemorySaver (which serializes the full 40-field state at every
# node boundary), we manage multi-turn message history with a simple dict.
# This eliminates ~3-5s of checkpoint overhead per message.

_message_store: dict[str, list] = {}    # {thread_id: [BaseMessage, ...]}
_MAX_MESSAGE_HISTORY = 20               # Rolling window per thread
_session_context_store: dict[str, dict] = {}  # compact stage/context fields per session

_SESSION_CONTEXT_KEYS = (
    "conversation_stage",
    "conversation_phase",
    "primary_concern",
    "concern_duration",
    "triggering_subject",
    "triggering_context",
    "functional_impact",
    "core_belief",
    "latest_recommended_technique",
    "latest_rejected_technique",
    "pending_recommended_technique",
    "pending_technique_reason",
    "pending_technique_created_at_turn",
    "pending_complement_technique",   # queued series complement — survives to next turn
    "pending_complement_signal",      # human-readable signal the complement targets
    "technique_candidates",
    "technique_area",
    "technique_plan_mode",
    "technique_series",
    "alternative_techniques",   # complement queue — must survive to next turn for series delivery
    "preferred_techniques",
    "gate_confidence",
    "gate_context_flags",
    "gate_emotional_register",
    "gate_intensity_hint",
    "gate_should_skip_mood_analysis",
    "gate_needs_full_pipeline",
    "needs_technique",
    "latest_referenced_entity",
    "active_thread_summary",
    "last_assistant_question",
    "expected_answer_type",
    "last_assistant_act",
    "resolved_user_act",
    "response_task",
    "question_count_since_technique",
    "active_technique",
    "last_detected_emotion",
    "last_detected_intensity",
    "session_start_emotion",
    "session_start_intensity",
    "session_start_sub_emotion",
    "session_start_symptoms",
    "session_start_behaviors",
    "technique_delivery_emotion",
    "technique_delivery_intensity",
    "technique_delivery_sub_emotion",
    "technique_delivery_symptoms",
    "technique_delivery_behaviors",
    "techniques_displayed_ids",  # anti-repetition: IDs of techniques already shown this session
    "peak_distress_intensity",   # highest confirmed distress this session (anchor for follow-ups)
    "followup_turn_count",       # consecutive contextual follow-up turns since last disclosure
    "raw_emotion_label",
    "primary_sub_emotion",
    "secondary_sub_emotions",
    "detected_symptoms",
    "detected_behaviors",
    "detected_contexts",
    "emotion_scores",
    "emotion_reasoning",
    "turn_type",
    "turn_type_guess",
    "pending_outcome_id",
    "previous_session_handoff",
    "exercise_consent",
    "solution_preference",
    "suppressed_topics",
    "active_issue_source",
    "context_sufficiency",
    "dialogue_solution_turn_count",
    "dialogue_support_mode",
    # v14.0: recovery arc + crisis dedup fields (must persist across turns)
    "session_disclosure_complete",
    "reflection_questions_since_resolution",
    "whatsapp_alert_sent",
    # v14.1: clinical baseline — captured once per session for PHQ-9/GAD-7 delta computation
    "session_start_clinical_score",
    "session_start_gad7_score",
)



def _env_flag(name: str) -> bool:
    return os.getenv(name, "0").lower() in {"1", "true", "yes", "on"}


def _prior_assistant_technique_flag(prev_messages: list) -> bool:
    for msg in reversed(prev_messages or []):
        role = str(getattr(msg, "role", None) or getattr(msg, "type", "") or "").upper()
        if "ASSISTANT" not in role and role != "AI":
            continue
        if bool(getattr(msg, "techniqueOfferedThisTurn", False)):
            return True
        if getattr(msg, "techniqueId", None):
            return True
        return False
    return False


def _turn_type_guess_for_gate(
    *,
    message: str,
    gate_result: dict,
    prev_messages: list,
    session_context_state: dict,
) -> str:
    session_message_count = sum(
        1 for msg in prev_messages or [] if str(getattr(msg, "type", "")).lower() == "human"
    ) + 1
    return initial_turn_type_guess(
        current_message=message,
        session_message_count=session_message_count,
        gate_route=str((gate_result or {}).get("route") or ""),
        gate_context_flags=list((gate_result or {}).get("context_flags") or []),
        last_assistant_message=last_assistant_text(prev_messages),
        previous_context=session_context_state,
        expected_answer_type=session_context_state.get("expected_answer_type"),
        prior_technique_offered=_prior_assistant_technique_flag(prev_messages),
    )


def _load_session_context_state(session_id: str) -> dict:
    """Fast in-memory therapeutic context for same-session continuity."""
    if not session_id:
        return {}
    return dict(_session_context_store.get(session_id, {}))


def _remember_session_context(session_id: str, state: dict) -> None:
    """Persist compact non-message state between turns without DB latency."""
    if not session_id:
        return

    previous = _session_context_store.get(session_id, {})
    updates = {key: state.get(key) for key in _SESSION_CONTEXT_KEYS if key in state}
    updates.update(commit_conversation_context(state, previous))

    # One-shot consumption of the complement queue: once the complement technique has
    # been delivered this turn, drop it from the persisted queue so a later "yes" does
    # not re-offer it forever. Mirrors the planner's recovery-guard clear. Alternatives
    # still persist through the immediate-delivery + preview turns (which keep their own
    # response_task), so the series stays exactly two techniques.
    _gate_flags_now = state.get("gate_context_flags") or []
    _complement_consumed = (
        state.get("response_task") == "offer_complement_technique"
        or state.get("intent") in {"reject_technique", "technique_not_helpful"}
        or "reject_technique" in _gate_flags_now
        or "technique_rejection" in _gate_flags_now
    )
    if state.get("response_task") == "offer_complement_technique":
        updates["alternative_techniques"] = []

    def _as_string_list(value) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item or "").strip()]
        if value is None:
            return []
        text = str(value).strip()
        return [text] if text else []

    technique = state.get("recommended_technique") or {}
    if technique and technique.get("name"):
        updates["latest_recommended_technique"] = technique
        updates["active_technique"] = {**technique, "status": "offered"}

    detected_emotion = state.get("fused_emotion") or state.get("emotion")
    detected_intensity = state.get("fused_intensity", state.get("intensity"))
    if not previous.get("session_start_emotion") and detected_emotion:
        updates["session_start_emotion"] = detected_emotion
        updates["session_start_intensity"] = detected_intensity
        updates["session_start_sub_emotion"] = state.get("primary_sub_emotion")
        updates["session_start_symptoms"] = _as_string_list(state.get("detected_symptoms"))
        updates["session_start_behaviors"] = _as_string_list(state.get("detected_behaviors"))
    if state.get("conversation_strategy") == "suggest_technique" and technique:
        updates["technique_delivery_emotion"] = state.get("technique_selection_emotion") or detected_emotion
        updates["technique_delivery_intensity"] = state.get("technique_selection_intensity") or detected_intensity
        updates["technique_delivery_sub_emotion"] = state.get("primary_sub_emotion")
        updates["technique_delivery_symptoms"] = _as_string_list(state.get("detected_symptoms"))
        updates["technique_delivery_behaviors"] = _as_string_list(state.get("detected_behaviors"))
    current_gate_route = state.get("gate_route", "")
    # Routes where the current message is a contextual reply, not a fresh disclosure.
    # We must NOT update last_detected_intensity on these turns — doing so causes
    # circular drift where follow-up answers (e.g. "i want to enjoy a lil bit")
    # overwrite the real anchor established at initial disclosure.
    _FOLLOWUP_ROUTES = {"contextual_followup", "chitchat", "memory_query", "positive_feedback", "technique_follow_up"}
    is_followup_route = current_gate_route in _FOLLOWUP_ROUTES
    followup_sub_emotion_enriched = bool(state.get("followup_sub_emotion_enriched"))
    if is_followup_route:
        for key in (
            "last_detected_emotion",
            "last_detected_intensity",
            "peak_distress_intensity",
            "raw_emotion_label",
            "primary_sub_emotion",
            "secondary_sub_emotions",
            "detected_symptoms",
            "detected_behaviors",
            "detected_contexts",
            "emotion_scores",
        ):
            updates.pop(key, None)
        if followup_sub_emotion_enriched:
            if state.get("primary_sub_emotion"):
                updates["primary_sub_emotion"] = state.get("primary_sub_emotion")
            if state.get("secondary_sub_emotions") is not None:
                updates["secondary_sub_emotions"] = state.get("secondary_sub_emotions") or []
            if state.get("detected_symptoms") is not None:
                updates["detected_symptoms"] = state.get("detected_symptoms") or []
            if state.get("detected_behaviors") is not None:
                updates["detected_behaviors"] = state.get("detected_behaviors") or []
            if state.get("detected_contexts") is not None:
                updates["detected_contexts"] = state.get("detected_contexts") or []
    else:
        for key in ("last_detected_emotion", "last_detected_intensity", "peak_distress_intensity"):
            updates.pop(key, None)

    should_write_anchor, anchor_intensity, anchor_reason = anchor_write_policy(
        state,
        previous,
        detected_intensity,
    )

    if detected_emotion and not is_followup_route and should_write_anchor:
        updates["last_detected_emotion"] = detected_emotion
    # Only anchor intensity on genuine therapeutic disclosures — not follow-ups.
    if detected_intensity is not None and not is_followup_route and should_write_anchor and anchor_intensity is not None:
        updates["last_detected_intensity"] = anchor_intensity
    elif not is_followup_route and not should_write_anchor:
        print(f"[SESSION_CONTEXT] Anchor write skipped: {anchor_reason}")

    # Track peak distress for anchoring: only raise, never lower.
    if (
        anchor_intensity is not None
        and should_write_anchor
        and anchor_intensity >= 0.5
        and current_gate_route in {"therapeutic", "crisis", ""}
    ):
        current_peak = float(previous.get("peak_distress_intensity") or 0.0)
        updates["peak_distress_intensity"] = max(current_peak, anchor_intensity)

    # Track consecutive contextual follow-up turns for progressive decay calculation.
    if current_gate_route == "contextual_followup":
        prev_count = int(previous.get("followup_turn_count") or 0)
        updates["followup_turn_count"] = prev_count + 1
    elif current_gate_route in {"therapeutic", "crisis"}:
        updates["followup_turn_count"] = 0  # Reset counter on new emotional disclosure

    if not is_followup_route and state.get("primary_sub_emotion"):
        updates["primary_sub_emotion"] = state.get("primary_sub_emotion")
    if not is_followup_route and state.get("secondary_sub_emotions") is not None:
        updates["secondary_sub_emotions"] = state.get("secondary_sub_emotions") or []
    if not is_followup_route and state.get("detected_symptoms") is not None:
        updates["detected_symptoms"] = state.get("detected_symptoms") or []
    if not is_followup_route and state.get("detected_behaviors") is not None:
        updates["detected_behaviors"] = state.get("detected_behaviors") or []
    if not is_followup_route and state.get("detected_contexts") is not None:
        updates["detected_contexts"] = state.get("detected_contexts") or []
    if not is_followup_route and state.get("emotion_scores") is not None:
        updates["emotion_scores"] = state.get("emotion_scores") or {}

    intent = state.get("intent")
    if intent == "reject_technique":
        rejected = state.get("latest_recommended_technique") or previous.get("latest_recommended_technique") or technique
        if rejected:
            updates["latest_rejected_technique"] = rejected

    if intent in {"technique_preference_update", "positive_feedback"}:
        preferred = list(previous.get("preferred_techniques") or [])
        preferred_candidate = (
            state.get("active_technique")
            or state.get("latest_recommended_technique")
            or previous.get("latest_recommended_technique")
            or technique
        )
        if preferred_candidate and preferred_candidate.get("name"):
            if not any((p.get("name") or "").lower() == preferred_candidate["name"].lower() for p in preferred if isinstance(p, dict)):
                preferred.append(preferred_candidate)
        updates["preferred_techniques"] = preferred[-5:]

    # Eagerly capture clinical baseline so subsequent bypass turns can read it.
    # session_saver computes this in the background (too late for the next turn);
    # we mirror the same logic here so it lands in the store synchronously.
    if not previous.get("session_start_clinical_score"):
        _raw_phq = state.get("clinical_raw_phq9") or state.get("clinical_phq9_score", 0)
        _raw_gad = state.get("clinical_raw_gad7") or state.get("clinical_gad7_score", 0)
        if _raw_phq and float(_raw_phq) > 0:
            updates["session_start_clinical_score"] = float(_raw_phq)
            if _raw_gad and float(_raw_gad) > 0:
                updates["session_start_gad7_score"] = float(_raw_gad)

    compact = dict(previous)
    clearable = {"last_assistant_question", "expected_answer_type"}
    for key, value in updates.items():
        if key in clearable:
            compact[key] = value
        elif value not in (None, "", []):
            compact[key] = value
    # Explicitly drop the queued complement once it's delivered or rejected. Falsy
    # values are skipped by the merge above, so we pop here to actually clear it.
    if _complement_consumed:
        compact.pop("pending_complement_technique", None)
        compact.pop("pending_complement_signal", None)
        compact.pop("alternative_techniques", None)
    _session_context_store[session_id] = compact


def clear_session_context(session_id: str) -> None:
    """
    Purge ALL in-memory state for a given session_id.

    Call this when the user starts a brand-new session so that:
    - Emotional anchors (last_detected_emotion, peak_distress_intensity)
    - Therapeutic thread (primary_concern, active_thread_summary, core_belief)
    - Consent state (exercise_consent, solution_preference, suppressed_topics)
    - Message history (_message_store)
    ...do NOT bleed from a previous session into the new one.

    The in-memory stores are the ONLY source of turn-to-turn context for the
    v6.0 no-checkpointer architecture.  Clearing them guarantees a clean slate.
    """
    if not session_id:
        return
    removed_ctx = _session_context_store.pop(session_id, None)
    removed_msg = _message_store.pop(session_id, None)
    ctx_keys = len(removed_ctx) if isinstance(removed_ctx, dict) else 0
    msg_count = len(removed_msg) if isinstance(removed_msg, list) else 0
    print(
        f"[SESSION_CLEAR] Purged in-memory state for session {session_id[:20]}... "
        f"| context_keys={ctx_keys} | messages={msg_count}"
    )


def _elapsed_s(start: float) -> float:
    return time.time() - start


def _voice_confidence(value) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _latency_monitoring_enabled() -> bool:
    """Return whether detailed agent-stage latency logs should be emitted."""
    return os.getenv("SENTIMIND_LATENCY_MONITORING", "1").lower() not in {"0", "false", "no", "off"}


def _latency_threshold_ms() -> int:
    """Slow-stage warning threshold in milliseconds."""
    raw = os.getenv("SENTIMIND_LATENCY_STAGE_WARN_MS", "800")
    try:
        return max(1, int(raw))
    except ValueError:
        return 800


def _latency_mark(trace: list, stage: str, start: float, **metadata) -> list:
    """Append one stage timing to a trace and emit a structured log line."""
    if not _latency_monitoring_enabled():
        return trace

    duration_ms = round(_elapsed_s(start) * 1000, 2)
    threshold_ms = _latency_threshold_ms()
    slow = duration_ms >= threshold_ms
    item = {
        "stage": stage,
        "duration_ms": duration_ms,
        "slow": slow,
        **{k: v for k, v in metadata.items() if v not in (None, "", [], {})},
    }
    trace.append(item)

    log = logger.warning if slow else logger.info
    log(
        "Latency AGENT | stage=%s duration_ms=%.2f slow=%s route=%s session=%s",
        stage,
        duration_ms,
        slow,
        metadata.get("route", "n/a"),
        metadata.get("session_id", "n/a"),
    )
    return trace


async def _timed_graph_node(stage: str, node_func, state: MentalHealthState) -> dict:
    """Run a LangGraph node and append its duration to the state trace."""
    stage_start = time.time()
    try:
        result = node_func(state)
        if asyncio.iscoroutine(result):
            result = await result
    except Exception:
        trace = list(state.get("latency_trace", []))
        _latency_mark(trace, stage, stage_start, status="error", session_id=state.get("session_id"))
        raise

    if not isinstance(result, dict):
        result = {}

    trace = list(state.get("latency_trace", []))
    _latency_mark(
        trace,
        stage,
        stage_start,
        route=state.get("gate_route"),
        session_id=state.get("session_id"),
        strategy=result.get("conversation_strategy") or state.get("conversation_strategy"),
    )
    result["latency_trace"] = trace
    return result


async def _run_parallel_intake_timed(state: MentalHealthState) -> dict:
    return await _timed_graph_node("node.parallel_intake", run_parallel_intake, state)


async def _run_analysis_and_planning_timed(state: MentalHealthState) -> dict:
    return await _timed_graph_node("node.analysis_and_planning", run_analysis_and_planning, state)


async def _run_response_pipeline_timed(state: MentalHealthState) -> dict:
    return await _timed_graph_node("node.response_pipeline", run_response_pipeline, state)


async def _handle_crisis_timed(state: MentalHealthState) -> dict:
    return await _timed_graph_node("node.crisis_handler", handle_crisis, state)


async def _generate_response_timed(state: MentalHealthState) -> dict:
    return await _timed_graph_node("node.response_generator", generate_response, state)


def _latency_summary(trace: list, total_start: float | None = None) -> dict:
    """Build compact latency metadata for API responses and SSE final events."""
    clean_trace = [item for item in trace or [] if isinstance(item, dict)]
    bottleneck = max(clean_trace, key=lambda item: item.get("duration_ms", 0), default=None)
    summary = {
        "enabled": _latency_monitoring_enabled(),
        "stage_count": len(clean_trace),
        "slow_threshold_ms": _latency_threshold_ms(),
        "slow_stages": [
            {
                "stage": item.get("stage"),
                "duration_ms": item.get("duration_ms"),
            }
            for item in clean_trace
            if item.get("slow")
        ],
        "bottleneck": {
            "stage": bottleneck.get("stage"),
            "duration_ms": bottleneck.get("duration_ms"),
        } if bottleneck else None,
    }
    if total_start is not None:
        summary["total_ms"] = round(_elapsed_s(total_start) * 1000, 2)
    return summary


def _extract_llm_str(response) -> str:
    """
    Safely extract a plain string from any LangChain LLM response object.

    Gemini (and some other providers) can return `.content` as a *list* of
    content-part dicts instead of a plain string when the model produces
    multimodal or structured output.  Callers that blindly do
    ``resp.content.split(" ")`` crash with 'list has no attribute split'.

    This helper normalises all cases to a UTF-8 string.
    """
    if response is None:
        return ""
    # Standard LangChain message objects
    content = getattr(response, "content", None)
    if content is None:
        # Fallback: raw string / unknown type
        return str(response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # Gemini multimodal format: [{"type": "text", "text": "..."}] or ["...", ...]
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(part.get("text") or part.get("content") or "")
            else:
                parts.append(str(part))
        return "".join(parts)
    return str(content)


async def _invoke_chat_llm(messages, *, max_tokens: int = 320, temperature: float = 0.7):
    """LLM call with key rotation for graph bypass handlers. Always returns an AIMessage."""
    from ..llm.groq_llm import get_llm_manager
    from langchain_core.messages import AIMessage as _AI

    manager = get_llm_manager()
    if hasattr(manager, "ainvoke_openrouter_with_rotation"):
        resp = await manager.ainvoke_openrouter_with_rotation(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    elif hasattr(manager, "ainvoke_gemini_with_rotation"):
        resp = await manager.ainvoke_gemini_with_rotation(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    else:
        llm = manager.get_llm().bind(max_output_tokens=max_tokens, temperature=temperature)
        resp = await llm.ainvoke(messages)

    # Normalise content to str so all callers are safe to call .split() / str ops
    text = _extract_llm_str(resp)
    return _AI(content=text)


async def _load_messages_with_db_fallback(thread_id: str) -> list:
    """
    Load conversation history for a session.

    Priority:
      1. In-memory _message_store  (fast, zero I/O — normal case)
      2. Prisma DB fallback         (cold start / server restart recovery)

    The DB fallback converts stored Message rows back to LangChain
    HumanMessage / AIMessage objects and populates _message_store so that
    subsequent turns hit the fast path.
    """
    if thread_id in _message_store and _message_store[thread_id]:
        return _message_store[thread_id]
    if _env_flag("SENTIMIND_TEST_DISABLE_DB_MESSAGE_FALLBACK"):
        return list(_message_store.get(thread_id, []))

    # ── DB FALLBACK ────────────────────────────────────────────────────────
    # _message_store is empty (cold start / server restart).  Hydrate from DB.
    try:
        from ..db.client import get_prisma_client
        prisma = await get_prisma_client()
        db_messages = await prisma.message.find_many(
            where={"sessionId": thread_id},
            order={"createdAt": "asc"},
            take=_MAX_MESSAGE_HISTORY,
        )
        if db_messages:
            hydrated: list = []
            for m in db_messages:
                role    = getattr(m, "role", "user")
                content = getattr(m, "content", "") or ""
                if not content:
                    continue
                # Prisma enum values come back as strings like "MessageRole.user"
                role_str = str(role).lower()
                if "user" in role_str or "human" in role_str:
                    hydrated.append(HumanMessage(content=content))
                else:
                    hydrated.append(AIMessage(content=content))
            if hydrated:
                _message_store[thread_id] = hydrated
                print(f"[MSG_STORE] Cold-start hydration: loaded {len(hydrated)} messages "
                      f"from DB for session {thread_id[:20]}...")
                return hydrated
    except Exception as e:
        print(f"[MSG_STORE] DB fallback failed (non-fatal): {str(e)[:80]}")

    return []


# ============================================
# v6.0 FIX 4: USER EXISTENCE CACHE
# ============================================
# ensure_user_exists_cached is imported from db/client.py  skips DB after first call.


# ============================================
# CRISIS DETECTION: LLM-BASED ONLY (v7.0+)
# ============================================
# All crisis detection is now semantic and LLM-powered.
# No keyword-based heuristics  pure language understanding.
# This ensures:
#   [OK] Catches nuanced crisis language
#   [OK] No false positives from figurative speech
#   [OK] Consistent with therapeutic standards


# ============================================
# v7.0 NOTE: KEYWORD-BASED FAST-PATHS REMOVED
# ============================================
# - No more _CHATCHAT_PATTERNS keyword matching
# - No more _EMOTIONAL_MARKERS fast-path
# - All routing decisions now use LLM for semantic understanding
# This ensures:
#   [OK] No false positives from metaphorical language
#   [OK] Exercises context preserved across conversations
#   [OK] Consistent, reliable decision making
# ============================================


def _is_crisis_keyword(message: str) -> bool:
    """
    DEPRECATED - No longer using keywords for crisis detection.
    All crisis detection now runs through LLM in the pipeline.
    Kept as stub for backward compatibility.
    """
    return False  # Always delegate to LLM-based detection


def _instant_crisis_response(user_id: str, session_id: str, message: str) -> dict:
    """
    v7.0 UPDATE: No longer using instant crisis responses.
    All routing now goes through LLM pipeline for semantic crisis detection.
    DEPRECATED FUNCTION - kept for backward compatibility only.
    """
    # Always default to medium crisis level - LLM will determine actual level
    return {
        "response": None,  # LLM will generate this
        "session_id": session_id or "",
        "emotion": "sadness",
        "sentiment": "negative",
        "intensity": 0.9,
        "confidence": 1.0,
        "crisis_detected": True,
        "crisis_level": "medium",
        "tools_used": ["llm_crisis_check"],
        "node_trace": ["crisis_llm_pipeline"],
        "recommended_technique": {},
        "recommended_techniques_by_category": {},
        "alternative_techniques": [],
        "technique_reasoning": "",
        "processing_time_ms": 0,
        "emotional_trend": "stable",
        "conversation_strategy": "crisis",
        "conversation_phase": "venting",
        "technique_readiness": 0.0,
        "skip_full_pipeline": False,
    }



async def _fast_casual_response(message: str, prev_messages: list) -> str:
    """
    Single fast LLM call for chitchat messages that bypass the full pipeline.
    Uses conversation history for context so the reply feels connected.
    """
    from ..llm.groq_llm import get_chat_llm
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

    llm = get_chat_llm()
    system = SystemMessage(content=(
        "You are SentiMind, a warm and friendly AI wellness companion. "
        "This message is casual  respond naturally and briefly as a friendly companion. "
        "Do NOT analyze emotions, suggest exercises, or push therapeutic content. "
        "Keep it short (1-3 sentences), warm, and conversational."
    ))
    msgs = [system]
    # Add last 4 turns of history for continuity
    for m in prev_messages[-4:]:
        role = getattr(m, 'type', 'human')
        content = getattr(m, 'content', '')
        if content:
            msgs.append(HumanMessage(content=content) if role == 'human' else AIMessage(content=content))
    msgs.append(HumanMessage(content=message))

    try:
        response = await _invoke_chat_llm(msgs, max_tokens=int(os.getenv("SENTIMIND_BYPASS_CASUAL_MAX_TOKENS", "480")), temperature=0.6)
        return response.content if hasattr(response, 'content') else str(response)
    except Exception as e:
        print(f"[GATE] [WARN]  Casual response failed: {e}")
        return "Hey! I'm here. What's on your mind? "


def _is_obvious_chitchat(message: str) -> bool:
    """
    DEPRECATED - No longer using keywords for chitchat detection.
    LLM now handles all routing decisions for consistency.
    """
    return False  # Always return False to force LLM-based classification


async def _fast_chitchat_response(user_id: str, message: str, session_id: str) -> dict:
    """
    DEPRECATED - v7.0 removes pre-graph short-circuits.
    All routing now uses LLM in the main pipeline.
    Kept for backward compatibility only.
    """
    # This function is no longer called - LLM handles all routing
    raise NotImplementedError("Chitchat short-circuit removed in v7.0 - use LLM pipeline instead")


def _wrap_bypass_result(
    reply: str,
    session_id: str,
    node_trace_label: str,
    start_time: float,
    technique: Optional[dict] = None,
) -> dict:
    """Build a standardised result dict for all pre-graph bypass handlers."""
    proc_time = int((time.time() - start_time) * 1000)
    cat = (technique or {}).get("category", "Recommended")
    return {
        "response":                          reply,
        "session_id":                        session_id,
        "emotion":                           "neutral",
        "sentiment":                         "neutral",
        "intensity":                         0.0,
        "confidence":                        0.85,
        "crisis_detected":                   False,
        "crisis_level":                      "none",
        "tools_used":                        ["smart_pipeline_gate"],
        "node_trace":                        [node_trace_label],
        "recommended_technique":             technique or {},
        "recommended_techniques_by_category":{cat: technique} if technique else {},
        "alternative_techniques":            [],
        "technique_reasoning":               "",
        "processing_time_ms":                proc_time,
        "emotional_trend":                   "stable",
        "conversation_strategy":             "no_action",
        "conversation_phase":                "neutral",
        "technique_readiness":               0.0,
    }


def _update_message_store(
    thread_id: str, prev_messages: list, user_message: str, ai_reply: str
) -> None:
    """Append new turn to in-memory store (used by every bypass handler)."""
    all_msgs = list(prev_messages) + [
        HumanMessage(content=user_message),
        AIMessage(content=ai_reply),
    ]
    _message_store[thread_id] = all_msgs[-_MAX_MESSAGE_HISTORY:]


def _is_explicit_exercise_request(message: str) -> bool:
    return _turn_signal_explicit_exercise_request(message)


_FRESH_DISTRESS_MARKERS = (
    "panic",
    "panicking",
    "can't breathe",
    "can t breathe",
    "cant breathe",
    "terrified",
    "hopeless",
    "worthless",
    "want to die",
    "kill myself",
    "hurt myself",
    "self harm",
    "self-harm",
)

_DIRECT_HELP_REQUEST_MARKERS = (
    "what should i do",
    "what can i do",
    "how can i handle",
    "how do i deal",
    "any advice",
    "can you help",
    "suggest something",
    "give me something",
    "need something practical",
)


def _last_ai_text(messages: list) -> str:
    for message in reversed(messages or []):
        if getattr(message, "type", "") == "ai":
            return getattr(message, "content", "") or ""
    return ""


def _established_distress_anchor(session_context_state: dict) -> float:
    values = []
    for key in ("last_detected_intensity", "peak_distress_intensity"):
        try:
            value = float(session_context_state.get(key))
        except Exception:
            continue
        values.append(value)
    return max(values, default=0.0)


def _protect_contextual_followup_gate(
    gate_result: dict,
    message: str,
    prev_messages: list,
    session_context_state: dict,
) -> dict:
    """Correct obvious follow-up answers before mood analysis can overwrite anchors.

    The LLM gate can sometimes see a contextual answer like
    "i want to enjoy a lil bit but im all alone" as a fresh positive/joy
    disclosure. If there is an established distress thread and the latest
    message answers the assistant's previous question, keep the turn in the
    contextual-follow-up lane so parallel_intake inherits the anchor instead
    of rerunning mood analysis on a low-signal fragment.
    """
    route = str((gate_result or {}).get("route") or "therapeutic").lower()
    if route != "therapeutic":
        return gate_result

    # If the gate explicitly flagged a NEW emotional disclosure, do NOT correct
    # to contextual_followup — the user is sharing something genuinely new,
    # not answering the previous question.
    gate_flags = list((gate_result or {}).get("context_flags") or [])
    if "new_emotional_disclosure" in gate_flags:
        return gate_result

    if not session_context_state:
        return gate_result

    anchor = _established_distress_anchor(session_context_state)
    has_thread_context = bool(
        session_context_state.get("active_thread_summary")
        or session_context_state.get("primary_concern")
        or session_context_state.get("core_belief")
        or session_context_state.get("functional_impact")
    )
    if anchor < 0.5 and not has_thread_context:
        return gate_result

    last_question = (
        session_context_state.get("last_assistant_question")
        or extract_last_question(_last_ai_text(prev_messages))
    )
    if not last_question:
        return gate_result

    clean = plain_text(message)
    if not clean or "?" in (message or ""):
        return gate_result

    if _is_explicit_exercise_request(message):
        return gate_result
    if has_negative_feedback_signal(message) or has_positive_outcome_signal(message):
        return gate_result
    if any(marker in clean for marker in _DIRECT_HELP_REQUEST_MARKERS):
        return gate_result
    if any(marker in clean for marker in _FRESH_DISTRESS_MARKERS):
        return gate_result

    word_count = len(re.findall(r"\w+", clean))
    if word_count > 36:
        return gate_result

    corrected = dict(gate_result)
    flags = list(corrected.get("context_flags") or [])
    for flag in ("answering_previous_question", "gate_corrected_contextual_followup"):
        if flag not in flags:
            flags.append(flag)

    try:
        hint = min(float(corrected.get("intensity_hint", 0.2) or 0.2), 0.35)
    except Exception:
        hint = 0.2

    corrected.update({
        "route": "contextual_followup",
        "context_flags": flags,
        "intensity_hint": hint,
        "needs_full_pipeline": True,
        "run_full_pipeline": True,
        "should_skip_mood_analysis": True,
        "reasoning": (
            f"{corrected.get('reasoning', '')} | deterministic correction: "
            "latest message answers prior context question; preserving distress anchor"
        ).strip(" |"),
    })
    print(
        "[GATE] Corrected therapeutic -> contextual_followup "
        f"(anchor={anchor:.0%}, last_question='{str(last_question)[:60]}')"
    )
    return corrected


async def _resolve_accepted_technique_name(
    accepted: Optional[str], message: str, prev_messages: list
) -> Optional[str]:
    """
    Validate that an accept_technique route points to a real DB technique.

    The LLM gate decides whether the latest user message is an acceptance.
    This helper only resolves the technique name and validates it against the DB
    so a routed acceptance cannot invent or fallback to a random exercise.
    """
    from ..tools.technique_tools import get_technique_by_name
    import re

    candidates: list[str] = []
    if accepted:
        candidates.append(str(accepted).strip())

    # If the user explicitly typed an exercise/technique request, try the full
    # message too. Plain affirmations are resolved by the LLM gate, not by
    # keyword-matching the user text here.
    if _is_explicit_exercise_request(message):
        candidates.append(message.strip())

    # If the immediately previous assistant turn named a technique, validate
    # that candidate. This is name resolution only; acceptance routing stays in
    # the LLM gate and its context_flags.
    prev_ai_msgs = [m for m in prev_messages if getattr(m, "type", "") == "ai"]
    if prev_ai_msgs:
        prev_ai = getattr(prev_ai_msgs[-1], "content", "") or ""
        candidates.extend(re.findall(r"\*\*([^*]{2,80})\*\*", prev_ai))
        candidates.extend(re.findall(
            r"(?:share|suggest|try|practice|start|work through)\s+([A-Z][A-Za-z0-9 \-]{2,80}?)(?:\s+technique|\s+exercise|[.,?!]|$)",
            prev_ai,
        ))

    seen = set()
    for candidate in candidates:
        clean = re.sub(r"^(the|a|an)\s+", "", candidate.strip(), flags=re.I)
        clean = clean.strip(" .,!?:;\"'")
        if not clean or clean.lower() in seen:
            continue
        seen.add(clean.lower())
        try:
            technique = await get_technique_by_name(clean)
            if technique and technique.get("name"):
                return technique["name"]
        except Exception as e:
            print(f"[GATE-ROUTE] Technique validation failed for '{clean}': {e}")

    return None


def _looks_emotionally_loaded(message: str) -> bool:
    """Small deterministic guard against unsafe chitchat/list bypasses."""
    text = (message or "").lower()
    distress_markers = {
        "alone", "lonely", "sad", "depressed", "anxious", "anxiety",
        "panic", "scared", "afraid", "hopeless", "worthless", "empty",
        "crying", "overwhelmed", "stressed", "trauma", "grief", "loss",
        "hurt myself", "kill myself", "die", "suicide", "can't cope",
        "cant cope", "need help", "what should i do", "what shoudl i do",
    }
    return any(marker in text for marker in distress_markers)


def _is_memory_query_candidate(message: str) -> bool:
    """Validate memory bypasses so ordinary reflective wording is not hijacked."""
    text = (message or "").lower()
    memory_markers = {
        "remember me", "do you remember", "last time", "last session",
        "previous session", "what did we talk", "what did we discuss",
        "what have we covered", "my information", "my info", "stored about me",
        "what do you know about me",
    }
    return any(marker in text for marker in memory_markers)


def _is_list_techniques_candidate(message: str) -> bool:
    """Validate that list_techniques means browsing options, not asking for support."""
    text = (message or "").lower()
    list_markers = {
        "list", "show me exercises", "show me techniques", "what exercises",
        "what techniques", "what options", "available exercises",
        "available techniques", "all exercises", "all techniques",
    }
    return any(marker in text for marker in list_markers) or (
        "show me" in text and ("exercise" in text or "technique" in text)
    )


def _is_rejection_candidate(message: str, prev_messages: list) -> bool:
    """Validate rejection bypasses; avoid treating every 'no' as global refusal."""
    text = (message or "").lower().strip()
    rejection_markers = {
        "no exercises", "no exercise", "don't want exercises", "dont want exercises",
        "don't want exercise", "dont want exercise", "stop suggesting",
        "stop giving me", "just listen", "just want to vent", "just want to talk",
        "no thanks", "not interested", "leave me alone", "don't want help",
        "dont want help",
    }
    if any(marker in text for marker in rejection_markers):
        return True
    # A bare "no" is only a rejection when the prior assistant offered a technique.
    if text in {"no", "nope", "nah"}:
        prev_ai_msgs = [m for m in prev_messages if getattr(m, "type", "") == "ai"]
        if prev_ai_msgs:
            prev = (getattr(prev_ai_msgs[-1], "content", "") or "").lower()
            return any(k in prev for k in ("technique", "exercise", "would you like to try", "give it a try"))
    return False


def _gate_route_to_intent(route: str, confidence: float, message: str) -> str:
    """
    Convert gate route to planner intent.
    The LLM (70b) is authoritative — its route is trusted directly.
    No confidence threshold gatekeeping.
    """
    if route == "crisis":
        return "crisis_signal"
    if route == "chitchat":
        return "chitchat"
    if route == "therapeutic":
        return "therapeutic"
    if route == "contextual_followup":
        return "contextual_followup"
    if route == "technique_request":
        return "technique_request"
    if route == "technique_follow_up":
        return "technique_follow_up"
    if route == "memory_query":
        return "memory_query"
    if route == "positive_feedback":
        return "positive_feedback"
    return "therapeutic"


def _gate_state_fields(gate_result: dict) -> dict:
    """Fields from smart_pipeline_gate that must survive into graph state."""
    res = {
        "gate_route": gate_result.get("route", "therapeutic"),
        "gate_confidence": float(gate_result.get("confidence", 0.0) or 0.0),
        "gate_emotional_register": gate_result.get("emotional_register"),
        "gate_context_flags": list(gate_result.get("context_flags") or []),
        "gate_intensity_hint": gate_result.get("intensity_hint"),
        "gate_should_skip_mood_analysis": bool(gate_result.get("should_skip_mood_analysis", False)),
        "gate_needs_full_pipeline": bool(gate_result.get("needs_full_pipeline", gate_result.get("run_full_pipeline", True))),
       
  
    }
    # Propagate consent/preference fields if present in gate result
    for key in ["exercise_consent", "solution_preference", "active_issue_source", "suppression_signal", "suppressed_topic"]:
        if gate_result.get(key) not in (None, ""):
            res[key] = gate_result[key]

    # Normalize bare "denied" from the LLM gate to "denied_soft" so the planner
    # and consent_parser can match it correctly (they check for denied_soft/denied_hard).
    if res.get("exercise_consent") == "denied":
        res["exercise_consent"] = "denied_soft"

    return res



async def _memory_query_response(
    message: str, user_id: str, session_id: str, prev_messages: list, start_time: float
) -> dict:
    """Load facts + session summaries and answer the user's memory question."""
    from ..llm.groq_llm import get_chat_llm
    from langchain_core.messages import SystemMessage as SysMsg

    session_ctx = _load_session_context_state(session_id)
    latest_tech = session_ctx.get("latest_recommended_technique") or {}
    preferred = session_ctx.get("preferred_techniques") or []
    lower = (message or "").lower()
    if latest_tech and latest_tech.get("name") and any(k in lower for k in ("technique", "exercise", "breathing", "its name", "what was")):
        if "first" in lower and preferred:
            remembered = preferred[0] if isinstance(preferred[0], dict) else latest_tech
        else:
            remembered = latest_tech
        reply = f"The technique was **{remembered.get('name')}**."
        print(f"[GATE-BYPASS] memory_query answered from session technique context: {remembered.get('name')}")
        return _wrap_bypass_result(reply, session_id, "gate:memory_query_bypass", start_time)

    facts_text   = ""
    summary_text = ""
    try:
        from ..memory.explicit_facts import get_user_facts
        from ..memory.session_summarizer import get_session_summaries
        facts, summaries = await asyncio.gather(
            get_user_facts(user_id),
            get_session_summaries(user_id),
            return_exceptions=True,
        )
        facts_text   = facts    if isinstance(facts,    str) and facts.strip()    else ""
        summary_text = summaries if isinstance(summaries, str) and summaries.strip() else ""
    except Exception as mem_e:
        print(f"[GATE-BYPASS] memory_query: memory load failed (non-fatal): {mem_e}")

    memory_block = ""
    if facts_text:
        memory_block += f"WHAT I KNOW ABOUT YOU:\n{facts_text}\n\n"
    if summary_text:
        memory_block += f"OUR PREVIOUS SESSIONS:\n{summary_text[:600]}\n\n"
    if not memory_block:
        memory_block = "I don't have stored memories about you yet — this may be a new account."

    llm  = get_chat_llm()
    msgs = [SysMsg(content=(
        "You are SentiMind, a warm AI wellness companion with access to the user's stored memories.\n\n"
        f"AVAILABLE MEMORY:\n{memory_block}\n"
        "Answer the user's question honestly. If information is missing say so warmly. "
        "Keep it personal and conversational (2-4 sentences)."
    ))]
    for m in prev_messages[-4:]:
        role = getattr(m, "type", "human")
        c    = getattr(m, "content", "")
        if c:
            msgs.append(HumanMessage(content=c) if role == "human" else AIMessage(content=c))
    msgs.append(HumanMessage(content=message))

    resp  = await _invoke_chat_llm(msgs, max_tokens=int(os.getenv("SENTIMIND_BYPASS_MEMORY_MAX_TOKENS", "600")), temperature=0.5)
    reply = resp.content if hasattr(resp, "content") else str(resp)
    print(f"[GATE-BYPASS] memory_query replied in {int((time.time()-start_time)*1000)}ms")
    return _wrap_bypass_result(reply, session_id, "gate:memory_query_bypass", start_time)


async def _list_techniques_response(
    category: Optional[str], user_id: str, session_id: str, prev_messages: list, start_time: float
) -> dict:
    """Fetch all (or category-filtered) techniques from DB and present them as a formatted list."""
    from ..db.client import get_prisma_client
    from ..llm.groq_llm import get_chat_llm
    from langchain_core.messages import SystemMessage as SysMsg

    techniques = []
    try:
        prisma = await get_prisma_client()
        where: dict = {"isActive": True}
        if category:
            where["category"] = {"is": {"name": {"contains": category, "mode": "insensitive"}}}
        techniques = await prisma.technique.find_many(
            where=where, include={"category": True}, order={"avgRating": "desc"}, take=25
        )
    except Exception as db_e:
        print(f"[GATE-BYPASS] list_techniques DB error: {db_e}")

    if not techniques:
        cat_str = f'"{category}" ' if category else ""
        no_match = (
            f"I don't have any {cat_str}techniques stored yet. "
            "Try asking for a specific breathing or mindfulness technique!"
        )
        return _wrap_bypass_result(no_match, session_id, "gate:list_techniques_bypass", start_time)

    groups: dict[str, list] = {}
    for t in techniques:
        cat_name = t.category.name if t.category else "General"
        groups.setdefault(cat_name, []).append(
            f"  \u2022 **{t.name}** ({t.durationMinutes} min) \u2014 {t.brief or 'No description'}"
        )
    tech_text = "\n".join(
        f"\n**{cat}**:\n" + "\n".join(items) for cat, items in groups.items()
    )

    llm  = get_chat_llm()
    cat_str = f'"{category}"' if category else 'all available'
    msgs = [SysMsg(content=(
        f"You are SentiMind, a warm AI wellness companion.\n"
        f"The user asked for a list of {cat_str} techniques.\n\n"
        f"AVAILABLE TECHNIQUES:\n{tech_text}\n\n"
        "Present this list warmly and concisely. Group by category. "
        "Invite them to pick one to try. Keep it friendly and encouraging."
    ))]
    for m in prev_messages[-2:]:
        role = getattr(m, "type", "human")
        c    = getattr(m, "content", "")
        if c:
            msgs.append(HumanMessage(content=c) if role == "human" else AIMessage(content=c))
    msgs.append(HumanMessage(content=f"Please list the {category or 'available'} techniques"))

    resp  = await _invoke_chat_llm(msgs, max_tokens=int(os.getenv("SENTIMIND_BYPASS_LIST_MAX_TOKENS", "1024")), temperature=0.5)
    reply = resp.content if hasattr(resp, "content") else str(resp)
    print(f"[GATE-BYPASS] list_techniques replied ({len(techniques)} items) in {int((time.time()-start_time)*1000)}ms")
    return _wrap_bypass_result(reply, session_id, "gate:list_techniques_bypass", start_time)


async def _accept_technique_response(
    technique_name: Optional[str],
    user_id: str,
    session_id: str,
    prev_messages: list,
    user_message: str,
    start_time: float,
    technique_data: Optional[dict] = None,
) -> dict:
    """Acknowledge the specific DB technique the user just accepted.

    The frontend/sidebar owns step delivery from database fields; the LLM must
    not invent or narrate technique steps here.
    """
    from ..tools.technique_tools import get_technique_by_name
    from ..llm.groq_llm import get_chat_llm
    from langchain_core.messages import SystemMessage as SysMsg

    technique = technique_data
    if technique_name:
        if technique:
            print(f"[GATE-BYPASS] accept_technique: using gate-prefetched DB exercise '{technique.get('name')}'")
        else:
            try:
                technique = await get_technique_by_name(technique_name)
            except Exception as e:
                print(f"[GATE-BYPASS] accept_technique: could not fetch '{technique_name}': {e}")

    llm = get_chat_llm()

    if technique:
        steps      = technique.get("steps") or []
        _steps_formatted = ""
        if steps and isinstance(steps, list):
            _steps_formatted = "\n- Steps:\n" + "\n".join(f"  * {s}" for s in steps)
        duration = technique.get("duration_minutes", technique.get("durationMinutes", "N/A"))
        difficulty = technique.get("difficulty", "N/A")
        tech_block = (
            f"Name: {technique.get('name')}\n"
            f"Duration: {duration} min\n"
            f"Difficulty: {difficulty}\n"
            f"Category: {technique.get('category', 'N/A')}\n"
            f"Why it works: {technique.get('why_it_works', technique.get('whyItWorks', ''))}"
            f"{_steps_formatted}"
        )
        system_content = (
            f"You are SentiMind. The router has resolved the latest user message as agreement "
            f"to try {technique.get('name')}.\n\n"
            f"TECHNIQUE TO ACKNOWLEDGE:\n{tech_block}\n\n"
            "1. Respond warmly in 1 sentence (e.g. 'Great, let’s do this together!')\n"
            "2. Name the technique and present it directly in your response in the exact style as the technique panel. The database steps are general/generic, so you MUST convert each step to target the user's current specific problem/stressor (e.g., rewrite general steps to address their specific situation, feelings, or triggers inline). Use this exact style:\n"
            "   ### Exercise: <Name>\n"
            "   * **Category:** <Category>\n"
            "   * **Duration:** <Duration> min\n"
            "   * **Difficulty:** <Difficulty>\n"
            "   * **Why it helps you right now:** <Personalised explanation of why this fits their current distress/context>\n"
            "   \n"
            "   **Steps:**\n"
            "   1. <Step 1, rewritten from the generic database step to address the user's current problem specifically>\n"
            "   2. <Step 2, rewritten from the generic database step to address the user's current problem specifically>\n"
            "   ...\n"
            "3. Do NOT suggest a different technique.\n"
            "4. NEVER refer to a sidebar or panel; print everything inline."
        )
    else:
        system_content = (
            "You are SentiMind. The user may have agreed to try something, but no verified "
            "database technique is available. Do NOT invent or deliver technique steps. "
            "Briefly acknowledge and ask what they would like to explore."
        )

    msgs = [SysMsg(content=system_content)]
    for m in prev_messages[-4:]:
        role = getattr(m, "type", "human")
        c    = getattr(m, "content", "")
        if c:
            msgs.append(HumanMessage(content=c) if role == "human" else AIMessage(content=c))
    msgs.append(HumanMessage(content=user_message or "I agree to try it."))

    resp  = await _invoke_chat_llm(msgs, max_tokens=int(os.getenv("SENTIMIND_BYPASS_ACCEPT_MAX_TOKENS", "480")), temperature=0.5)
    reply = resp.content if hasattr(resp, "content") else str(resp)
    print(f"[GATE-BYPASS] accept_technique '{technique_name}' replied in {int((time.time()-start_time)*1000)}ms")
    return _wrap_bypass_result(reply, session_id, "gate:accept_technique_bypass", start_time, technique=technique)


async def _rejection_response(
    message: str, session_id: str, prev_messages: list, start_time: float
) -> dict:
    """Acknowledge rejection of exercises with empathy. No technique is suggested."""
    from ..llm.groq_llm import get_chat_llm
    from langchain_core.messages import SystemMessage as SysMsg

    llm  = get_chat_llm()
    msgs = [SysMsg(content=(
        "You are SentiMind, a caring AI wellness companion.\n"
        "The user has said they do NOT want exercises or techniques right now.\n"
        "RULES:\n"
        "1. Validate their preference warmly and without judgment.\n"
        "2. Do NOT suggest any technique, exercise, or breathing drill.\n"
        "3. Ask gently what kind of support they\u2019d prefer (e.g. talking, listening).\n"
        "4. Keep it short (2-3 sentences). Be genuinely warm and present."
    ))]
    for m in prev_messages[-4:]:
        role = getattr(m, "type", "human")
        c    = getattr(m, "content", "")
        if c:
            msgs.append(HumanMessage(content=c) if role == "human" else AIMessage(content=c))
    msgs.append(HumanMessage(content=message))

    resp  = await _invoke_chat_llm(msgs, max_tokens=int(os.getenv("SENTIMIND_BYPASS_REJECTION_MAX_TOKENS", "480")), temperature=0.5)
    reply = resp.content if hasattr(resp, "content") else str(resp)
    print(f"[GATE-BYPASS] rejection replied in {int((time.time()-start_time)*1000)}ms")
    return _wrap_bypass_result(reply, session_id, "gate:rejection_bypass", start_time)


async def _technique_rejection_response(
    message: str, session_id: str, prev_messages: list, start_time: float
) -> dict:
    """Handle rejection of a specific prior technique without escalation."""
    from ..llm.groq_llm import get_chat_llm
    from langchain_core.messages import SystemMessage as SysMsg

    session_ctx = _load_session_context_state(session_id)
    latest = session_ctx.get("latest_recommended_technique") or session_ctx.get("active_technique") or {}
    latest_name = latest.get("name") if isinstance(latest, dict) else ""

    llm = get_chat_llm()
    msgs = [SysMsg(content=(
        "You are SentiMind, a warm AI wellness companion.\n"
        "The user is rejecting or disliking a specific technique that was already offered.\n"
        f"Latest technique name: {latest_name or 'unknown'}.\n\n"
        "Rules:\n"
        "1. Treat this as mild negative feedback, not anger, crisis, or a new emotional disclosure.\n"
        "2. Acknowledge it without defensiveness.\n"
        "3. Do not suggest a replacement yet.\n"
        "4. Ask one short question about what felt unhelpful.\n"
        "5. Keep it to 2-3 sentences."
    ))]
    for m in prev_messages[-4:]:
        role = getattr(m, "type", "human")
        c = getattr(m, "content", "")
        if c:
            msgs.append(HumanMessage(content=c) if role == "human" else AIMessage(content=c))
    msgs.append(HumanMessage(content=message))

    resp = await _invoke_chat_llm(msgs, max_tokens=int(os.getenv("SENTIMIND_BYPASS_TECH_REJECTION_MAX_TOKENS", "480")), temperature=0.5)
    reply = resp.content if hasattr(resp, "content") else str(resp)
    result = _wrap_bypass_result(reply, session_id, "gate:technique_rejection_bypass", start_time)
    result.update({
        "emotion": "neutral",
        "sentiment": "negative",
        "intensity": 0.35,
        "confidence": 0.85,
    })
    print(f"[GATE-BYPASS] technique rejection replied in {int((time.time()-start_time)*1000)}ms")
    return result


async def _positive_feedback_response(
    message: str, session_id: str, prev_messages: list, start_time: float
) -> dict:
    """Warmly acknowledge that a technique or step helped."""
    from ..llm.groq_llm import get_chat_llm
    from langchain_core.messages import SystemMessage as SysMsg

    session_ctx = _load_session_context_state(session_id)
    latest = session_ctx.get("latest_recommended_technique") or session_ctx.get("active_technique") or {}
    latest_name = latest.get("name") if isinstance(latest, dict) else ""

    llm = get_chat_llm()
    msgs = [SysMsg(content=(
        "You are SentiMind, a warm AI wellness companion.\n"
        "The user is giving positive feedback after support or a technique.\n"
        f"Latest technique name: {latest_name or 'unknown'}.\n\n"
        "Rules:\n"
        "1. Respond warmly and specifically.\n"
        "2. If a latest technique name exists, mention it briefly.\n"
        "3. Do not suggest a new technique.\n"
        "4. Ask one gentle follow-up about what changed or what they noticed.\n"
        "5. Keep it to 2-3 sentences."
    ))]
    for m in prev_messages[-4:]:
        role = getattr(m, "type", "human")
        c = getattr(m, "content", "")
        if c:
            msgs.append(HumanMessage(content=c) if role == "human" else AIMessage(content=c))
    msgs.append(HumanMessage(content=message))

    resp = await _invoke_chat_llm(msgs, max_tokens=int(os.getenv("SENTIMIND_BYPASS_POSITIVE_MAX_TOKENS", "480")), temperature=0.5)
    reply = resp.content if hasattr(resp, "content") else str(resp)
    result = _wrap_bypass_result(reply, session_id, "gate:positive_feedback_bypass", start_time)
    result.update({
        "emotion": "joy",
        "sentiment": "positive",
        "intensity": 0.15,
        "confidence": 0.85,
    })
    print(f"[GATE-BYPASS] positive feedback replied in {int((time.time()-start_time)*1000)}ms")
    return result


async def _crisis_gate_response(
    message: str,
    user_id: str,
    session_id: str,
    prev_messages: list,
    start_time: float,
    gate_result: dict,
) -> dict:
    """
    Crisis fast path.

    If the smart gate has already routed the turn as crisis, do not run the
    therapeutic graph. Crisis needs safety handling and a crisis response only;
    mood/trend/clinical/distortion/technique work is not response-critical here.
    """
    metadata = gate_result.get("metadata") or {}
    crisis_level = metadata.get("crisis_level") or "medium"
    if crisis_level not in {"medium", "high"}:
        crisis_level = "medium"

    crisis_state = {
        "messages": list(prev_messages) + [HumanMessage(content=message)],
        "user_id": user_id,
        "session_id": session_id,
        "emotion": "sadness",
        "fused_emotion": "sadness",
        "raw_emotion_label": "crisis",
        "primary_sub_emotion": "hopelessness",
        "secondary_sub_emotions": ["distress"],
        "emotion_scores": {"sadness": 0.95, "fear": 0.6},
        "emotion_reasoning": "smart gate crisis route",
        "sentiment": "negative",
        "intensity": 0.95,
        "fused_intensity": 0.95,
        "confidence": gate_result.get("confidence", 0.8),
        "crisis_detected": True,
        "crisis_level": crisis_level,
        "crisis_pre_screened": True,
        "conversation_strategy": "crisis",
        "conversation_phase": "venting",
        "technique_readiness": 0.0,
        "agent_role": "crisis_support",
        "tools_used": ["smart_pipeline_gate"],
        "recommended_technique": {},
        "recommended_techniques_by_category": {},
        "alternative_techniques": [],
        "memory_context": gate_result.get("prefetched_user_context", ""),
        "prefetched_session_context": gate_result.get("prefetched_session_context", {}),
    }

    print(f"[GATE-ROUTE] Crisis fast path | level={crisis_level} | skipping therapeutic graph")
    crisis_updates = await handle_crisis(crisis_state)
    response_state = {**crisis_state, **(crisis_updates or {})}
    response_updates = await generate_response(response_state)
    final_state = {**response_state, **(response_updates or {})}

    reply = final_state.get("final_response") or (
        "I'm really glad you told me. I want to stay with you through this moment. "
        "Are you safe right now?"
    )

    if not _env_flag("SENTIMIND_DISABLE_BACKGROUND_PERSIST_FOR_TESTS"):
        try:
            asyncio.create_task(_background_persist(final_state))
        except Exception as bg_err:
            print(f"[GATE-CRISIS] Background persist scheduling failed: {bg_err}")

    result = _wrap_bypass_result(reply, session_id, "gate:crisis_fast_path", start_time)
    crisis_emotion = _clean_metadata_label(final_state.get("fused_emotion", final_state.get("emotion")), "sadness")
    crisis_primary = _clean_metadata_label(final_state.get("primary_sub_emotion"))
    result.update({
        "emotion": crisis_emotion,
        "raw_emotion_label": _clean_metadata_label(final_state.get("raw_emotion_label")),
        "emotion_label": _emotion_label(crisis_emotion, crisis_primary),
        "primary_sub_emotion": crisis_primary,
        "secondary_sub_emotions": _clean_metadata_list(final_state.get("secondary_sub_emotions", [])),
        "detected_symptoms": _clean_metadata_list(final_state.get("detected_symptoms", [])),
        "detected_behaviors": _clean_metadata_list(final_state.get("detected_behaviors", [])),
        "detected_contexts": _clean_metadata_list(final_state.get("detected_contexts", [])),
        "emotion_scores": final_state.get("emotion_scores", {}),
        "emotion_reasoning": final_state.get("emotion_reasoning"),
        "sentiment": _clean_metadata_label(final_state.get("sentiment"), "negative"),
        "intensity": final_state.get("fused_intensity", final_state.get("intensity", 0.95)),
        "confidence": final_state.get("confidence", gate_result.get("confidence", 0.8)),
        "crisis_detected": True,
        "crisis_level": final_state.get("crisis_level", crisis_level),
        "tools_used": final_state.get("tools_used", ["smart_pipeline_gate", "handle_crisis"]),
        "node_trace": ["smart_gate", "crisis_handler", "response_generator"],
        "conversation_strategy": "crisis",
        "conversation_phase": "venting",
    })
    return result



async def _background_extract_facts(user_id: str, message: str, session_id: str, anonymous_mode: bool = False) -> None:
    """Fire-and-forget wrapper for fact extraction on bypass routes."""
    if anonymous_mode:
        return
    try:
        from ..memory.explicit_facts import extract_and_save_facts
        await extract_and_save_facts(user_id, message, session_id)
    except Exception as e:
        print(f"[MEMORY:FACTS] Background extraction failed (non-fatal): {str(e)[:80]}")


async def _background_record_technique_feedback(state: dict) -> None:
    """Fire-and-forget personalization write for explicit technique feedback."""
    try:
        from ..pipeline.outcome_tracker_node import record_explicit_technique_feedback
        await record_explicit_technique_feedback(state)
    except Exception as e:
        print(f"[PERSIST] Positive technique feedback update failed (non-fatal): {str(e)[:100]}")


async def _execute_gate_route(
    gate_result: dict,
    message: str,
    user_id: str,
    actual_session_id: str,
    prev_messages: list,
    start_time: float,
    voice_features: Optional[dict] = None,
    audio_file_path: Optional[str] = None,
    anonymous_mode: bool = False,
) -> Optional[dict]:
    """
    Dispatcher: maps the gate route to the right bypass handler.
    Returns a completed result dict (bypass ran), or None (run full pipeline).
    Also updates _message_store for every bypass route.

    voice_features: when provided, all bypass handlers are skipped and None
    is returned so the full pipeline runs with voice emotion data intact.
    """
    route    = gate_result.get("route", "therapeutic")
    conf     = gate_result.get("confidence", 0.5)
    metadata = gate_result.get("metadata") or {}
    previous_context = _load_session_context_state(actual_session_id)
    prior_exercise_consent = previous_context.get("exercise_consent", "unknown")
    prior_solution_preference = previous_context.get("solution_preference", "unknown")
    prior_blocks_exercises = (
        prior_exercise_consent in {"denied_soft", "denied_hard"}
        or prior_solution_preference == "listen_only"
    )
    explicit_current_exercise_request = _is_explicit_exercise_request(message)

    if prior_blocks_exercises and not explicit_current_exercise_request:
        flags = gate_result.get("context_flags") or []
        blocked_acceptance = route in {"accept_technique", "list_techniques", "technique_request"} or (
            route == "technique_follow_up" and "accept_technique" in flags
        )
        if blocked_acceptance and "reject_technique" not in flags and "technique_rejection" not in flags:
            print(
                "[GATE-ROUTE] Technique bypass blocked by prior listen-only/exercise refusal; "
                "running full pipeline for consent-aware response"
            )
            return None

    # If voice features or an audio file are present, the full pipeline MUST run so that:
    # 1. voice_features are injected or extracted in input_state
    # 2. emotion_fusion_node CASE 0 (therapeutic voice feature passthrough) executes
    # 3. The response generator sees the voice emotion context
    # Bypass routes (chitchat, memory, list, accept, reject) are NOT voice-aware
    # and would silently drop all emotion data from the Gemini audio call.
    if voice_features or audio_file_path:
        print(f"[GATE-ROUTE] Voice message detected (audio={bool(audio_file_path)}, features={bool(voice_features)}) — forcing full pipeline (bypassing '{route}' gate)")
        return None

    result: Optional[dict] = None

    if route == "chitchat":
        # Fire-and-forget fact extraction even on bypass — LLM decides if there's a fact (skip if trivial/short)
        if not _env_flag("SENTIMIND_DISABLE_BACKGROUND_PERSIST_FOR_TESTS"):
            if len(message.split()) >= 8:
                asyncio.create_task(_background_extract_facts(user_id, message, actual_session_id, anonymous_mode))
        print(f"[GATE-ROUTE] Chitchat bypass — LLM decision trusted directly (conf={conf:.0%})")
        reply  = await _fast_casual_response(message, prev_messages)
        result = _wrap_bypass_result(reply, actual_session_id, "gate:chitchat_bypass", start_time)

    elif route == "memory_query":
        if not _env_flag("SENTIMIND_DISABLE_BACKGROUND_PERSIST_FOR_TESTS"):
            if len(message.split()) >= 8:
                asyncio.create_task(_background_extract_facts(user_id, message, actual_session_id, anonymous_mode))
        print(f"[GATE-ROUTE] Memory query bypass — LLM trusted (conf={conf:.0%})")
        result = await _memory_query_response(
            message, user_id, actual_session_id, prev_messages, start_time
        )

    elif route == "list_techniques":
        category = metadata.get("technique_category")
        print(f"[GATE-ROUTE] List techniques bypass — LLM trusted (conf={conf:.0%}) | category={category}")
        result = await _list_techniques_response(
            category, user_id, actual_session_id, prev_messages, start_time
        )

    elif route == "technique_request":
        if "list_techniques" in (gate_result.get("context_flags") or []):
            category = metadata.get("technique_category")
            print(f"[GATE-ROUTE] Technique list request bypass | category={category}")
            result = await _list_techniques_response(
                category, user_id, actual_session_id, prev_messages, start_time
            )
        elif metadata.get("accepted_technique") and _is_explicit_exercise_request(message):
            accepted = await _resolve_accepted_technique_name(
                metadata.get("accepted_technique"), message, prev_messages
            )
            if accepted:
                print(f"[GATE-ROUTE] Named technique request bypass | technique={accepted}")
                result = await _accept_technique_response(
                    accepted,
                    user_id,
                    actual_session_id,
                    prev_messages,
                    message,
                    start_time,
                    metadata.get("exercise_data"),
                )
            else:
                print("[GATE-ROUTE] Technique request continues through stage machine")
                return None
        else:
            return None

    elif route == "technique_follow_up":
        flags = gate_result.get("context_flags") or []
        if "reject_technique" in flags or "technique_rejection" in flags:
            if not _env_flag("SENTIMIND_DISABLE_BACKGROUND_PERSIST_FOR_TESTS"):
                asyncio.create_task(_background_extract_facts(user_id, message, actual_session_id, anonymous_mode))
            print(f"[GATE-ROUTE] Technique rejection bypass (conf={conf:.0%})")
            result = await _technique_rejection_response(
                message, actual_session_id, prev_messages, start_time
            )
        elif "accept_technique" in flags:
            accepted = metadata.get("accepted_technique")
            accepted = await _resolve_accepted_technique_name(accepted, message, prev_messages)
            if not accepted:
                print("[GATE-ROUTE] Technique follow-up accept needs full context")
                return None
            print(f"[GATE-ROUTE] Technique acceptance bypass | technique={accepted}")
            result = await _accept_technique_response(
                accepted,
                user_id,
                actual_session_id,
                prev_messages,
                message,
                start_time,
                metadata.get("exercise_data"),
            )
        else:
            return None

    elif route == "positive_feedback":
        if not _env_flag("SENTIMIND_DISABLE_BACKGROUND_PERSIST_FOR_TESTS"):
            asyncio.create_task(_background_extract_facts(user_id, message, actual_session_id, anonymous_mode))
        print(f"[GATE-ROUTE] Positive feedback bypass (conf={conf:.0%})")
        result = await _positive_feedback_response(
            message, actual_session_id, prev_messages, start_time
        )

    elif route == "accept_technique":
        accepted = metadata.get("accepted_technique")
        accepted = await _resolve_accepted_technique_name(accepted, message, prev_messages)
        if not accepted:
            print("[GATE-ROUTE] Accept route rejected: no real DB technique was offered/named")
            return None
        print(f"[GATE-ROUTE] Accept technique bypass | technique={accepted}")
        result = await _accept_technique_response(
            accepted,
            user_id,
            actual_session_id,
            prev_messages,
            message,
            start_time,
            metadata.get("exercise_data"),
        )

    elif route == "rejection":
        if not _env_flag("SENTIMIND_DISABLE_BACKGROUND_PERSIST_FOR_TESTS"):
            asyncio.create_task(_background_extract_facts(user_id, message, actual_session_id, anonymous_mode))
        print(f"[GATE-ROUTE] Rejection bypass — LLM trusted (conf={conf:.0%})")
        result = await _rejection_response(
            message, actual_session_id, prev_messages, start_time
        )

    elif route == "crisis":
        result = await _crisis_gate_response(
            message,
            user_id,
            actual_session_id,
            prev_messages,
            start_time,
            gate_result,
        )

    if result is not None:
        result.update(_gate_state_fields(gate_result))
        flags = gate_result.get("context_flags") or []
        if (
            route in {"accept_technique", "technique_follow_up", "technique_request"}
            and "reject_technique" not in flags
            and result.get("recommended_technique")
        ):
            _alternatives = (
                result.get("alternative_techniques")
                or previous_context.get("alternative_techniques")
                or []
            )
            _accept_task = "offer_complement_technique" if _alternatives else "continue_active_technique"
            if _accept_task == "offer_complement_technique":
                print(f"[ACCEPT] Alternatives found → transitioning to offer_complement_technique")
            result.update({
                "intent": "accept_technique",
                "conversation_stage": "FOLLOW_UP",
                "conversation_strategy": "suggest_technique",
                "needs_technique": True,
                "latest_recommended_technique": result.get("recommended_technique"),
                "active_technique": {**result.get("recommended_technique", {}), "status": "active"} if result.get("recommended_technique") else None,
                "gate_context_flags": flags or ["accept_technique"],
                "response_task": _accept_task,
                "exercise_consent": "allowed",
                "solution_preference": "exercise_requested",
                "alternative_techniques": _alternatives if _accept_task == "offer_complement_technique" else result.get("alternative_techniques", []),
            })
        elif route == "rejection" or (
            route == "technique_follow_up"
            and ("reject_technique" in flags or "technique_rejection" in flags)
        ):
            rejected = previous_context.get("latest_recommended_technique")
            result.update({
                "intent": "reject_technique",
                "conversation_stage": "FOLLOW_UP",
                "conversation_strategy": "encourage_reflection",
                "needs_technique": False,
                "latest_rejected_technique": rejected,
                "latest_recommended_technique": previous_context.get("latest_recommended_technique"),
                "gate_context_flags": flags or ["reject_technique", "technique_rejection"],
                "response_task": "handle_technique_rejection",
                "intensity": min(float(result.get("intensity", 0.0) or 0.0), 0.45),
            })
        elif route == "memory_query":
            result.update({
                "intent": "memory_query",
                "conversation_stage": "FOLLOW_UP",
                "conversation_strategy": "encourage_reflection",
                "needs_technique": False,
                "latest_recommended_technique": previous_context.get("latest_recommended_technique"),
                "latest_rejected_technique": previous_context.get("latest_rejected_technique"),
                "gate_context_flags": ["memory_query"],
                "response_task": "answer_memory_query",
            })
        elif route == "positive_feedback":
            result.update({
                "intent": "positive_feedback",
                "conversation_stage": "RECOVERY",
                "conversation_phase": "recovery",
                "conversation_strategy": "encourage_reflection",
                "needs_technique": False,
                "latest_recommended_technique": previous_context.get("latest_recommended_technique"),
                "active_technique": previous_context.get("active_technique"),
                "gate_context_flags": flags or ["positive_feedback"],
                "response_task": "positive_feedback",
                "reflection_questions_since_resolution": 0,
            })
            feedback_state = {
                **result,
                "messages": list(prev_messages) + [HumanMessage(content=message)],
                "user_id": user_id,
                "session_id": actual_session_id,
            }
            if not _env_flag("SENTIMIND_DISABLE_BACKGROUND_PERSIST_FOR_TESTS"):
                asyncio.create_task(_background_record_technique_feedback(feedback_state))
        elif route == "chitchat":
            result.update({
                "intent": "chitchat",
                "conversation_stage": "CHITCHAT",
                "needs_technique": False,
                "gate_context_flags": ["chitchat"],
                "response_task": "chitchat",
            })
        elif route == "crisis":
            result.update({
                "intent": "crisis",
                "conversation_stage": "CRISIS",
                "needs_technique": False,
                "gate_context_flags": ["crisis"],
                "response_task": "crisis_support",
            })

        # Persist the new turn into the in-memory message store
        _update_message_store(actual_session_id, prev_messages, message, result["response"])
        _remember_session_context(actual_session_id, result)

    return result  # None => caller must run full pipeline


# ============================================
# CRISIS PRE-SCREENER NODE (runs inside parallel_intake)
# ============================================

async def screen_for_crisis(state: MentalHealthState) -> dict:
    """
    LLM-BASED CRISIS PRE-SCREENER (v7.0 - NO KEYWORDS)

    Uses semantic LLM understanding instead of keyword matching.
    OpenRouter llama-3.3-70b-instruct is the sole authoritative decision maker.
    This ensures:
    - No false positives from metaphorical language
    - Nuanced understanding of intent
    - Context-aware crisis detection
    """
    from ..llm.llm_classifier import _get_crisis_classifier

    messages = state.get("messages", [])
    msg_raw = messages[-1].content.lower() if messages else ""
    user_id = state.get("user_id", "anonymous")

    # ---- Visual separator per request for clean terminal logs ----
    separator = '\u2550' * 60
    print(f"\n{separator}")
    print(f"[PIPELINE] [LAUNCH] New message | User: {user_id}")
    print(f"[PIPELINE] [MSG] Message: \"{(messages[-1].content if messages else '')[:80]}...\"")
    print(separator)
    print(f"[NODE:CRISIS_SCREENER] Running LLM-based crisis analysis (no keywords)...")

    # ---- SINGLE LAYER: OpenRouter llama-3.3-70b-instruct (semantic understanding) ----
    original_message = messages[-1].content if messages else ""
    print(f"[CRISIS_SCREENER] [BOT] Running OpenRouter llama-3.3-70b semantic analysis...")
    llm_result = await llm_crisis_check(original_message)

    if llm_result.get("crisis_detected", False):
        crisis_level = llm_result.get("crisis_level", "medium")
        source = llm_result.get("source", "llm")
        reasoning = llm_result.get("reasoning", "")
        print(f"[CRISIS_SCREENER] [ALERT] LLM detected crisis ({crisis_level})")
        if reasoning:
            print(f"[CRISIS_SCREENER]    Reasoning: {reasoning}")
        return {
            "crisis_detected": True,
            "crisis_level": crisis_level,
            "crisis_pre_screened": True,
        }

    print("[CRISIS_SCREENER] [OK] No crisis detected (LLM analysis clean)")
    return {
        "crisis_detected": False,
        "crisis_level": "none",
        "crisis_pre_screened": True,
    }


# ============================================
# ROUTING FUNCTIONS
# ============================================

def _route_after_crisis_screener(state: MentalHealthState) -> str:
    """Route to crisis_handler only for medium/high crisis. Low risk = normal pipeline."""
    crisis_level = state.get("crisis_level", "low")
    crisis_detected = state.get("crisis_detected", False)
    crisis_pre_screened = state.get("crisis_pre_screened", False)

    if crisis_pre_screened and crisis_detected and crisis_level in ("high", "medium"):
        print(f"[CRISIS_SCREENER] Routing to crisis_handler (level={crisis_level})")
        return "crisis_direct"

    if crisis_pre_screened and crisis_detected and crisis_level == "low":
        print(f"[CRISIS_SCREENER] Low-level distress  routing to normal pipeline (not a crisis)")

    return "normal"


def _route_after_analysis_and_planning(state: MentalHealthState) -> str:
    """
    Route after fused analysis_and_planning node.
    - no_action (chitchat) -> skip response_pipeline, go direct to response_generator
    - normal -> continue to response_pipeline (technique + role selection)
    """
    strategy = state.get("conversation_strategy", "ask_question")
    if strategy == "no_action":
        print(f"[BOLT] [ROUTER] Casual chitchat fast-path triggered. Skipping response_pipeline.")
        return "fast_chitchat_path"
    return "normal_therapeutic_path"


def _route_after_response_pipeline(state: MentalHealthState) -> str:
    """
    Crisis routing after response_pipeline (fused technique + role).

    Crisis is CONTENT-gated ONLY: it may be entered solely from a genuine
    self-harm / suicidal signal (deterministic safety net or an upstream
    content pre-screen). Emotional intensity or distress alone must NEVER
    route to the crisis protocol.
    """
    intensity = state.get("fused_intensity", state.get("intensity", 0.5))
    emotion = state.get("fused_emotion", state.get("emotion", "neutral"))
    crisis_detected = bool(state.get("crisis_detected", False))

    if not crisis_detected:
        print(f"[ROUTER] Normal route (emotion: {emotion}, intensity: {intensity:.0%})")
        return "response"

    crisis_level = str(state.get("crisis_level", "low")).lower()
    messages = state.get("messages", [])
    last_user = messages[-1].content if messages else ""
    # A crisis flag is honored only when backed by an actual self-harm/suicidal
    # CONTENT signal — either a content pre-screen (gate/deterministic/LLM) that
    # produced a real risk level, or the deterministic safety net matching the
    # raw message. This guarantees intensity/distress can never manufacture a crisis.
    content_signal = (
        bool(state.get("crisis_pre_screened")) and crisis_level in {"medium", "high"}
    ) or deterministic_crisis_safety_net(last_user).get("crisis_detected", False)

    if content_signal:
        print(f"[ROUTER] Crisis (content-based self-harm signal, level={crisis_level}) — routing to crisis_handler")
        return "crisis"

    print(
        f"[ROUTER] crisis flag present but NO self-harm content "
        f"(emotion={emotion}, intensity={intensity:.0%}) — distress is not a crisis; routing normal"
    )
    return "response"


# ============================================
# v6.0 GRAPH BUILDER (5 nodes, 0 checkpoints)
# ============================================

def build_graph() -> StateGraph:
    """
    Build optimized deterministic LangGraph v6.0.

    SENTIMIND v6.0 LATENCY-OPTIMIZED ARCHITECTURE:

     Graph Nodes (5):
      1. parallel_intake            4-way concurrent: crisis || context || mood || intent
      2. analysis_and_planning      FUSED: emotion_fusion + analysis + planner + activation
      3. response_pipeline          FUSED: technique_selector + role_selector
      4. response_generator         Single async Groq LLM call
      5. crisis_handler             Safety response (conditional)

     Post-Graph (background):
      parallel_persist              Fire-and-forget: profile || saver || outcome

     NO CHECKPOINTER  zero serialization overhead.
     Message history managed via _message_store dict.
    """
    print("[GRAPH] [HAMMER] Building v6.0 latency-optimized graph (5 nodes, no checkpointer)...")

    graph = StateGraph(MentalHealthState)

    # ========================================
    # ADD NODES (5 graph nodes  down from 10)
    # ========================================

    graph.add_node("run_parallel_intake", _run_parallel_intake_timed)
    graph.add_node("run_analysis_and_planning", _run_analysis_and_planning_timed)
    graph.add_node("run_response_pipeline", _run_response_pipeline_timed)
    graph.add_node("handle_crisis", _handle_crisis_timed)
    graph.add_node("generate_response", _generate_response_timed)

    # ========================================
    # ADD EDGES (v6.0 optimized flow)
    # ========================================

    # START -> run_parallel_intake (4-way: crisis + context + mood + intent)
    graph.add_edge(START, "run_parallel_intake")

    # run_parallel_intake -> EITHER run_analysis_and_planning (normal) OR handle_crisis
    graph.add_conditional_edges(
        "run_parallel_intake",
        _route_after_crisis_screener,
        {
            "crisis_direct": "handle_crisis",
            "normal": "run_analysis_and_planning"
        }
    )

    # run_analysis_and_planning -> EITHER generate_response (chitchat) OR run_response_pipeline
    graph.add_conditional_edges(
        "run_analysis_and_planning",
        _route_after_analysis_and_planning,
        {
            "fast_chitchat_path": "generate_response",
            "normal_therapeutic_path": "run_response_pipeline"
        }
    )

    # run_response_pipeline -> EITHER handle_crisis OR generate_response
    graph.add_conditional_edges(
        "run_response_pipeline",
        _route_after_response_pipeline,
        {
            "crisis": "handle_crisis",
            "response": "generate_response"
        }
    )

    # Terminal edges
    # v7.0 UPDATE: Crisis handler routes to response generator so LLM can generate crisis response
    graph.add_edge("handle_crisis", "generate_response")
    graph.add_edge("generate_response", END)

    print("[GRAPH] [OK] Graph built (5 nodes, no checkpointer, v6.0 latency-optimized)")
    return graph


# ============================================
# AGENT SINGLETON (NO CHECKPOINTER)
# ============================================

_compiled_agent = None


def get_agent():
    """
    Get or create the compiled agent (singleton pattern).
    v6.0: NO checkpointer  zero serialization overhead.
    """
    global _compiled_agent

    if _compiled_agent is None:
        print("\n" + "="*60)
        print("[AGENT] [BRAIN] Initializing SentiMind Mental Health Agent v6.0")
        print("="*60)

        try:
            graph = build_graph()

            # v6.0: Compile WITHOUT checkpointer  zero serialization overhead.
            # Message history is managed via _message_store dict.
            _compiled_agent = graph.compile()

            print("[AGENT] [OK] Agent loaded successfully (NO CHECKPOINTER)")
            print("[AGENT] [CHART] Architecture v6.0: ParallelIntake -> AnalysisAndPlanning[fused] -> ResponsePipeline[fused] -> OptimizedResponse -> Persist[bg]")
            print("[AGENT] [BOLT] Pre-graph: smart_pipeline_gate + route bypasses")
            print("[AGENT]  Graph nodes: 5 (down from 10)")
            print("="*60 + "\n")

        except Exception as e:
            print(f"[AGENT] [ERR] Failed to build agent: {e}")
            import traceback
            traceback.print_exc()
            raise

    return _compiled_agent


# ============================================
# HELPER: Build result dict from graph state
# ============================================

def _build_result_dict(result: dict, actual_session_id: str, node_trace: list, processing_time: int) -> dict:
    """Extract standardized result dict from graph state."""
    final_response = result.get("final_response", "I'm here to listen. How are you feeling? [HEART]")
    tools_used = result.get("tools_used", [])
    recommended_techniques_by_category = result.get("recommended_techniques_by_category", {})
    emotion = _clean_metadata_label(result.get("fused_emotion", result.get("emotion")), "neutral")
    primary_sub_emotion = _clean_metadata_label(result.get("primary_sub_emotion"))
    sentiment = _clean_metadata_label(result.get("sentiment"), "neutral")

    return {
        "response": final_response,
        "session_id": actual_session_id,
        "emotion": emotion,
        "raw_emotion_label": _clean_metadata_label(result.get("raw_emotion_label")),
        "emotion_label": _emotion_label(emotion, primary_sub_emotion),
        "primary_sub_emotion": primary_sub_emotion,
        "secondary_sub_emotions": _clean_metadata_list(result.get("secondary_sub_emotions", [])),
        "detected_symptoms": _clean_metadata_list(result.get("detected_symptoms", [])),
        "detected_behaviors": _clean_metadata_list(result.get("detected_behaviors", [])),
        "detected_contexts": _clean_metadata_list(result.get("detected_contexts", [])),
        "emotion_scores": result.get("emotion_scores", {}),
        "emotion_reasoning": result.get("emotion_reasoning"),
        "sentiment": sentiment,
        "intensity": result.get("fused_intensity", result.get("intensity", 0.5)),
        "confidence": result.get("confidence", 0.8),
        "crisis_detected": result.get("crisis_detected", False),
        "crisis_level": result.get("crisis_level", "low"),
        "tools_used": tools_used,
        "node_trace": node_trace,
        "recommended_technique": result.get("recommended_technique", {}),
        "technique_offered_this_turn": result.get("technique_offered_this_turn", False),
        "recommended_techniques_by_category": recommended_techniques_by_category,
        "alternative_techniques": result.get("alternative_techniques", []),
        "technique_candidates": result.get("technique_candidates", []),
        "technique_area": result.get("technique_area", []),
        "technique_plan_mode": result.get("technique_plan_mode", "single"),
        "technique_series": result.get("technique_series", []),
        "llm_selected_technique_id": result.get("llm_selected_technique_id"),
        "technique_reasoning": result.get("technique_reasoning", ""),
        "processing_time_ms": processing_time,
        "emotional_trend": result.get("emotional_trend", "stable"),
        "conversation_strategy": result.get("conversation_strategy", "validate_only"),
        "conversation_phase": result.get("conversation_phase", "venting"),
        "technique_readiness": result.get("technique_readiness", 0.0),
        "intent": result.get("intent", result.get("prefetched_intent", {}).get("intent", "")) if isinstance(result.get("prefetched_intent", {}), dict) else result.get("intent", ""),
        "conversation_stage": result.get("conversation_stage", "DISCOVERY"),
        "needs_technique": result.get("needs_technique", False),
        "primary_concern": result.get("primary_concern"),
        "concern_duration": result.get("concern_duration"),
        "triggering_subject": result.get("triggering_subject"),
        "triggering_context": result.get("triggering_context"),
        "functional_impact": result.get("functional_impact"),
        "core_belief": result.get("core_belief"),
        "latest_recommended_technique": result.get("latest_recommended_technique"),
        "latest_rejected_technique": result.get("latest_rejected_technique"),
        "preferred_techniques": result.get("preferred_techniques", []),
        "gate_route": result.get("gate_route"),
        "gate_confidence": result.get("gate_confidence"),
        "gate_context_flags": result.get("gate_context_flags", []),
        "gate_emotional_register": result.get("gate_emotional_register"),
        "gate_intensity_hint": result.get("gate_intensity_hint"),
        "gate_should_skip_mood_analysis": result.get("gate_should_skip_mood_analysis"),
        "gate_needs_full_pipeline": result.get("gate_needs_full_pipeline"),
        "latest_referenced_entity": result.get("latest_referenced_entity"),
        "active_thread_summary": result.get("active_thread_summary"),
        "last_assistant_question": result.get("last_assistant_question"),
        "expected_answer_type": result.get("expected_answer_type"),
        "last_assistant_act": result.get("last_assistant_act"),
        "resolved_user_act": result.get("resolved_user_act"),
        "response_task": result.get("response_task"),
        "question_count_since_technique": result.get("question_count_since_technique"),
        "active_technique": result.get("active_technique"),
        "compact_analysis": result.get("compact_analysis"),
        "last_detected_emotion": result.get("last_detected_emotion"),
        "last_detected_intensity": result.get("last_detected_intensity"),
        "has_voice": result.get("has_voice", False),
        "voice_transcribed": result.get("voice_transcribed", False),
        "voice_processed": result.get("voice_processed", False),
        "voice_features": result.get("voice_features"),
        "transcription": result.get("transcription", ""),
        "latency_trace": result.get("latency_trace", []),
        "latency_summary": result.get("latency_summary", {}),
        # Clinical scoring fields (PHQ-9 / GAD-7) — included so tests and the
        # frontend can observe severity changes without hitting the dashboard API.
        "clinical_severity":   result.get("clinical_severity"),
        "clinical_phq9_score": result.get("clinical_phq9_score"),
        "clinical_gad7_score": result.get("clinical_gad7_score"),
        "clinical_raw_phq9":   result.get("clinical_raw_phq9"),
        "clinical_raw_gad7":   result.get("clinical_raw_gad7"),
        "clinical_confidence": result.get("clinical_confidence"),
        "clinical_delta":      result.get("clinical_delta"),
    }


# ============================================
# v6.0 HELPER: Context Fetcher for Gate
# ============================================
async def _load_session_context_data(session_id: Optional[str], user_id: Optional[str]) -> dict:
    """
    Load COMPLETE session context (summary, description, facts) from database.
    
    This loads ALL session summary information:
    - Session summary text (high-level overview)
    - Session description (detailed notes)
    - Session facts (topics discussed this session)
    
    Returns dict with structure:
    {
        "summary": "User is sad about work stress",
        "description": "User mentioned anxiety about deadlines and lack of work-life balance...",
        "facts": [
            {"fact": "User is sad", "mention_count": 2},
            {"fact": "Exercise was suggested", "mention_count": 1}
        ],
        "formatted_context": "Full text for LLM"
    }
    """
    if not session_id:
        return {
            "summary": "",
            "description": "",
            "facts": [],
            "formatted_context": ""
        }
    
    try:
        from ..db.client import get_prisma_client
        import json
        
        prisma = await get_prisma_client()
        
        # Query SessionSummary table for this session
        # Note: Prisma Python converts model names to lowercase: sessionsummary
        try:
            session_summary = await prisma.sessionsummary.find_first(
                where={"sessionId": session_id}
            )
        except (AttributeError, Exception) as e:
            print(f"[GATE] Could not query sessionsummary: {e}")
            session_summary = None
        
        if not session_summary:
            print(f"[GATE] No session summary found for session {session_id}")
            return {
                "summary": "",
                "description": "",
                "facts": [],
                "formatted_context": ""
            }
        
        # Extract all fields
        summary_text = getattr(session_summary, 'summary', '') or ""
        
        # Session model doesn't have 'description' field, build from title
        title_text = getattr(session_summary, 'title', '') or ""
        
        # Parse techniques field (JSON array)
        techniques_data = getattr(session_summary, 'techniques', None) or []
        
        # Convert techniques to facts format
        facts = []
        if isinstance(techniques_data, list):
            facts = [{"fact": t, "mention_count": 1} for t in techniques_data if t]
        
        # Build formatted context for LLM
        context_parts = []
        
        if summary_text.strip():
            context_parts.append(f"Session Summary: {summary_text}")
        
        if title_text.strip():
            context_parts.append(f"Session Title: {title_text}")
        
        if techniques_data:
            tech_lines = [f"  - {t}" for t in techniques_data if t]
            if tech_lines:
                context_parts.append("Techniques Discussed:\n" + "\n".join(tech_lines))
        
        formatted_context = "\n\n".join(context_parts)
        
        print(f"[GATE] Session context loaded:")
        print(f"       Summary: {summary_text[:60]}..." if summary_text else "       (no summary)")
        print(f"       Title: {title_text[:60]}..." if title_text else "       (no title)")
        print(f"       Techniques: {len(techniques_data)} discussed")
        
        return {
            "summary": summary_text,
            "description": title_text,
            "facts": facts,
            "formatted_context": formatted_context
        }
    
    except Exception as e:
        print(f"[GATE] Session context load failed (non-fatal): {str(e)[:60]}")
        return {
            "summary": "",
            "description": "",
            "facts": [],
            "formatted_context": ""
        }


async def _fetch_user_context_for_gate(uid: str, session_id: Optional[str] = None) -> str:
    """
    Fetch user facts + session summaries + CURRENT session messages for the gate.
    
    Enables context-aware routing by providing:
    - User background facts (triggers, goals, patterns)
    - Previous session summaries
    - CURRENT session messages (full conversation history in THIS session)
    
    This allows smart_pipeline_gate to properly detect:
    - Follow-up to technique (\"That helped!\" vs standalone praise)
    - Technique acceptance (\"yes\" after offer vs \"yes\" in isolation)
    - Emotion progression (changes within single session)
    """
    try:
        import asyncio
        from ..memory.explicit_facts import get_user_facts
        from ..memory.session_summarizer import get_session_summaries
        
        facts, summaries = await asyncio.gather(
            get_user_facts(uid),
            get_session_summaries(uid, exclude_session_id=session_id),
            return_exceptions=True
        )
        
        parts = []
        
        if isinstance(facts, str) and facts.strip():
            parts.append(f"USER BACKGROUND:\n{facts.strip()}")
        
        if isinstance(summaries, str) and summaries.strip():
            summary_lines = summaries.strip().splitlines()
            parts.append(f"PREVIOUS SESSIONS:\n" + "\n".join(summary_lines[:16]))
        
        # Recent in-session turns are already supplied to smart_pipeline_gate via
        # recent_context from _load_messages_with_db_fallback. Avoid querying the
        # same session messages a second time unless explicitly enabled.
        if session_id and os.getenv("SENTIMIND_GATE_DB_SESSION_MESSAGES", "0").lower() in {"1", "true", "yes"}:
            try:
                from ..db.client import get_prisma_client
                
                prisma = await get_prisma_client()
                session_record = await prisma.session.find_unique(
                    where={"id": session_id},
                    include={"messages": True}
                )
                
                if session_record and session_record.messages:
                    conversation_lines = []
                    for msg in session_record.messages[-8:]:  # Last 8 messages from THIS session
                        sender = "USER" if getattr(msg, 'role', 'user') == "user" else "AI"
                        content = getattr(msg, 'content', '')[:100]
                        if content:
                            conversation_lines.append(f"{sender}: {content}")
                    
                    if conversation_lines:
                        parts.append(f"CURRENT CONVERSATION:\n" + "\n".join(conversation_lines))
            except Exception as e:
                print(f"[GATE] Session messages (non-fatal): {str(e)[:50]}")
        
        result = "\n\n".join(parts)
        if result:
            print(f"[GATE] Context loaded ({len(result)} chars): background + summaries + current session")
        return result
    except Exception as e:
        print(f"[GATE] Context fetch failed (non-fatal): {str(e)[:60]}")
        return ""


async def _execute_smart_gate(message: str, user_id: str, session_id: Optional[str], prev_messages: list) -> dict:
    """
    Helper to run the smart pipeline gate with full parallel context loading.
    Used by both streaming and non-streaming chat paths.
    """
    recent_context = " | ".join(
        f"{getattr(m, 'type', 'human').upper()}: {getattr(m, 'content', '')[:80]}"
        for m in prev_messages[-3:]
    ) if prev_messages else ""

    # PARALLEL context fetch — both DB calls run at the same time
    user_context, session_context = await asyncio.gather(
        _fetch_user_context_for_gate(user_id, session_id),
        _load_session_context_data(session_id, user_id),
    )

    print(f"[GATE] Parallel context loaded: summary='{session_context.get('summary', '')[:40]}...', "
          f"{len(session_context.get('facts', []))} facts")

    # ONE context-aware gate call  the LLM has FULL context for informed routing
    try:
        gate_result = await smart_pipeline_gate(message, recent_context, user_context, session_context)
        # Cache successful route for grace fallbacks
        if session_id and gate_result and "route" in gate_result:
            if session_id not in _session_context_store:
                _session_context_store[session_id] = {}
            _session_context_store[session_id]["last_successful_gate_route"] = gate_result["route"]
            
        gate_result["prefetched_user_context"] = user_context
        gate_result["prefetched_session_context"] = session_context
        return gate_result
    except Exception as e:
        print(f"[GATE] [ERROR] smart_pipeline_gate failed: {e}. Using cached fallback...")
        cached_route = "therapeutic"
        if session_id and session_id in _session_context_store:
            cached_route = _session_context_store[session_id].get("last_successful_gate_route", "therapeutic")
            
        fallback = {
            "route": cached_route,
            "confidence": 0.5,
            "reasoning": f"gate_error_cached_fallback_to_{cached_route}",
            "emotional_register": "concern",
            "context_flags": ["gate_error"],
            "intensity_hint": 0.45,
            "needs_full_pipeline": cached_route == "therapeutic",
            "should_skip_mood_analysis": cached_route != "therapeutic",
            "run_full_pipeline": cached_route == "therapeutic",
            "metadata": {},
            "prefetched_user_context": user_context,
            "prefetched_session_context": session_context,
        }
        return fallback


# ============================================
# MAIN CHAT FUNCTION (v6.0)
# ============================================

async def chat_with_agent(
    user_id: str,
    message: str,
    session_id: Optional[str] = None,
    audio_file_path: Optional[str] = None,
    voice_features: Optional[dict] = None,
) -> dict:
    """
    Process a user message through the mental health agent.

    v6.0 FLOW:
      1. Short-circuit check: crisis keywords -> hardcoded template (<300ms)
      2. Short-circuit check: obvious chitchat -> single LLM call (<1,500ms)
      3. Full pipeline: 5-node LangGraph graph -> response
      4. Fire-and-forget: parallel_persist runs as background task
    """
    start_time = time.time()
    latency_trace: list[dict] = []

    print("\n" + "="*60)
    print(f"[CHAT] [NEW] New message from user: {user_id}")
    print(f"[CHAT] [MSG] Message: \"{message[:80]}...\"" if len(message) > 80 else f"[CHAT] [MSG] Message: \"{message}\"")
    print("="*60)

    try:
        ensure_user_task = asyncio.create_task(ensure_user_exists_cached(user_id))

        #  SMART PIPELINE GATE 
        # Context-aware routing. user facts + session summaries are fetched
        # CONCURRENTLY (asyncio.gather), then ONE gate LLM call is made with
        # the full context. Saves 200-400ms vs the old sequential DB calls.
        stage_start = time.time()
        prev_messages = await _load_messages_with_db_fallback(session_id or "")
        print(f"[LATENCY] message_history={_elapsed_s(stage_start):.3f}s")
        _latency_mark(latency_trace, "pre_graph.message_history", stage_start, session_id=session_id or "new")

        stage_start = time.time()
        gate_result = await _execute_smart_gate(message, user_id, session_id, prev_messages)
        print(f"[LATENCY] smart_gate={_elapsed_s(stage_start):.3f}s")
        _latency_mark(
            latency_trace,
            "pre_graph.smart_gate",
            stage_start,
            route=gate_result.get("route"),
            session_id=session_id or "new",
        )

        # ── Setup session (needed for all paths) ─────────────────────────────
        stage_start = time.time()
        await ensure_user_task
        actual_session_id = session_id
        if not actual_session_id:
            new_session = await create_new_session(user_id)
            actual_session_id = new_session["id"]
        session_context_state = _load_session_context_state(actual_session_id)
        gate_result = _protect_contextual_followup_gate(
            gate_result,
            message,
            prev_messages,
            session_context_state,
        )
        turn_type_guess = _turn_type_guess_for_gate(
            message=message,
            gate_result=gate_result,
            prev_messages=prev_messages,
            session_context_state=session_context_state,
        )
        gate_result["turn_type_guess"] = turn_type_guess
        print(f"[LATENCY] session_setup={_elapsed_s(stage_start):.3f}s")
        _latency_mark(latency_trace, "pre_graph.session_setup", stage_start, session_id=actual_session_id)

        # ── Bypass dispatcher (chitchat / memory / list / accept / rejection) ─
        # VOICE GUARD: if voice_features are present, _execute_gate_route returns None
        # immediately so the full pipeline runs and emotion data is preserved.
        stage_start = time.time()
        bypass_result = await _execute_gate_route(
            gate_result, message, user_id, actual_session_id, prev_messages, start_time,
            voice_features=voice_features,
            audio_file_path=audio_file_path,
            anonymous_mode=_anonymous_mode,
        )
        print(f"[LATENCY] gate_route_dispatch={_elapsed_s(stage_start):.3f}s")
        _latency_mark(
            latency_trace,
            "pre_graph.gate_route_dispatch",
            stage_start,
            route=gate_result.get("route"),
            session_id=actual_session_id,
        )
        if bypass_result is not None:
            proc_time = int((time.time() - start_time) * 1000)
            bypass_result["processing_time_ms"] = proc_time
            _latency_mark(
                latency_trace,
                "total.chat",
                start_time,
                route=bypass_result.get("gate_route") or gate_result.get("route"),
                session_id=actual_session_id,
            )
            bypass_result["latency_trace"] = latency_trace
            bypass_result["latency_summary"] = _latency_summary(latency_trace, start_time)
            print(f"[GATE] Bypass replied in {proc_time}ms | trace={bypass_result.get('node_trace')}")
            # Bypass routes (positive_feedback, chitchat, etc.) skip the full pipeline
            # and therefore never reach the persist block below. Inject the fields that
            # session_saver requires and fire persist here so messages are always stored.
            bypass_result.setdefault("user_id", user_id)
            bypass_result.setdefault("session_id", actual_session_id)
            _bypass_messages = list(prev_messages) + [HumanMessage(content=message)]
            bypass_result.setdefault("messages", _bypass_messages)
            bypass_result.setdefault("final_response", bypass_result.get("response", ""))
            # Inject clinical state so session_saver can write the closing snapshot.
            # These fields live in the clinical session cache and session context store,
            # neither of which is available in the bypass result dict.
            _bypass_session_ctx = _load_session_context_state(actual_session_id)
            bypass_result.setdefault("session_start_clinical_score", _bypass_session_ctx.get("session_start_clinical_score"))
            bypass_result.setdefault("session_start_gad7_score", _bypass_session_ctx.get("session_start_gad7_score"))
            try:
                from ..nodes.analysis_and_planning import _clinical_session_cache
                _cached_clin = _clinical_session_cache.get(actual_session_id, {}).get("result", {})
                if _cached_clin:
                    bypass_result.setdefault("clinical_severity",   _cached_clin.get("severity", "minimal"))
                    bypass_result.setdefault("clinical_phq9_score", _cached_clin.get("phq9_total", 0))
                    bypass_result.setdefault("clinical_gad7_score", _cached_clin.get("gad7_total", 0))
                    bypass_result.setdefault("clinical_raw_phq9",   _cached_clin.get("current_phq9_total", _cached_clin.get("phq9_total", 0)))
                    bypass_result.setdefault("clinical_raw_gad7",   _cached_clin.get("current_gad7_total", _cached_clin.get("gad7_total", 0)))
                    bypass_result.setdefault("clinical_confidence", _cached_clin.get("confidence", _cached_clin.get("clinical_confidence", 0.0)))
                    bypass_result.setdefault("clinical_delta",      _cached_clin.get("clinical_delta"))
                    bypass_result.setdefault("clinical_indicators", _cached_clin.get("clinical_indicators", []))
            except Exception as _clin_inj_err:
                print(f"[GATE] [WARN] Clinical state injection skipped: {_clin_inj_err}")
            if not _env_flag("SENTIMIND_DISABLE_BACKGROUND_PERSIST_FOR_TESTS"):
                try:
                    asyncio.create_task(_background_persist(bypass_result))
                except Exception as _bg_err:
                    print(f"[GATE] [WARN] Bypass persist scheduling failed: {_bg_err}")
                # For positive_feedback bypass, also refresh the clinical cache so the
                # NEXT full-pipeline turn reads updated scores instead of stale ones.
                _bypass_route = bypass_result.get("gate_route", "") or gate_result.get("route", "")
                if "positive_feedback" in _bypass_route:
                    try:
                        from ..nodes.analysis_and_planning import _refresh_clinical_cache, _clinical_session_cache
                        _session_ctx_for_clinical = _load_session_context_state(actual_session_id)
                        _recent_ctx_str = "\n".join(
                            f"{'User' if getattr(m, 'type', '') == 'human' else 'Assistant'}: "
                            f"{str(getattr(m, 'content', ''))[:150]}"
                            for m in prev_messages[-5:] if getattr(m, "content", "")
                        )
                        asyncio.create_task(_refresh_clinical_cache(
                            session_id=actual_session_id,
                            user_id=user_id,
                            message=message,
                            recent_context=_recent_ctx_str,
                            emotion="neutral",
                            intensity=0.3,
                            emotional_trend="stable",
                            session_start_score=_session_ctx_for_clinical.get("session_start_clinical_score"),
                        ))
                    except Exception as _clin_err:
                        print(f"[GATE] [WARN] Clinical cache refresh skipped: {_clin_err}")
            return bypass_result
        #  THERAPEUTIC / CRISIS: fall through to full graph 
        gate_route = gate_result.get("route", "therapeutic")
        gate_conf  = gate_result.get("confidence", 0.5)
        print(f"[GATE] [PLAY] Route={gate_route.upper()} — running full pipeline")

        agent = get_agent()
        thread_id = actual_session_id
        print(f"[CHAT] [LINK] Session: {actual_session_id}")

        # Already loaded above (before bypass check) — reuse for pipeline input
        prev_messages_full = prev_messages
        session_context_state = _load_session_context_state(actual_session_id)

        # Gate intent is AUTHORITATIVE — planner will see source="smart_gate" and
        # skip its own duplicate llm_intent_check call entirely.
        # For chitchat that didn’t clear the bypass threshold (conf 0.55–0.69),
        # forwarding "chitchat" lets the planner fast-path to no_action without
        # a second LLM call.
        _gate_to_intent_map = {
            "chitchat":    "chitchat",
            "therapeutic": "venting",   # planner does finer sub-classification
            "crisis":      "crisis_signal",
        }
        gate_prefetched_intent = {
            "intent": _gate_route_to_intent(gate_route, gate_conf, message),
            "confidence": gate_conf,
            "source": "smart_gate",   # AUTHORITATIVE — planner skips duplicate LLM call
        }

        # Load anonymous mode flag so downstream nodes can skip long-term storage.
        _anonymous_mode = False
        try:
            from ..api.helpers import _read_profile_setting_overrides
            from ..db.client import get_prisma_client as _get_prisma_for_anon
            _anon_prisma = await _get_prisma_for_anon()
            _prefs = await _read_profile_setting_overrides(_anon_prisma, user_id)
            _anonymous_mode = bool(_prefs.get("anonymousMode", False))
        except Exception:
            pass

        input_state = {
            **session_context_state,
            "messages": prev_messages_full + [HumanMessage(content=message)],
            "message": message,
            "user_id": user_id,
            "session_id": actual_session_id,
            "anonymous_mode": _anonymous_mode,
            "tools_used": [],
            **_gate_state_fields(gate_result),
            "prefetched_intent": gate_prefetched_intent,  #  skips duplicate LLM call
            "prefetched_user_context": gate_result.get("prefetched_user_context", ""),
            "prefetched_session_context": gate_result.get("prefetched_session_context", {}),
            "turn_type_guess": turn_type_guess,
            "previous_turn_context": dict(session_context_state),
            "latency_trace": latency_trace,
            "session_message_count": sum(
                1 for m in prev_messages_full if getattr(m, "type", "") == "human"
            ) + 1,
        }

        if audio_file_path or voice_features:
            input_state["has_voice"] = True
            input_state["gate_needs_full_pipeline"] = True
            if audio_file_path:
                input_state["audio_file_path"] = audio_file_path
                print(f"[CHAT] [AUDIO] Audio file path included: {audio_file_path[:60]}...")
        if voice_features:
            input_state["voice_features"] = voice_features
            input_state["voice_feature_snapshot"] = voice_features
            input_state["transcription_confidence"] = _voice_confidence(voice_features.get("confidence", 0.0))
            input_state["voice_processed"] = True
            input_state["transcription"] = input_state.get("transcription") or message
            input_state["voice_distress_index"] = voice_features.get("distress_index", 0.0)
            input_state["voice_pause_density"] = voice_features.get("pause_density", 0.25)
            input_state["voice_mfcc_vector"] = voice_features.get("mfcc_vector", [0.0] * 13)
            print(
                f"[CHAT] [AUDIO] Voice features injected | Emotion: {voice_features.get('emotion')} "
                f"(conf={voice_features.get('confidence', 0):.0%})"
            )

        print(f"[CHAT] [SEARCH] Messages in context: {len(input_state['messages'])} (prev: {len(prev_messages_full)})")

        #  Run the graph (no checkpointer, no aget_state needed) 
        print("[CHAT] [LAUNCH] Invoking v6.0 graph (5 nodes, no checkpointer)...")

        # Use ainvoke  returns the full merged final state directly.
        # No checkpoint serialization at node boundaries = massive speedup.
        stage_start = time.time()
        result = await agent.ainvoke(input_state)
        print(f"[LATENCY] graph_pipeline={_elapsed_s(stage_start):.3f}s")
        latency_trace = list(result.get("latency_trace", latency_trace))
        _latency_mark(latency_trace, "graph.pipeline_total", stage_start, route=gate_route, session_id=actual_session_id)

        processing_time = int((time.time() - start_time) * 1000)
        _latency_mark(latency_trace, "total.chat", start_time, route=gate_route, session_id=actual_session_id)
        result["latency_trace"] = latency_trace
        result["latency_summary"] = _latency_summary(latency_trace, start_time)

        # Determine node trace from the strategy/crisis fields
        strategy = result.get("conversation_strategy", "")
        crisis_detected = result.get("crisis_detected", False)
        crisis_pre_screened = result.get("crisis_pre_screened", False)

        if crisis_pre_screened and crisis_detected:
            node_trace = ["parallel_intake", "crisis_handler"]
        elif strategy == "no_action":
            node_trace = ["parallel_intake", "analysis_and_planning", "response_generator"]
        else:
            node_trace = ["parallel_intake", "analysis_and_planning", "response_pipeline", "response_generator"]

        final_response = result.get("final_response", "I'm here to listen. How are you feeling? [HEART]")

        # v6.0 FIX 1: Store messages for multi-turn continuity
        all_messages = list(result.get("messages", []))
        if final_response:
            all_messages.append(AIMessage(content=final_response))
        _message_store[thread_id] = all_messages[-_MAX_MESSAGE_HISTORY:]
        _remember_session_context(thread_id, result)

        print("\n" + "-"*60)
        print(f"[CHAT] [OK] Processing complete in {processing_time}ms")
        print(f"[CHAT] [REFRESH] Node trace: {' -> '.join(node_trace)}")
        print(
            "[CHAT] [MOOD] "
            f"core={result.get('fused_emotion', result.get('emotion', 'neutral'))} | "
            f"sub={result.get('primary_sub_emotion') or 'none'} | "
            f"secondary={_fmt_list(result.get('secondary_sub_emotions'))} | "
            f"symptoms={_fmt_list(result.get('detected_symptoms'))}"
        )
        print(f"[CHAT] [MSG] Response ({len(final_response)} chars): \"{final_response}\"")
        print("-"*60 + "\n")

        # v6.0 FIX 3: Fire-and-forget persist  user gets response NOW.
        # parallel_persist runs as a background task.
        if not _env_flag("SENTIMIND_DISABLE_BACKGROUND_PERSIST_FOR_TESTS"):
            try:
                asyncio.create_task(_background_persist(result))
            except Exception as bg_err:
                print(f"[CHAT] [WARN] Background persist scheduling failed: {bg_err}")
        else:
            print("[CHAT] Background persist disabled for test run")

        return _build_result_dict(result, actual_session_id, node_trace, processing_time)

    except Exception as e:
        print(f"[CHAT] [ERR] Error: {e}")
        import traceback
        traceback.print_exc()

        return {
            "response": "I appreciate you reaching out. I'm here to support you. How are you feeling today? [HEART]",
            "session_id": session_id or f"user_{user_id}",
            "emotion": "neutral",
            "raw_emotion_label": "neutral",
            "emotion_label": "neutral",
            "primary_sub_emotion": "neutral",
            "secondary_sub_emotions": [],
            "detected_symptoms": [],
            "detected_behaviors": [],
            "detected_contexts": [],
            "emotion_scores": {"neutral": 1.0},
            "emotion_reasoning": "pipeline error fallback",
            "sentiment": "neutral",
            "intensity": 0.5,
            "confidence": 0.5,
            "crisis_detected": False,
            "crisis_level": "none",
            "conversation_strategy": "validate_only",
            "conversation_phase": "venting",
            "conversation_stage": "DISCOVERY",
            "response_task": "fallback_support",
            "gate_route": "error_fallback",
            "gate_context_flags": ["pipeline_error"],
            "node_trace": ["error_fallback"],
            "tools_used": [],
            "recommended_technique": {},
            "recommended_techniques_by_category": {},
            "alternative_techniques": [],
            "processing_time_ms": 0,
        }


async def _background_persist(state: dict):
    """
    v6.0 FIX 3: Run parallel_persist as a background task.
    The user already has their response  this just saves to DB.
    """
    try:
        updates = await run_parallel_persist(state)
        # session_saver may compute session_start_clinical_score on the first clinical turn.
        # Propagate it back to the session context store so subsequent bypass turns can read it
        # for the closing clinical snapshot (the "After Therapy" score).
        _sid = state.get("session_id")
        if _sid and isinstance(updates, dict):
            _start_phq = updates.get("session_start_clinical_score")
            _start_gad = updates.get("session_start_gad7_score")
            if _start_phq is not None:
                _ctx = _session_context_store.setdefault(_sid, {})
                if _ctx.get("session_start_clinical_score") is None:
                    _ctx["session_start_clinical_score"] = _start_phq
                    if _start_gad is not None:
                        _ctx["session_start_gad7_score"] = _start_gad
                    print(f"[PERSIST] Clinical baseline propagated to session context: PHQ-9={_start_phq}, GAD-7={_start_gad}")
        print("[PERSIST] [OK] Background persist complete")
    except Exception as e:
        print(f"[PERSIST] [WARN] Background persist error: {e}")


# ============================================
# STREAMING CHAT FUNCTION (v6.0)
# ============================================

async def chat_with_agent_streaming(
    user_id: str,
    message: str,
    session_id: Optional[str] = None,
    audio_file_path: Optional[str] = None,
    voice_features: Optional[dict] = None
):
    """
    Queue-based streaming variant of chat_with_agent (v6.0).
    Yields events: {"type": "token", "content": "..."} and {"type": "done", "metadata": {...}}
    A background worker task runs the pipeline and enqueues events.
    The outer async-generator drains the queue and yields to the HTTP response.
    """
    start_time = time.time()
    latency_trace: list[dict] = []
    token_queue: asyncio.Queue = asyncio.Queue()

    async def _graph_worker():
        try:
            #  SMART PIPELINE GATE (streaming path) 
            stage_start = time.time()
            await ensure_user_exists_cached(user_id)
            actual_session_id = session_id
            if not actual_session_id:
                new_session = await create_new_session(user_id)
                actual_session_id = new_session["id"]
            print(f"[LATENCY:STREAM] session_setup={_elapsed_s(stage_start):.3f}s")
            _latency_mark(latency_trace, "stream.pre_graph.session_setup", stage_start, session_id=actual_session_id)

            thread_id = actual_session_id
            stage_start = time.time()
            prev_messages = await _load_messages_with_db_fallback(thread_id)
            print(f"[LATENCY:STREAM] message_history={_elapsed_s(stage_start):.3f}s")
            _latency_mark(latency_trace, "stream.pre_graph.message_history", stage_start, session_id=actual_session_id)

            stage_start = time.time()
            gate_result = await _execute_smart_gate(message, user_id, actual_session_id, prev_messages)
            print(f"[LATENCY:STREAM] smart_gate={_elapsed_s(stage_start):.3f}s")
            _latency_mark(
                latency_trace,
                "stream.pre_graph.smart_gate",
                stage_start,
                route=gate_result.get("route"),
                session_id=actual_session_id,
            )

            session_context_state = _load_session_context_state(actual_session_id)
            gate_result = _protect_contextual_followup_gate(
                gate_result,
                message,
                prev_messages,
                session_context_state,
            )
            turn_type_guess = _turn_type_guess_for_gate(
                message=message,
                gate_result=gate_result,
                prev_messages=prev_messages,
                session_context_state=session_context_state,
            )
            gate_result["turn_type_guess"] = turn_type_guess
            gate_route = gate_result.get("route", "therapeutic")
            gate_conf  = gate_result.get("confidence", 0.5)

            # ── Bypass dispatcher (all non-pipeline routes) ───────────────────
            # VOICE GUARD: if voice_features are present, _execute_gate_route returns None
            # immediately so the full pipeline runs and emotion data is preserved.
            stage_start = time.time()
            bypass_result = await _execute_gate_route(
                gate_result, message, user_id, actual_session_id, prev_messages, start_time,
                voice_features=voice_features,
                audio_file_path=audio_file_path,
            )
            print(f"[LATENCY:STREAM] gate_route_dispatch={_elapsed_s(stage_start):.3f}s")
            _latency_mark(
                latency_trace,
                "stream.pre_graph.gate_route_dispatch",
                stage_start,
                route=gate_route,
                session_id=actual_session_id,
            )
            if bypass_result is not None:
                proc_time = int((time.time() - start_time) * 1000)
                bypass_result["processing_time_ms"] = proc_time
                _latency_mark(
                    latency_trace,
                    "stream.total.worker",
                    start_time,
                    route=gate_route,
                    session_id=actual_session_id,
                )
                bypass_result["latency_trace"] = latency_trace
                bypass_result["latency_summary"] = _latency_summary(latency_trace, start_time)
                reply = bypass_result["response"]
                # Defensive: normalise list/non-string content (Gemini multimodal responses)
                if not isinstance(reply, str):
                    reply = _extract_llm_str(reply) if reply else ""
                # Stream the bypass reply word-by-word (uniform UX across all routes)
                words = reply.split(" ") if reply else []
                for i, word in enumerate(words):
                    await token_queue.put({"type": "token", "content": word if i == 0 else " " + word})
                    await asyncio.sleep(0.01)
                await token_queue.put({"type": "done", "metadata": bypass_result})
                # Persist gate-bypass turn to DB (memory_query, chitchat, accept/reject, etc.)
                if not _env_flag("SENTIMIND_DISABLE_BACKGROUND_PERSIST_FOR_TESTS"):
                    _persist_state = {
                        **bypass_result,
                        "messages": list(prev_messages) + [
                            HumanMessage(content=message),
                            AIMessage(content=reply),
                        ],
                        "user_id": user_id,
                        "session_id": actual_session_id,
                        "final_response": reply,
                        "turn_type_guess": turn_type_guess,
                        "turn_type": turn_type_guess,
                    }
                    asyncio.create_task(_background_persist(_persist_state))
                    print(f"[PERSIST] [BYPASS] Scheduled DB persist for route={gate_route}")
                return

            print(f"[GATE-STREAM] [PLAY] Route={gate_route.upper()} ({gate_conf:.0%}) — running full pipeline")


            # Gate intent is AUTHORITATIVE — planner skips duplicate LLM call
            _gate_to_intent_map = {
                "chitchat":    "chitchat",
                "therapeutic": "venting",
                "crisis":      "crisis_signal",
            }
            gate_prefetched_intent = {
                "intent": _gate_route_to_intent(gate_route, gate_conf, message),
                "confidence": gate_conf,
                "source": "smart_gate",   # AUTHORITATIVE — planner skips duplicate LLM call
            }

            #  FULL PIPELINE 
            agent = get_agent()
            session_context_state = _load_session_context_state(actual_session_id)

            input_state = {
                **session_context_state,
                "messages": prev_messages + [HumanMessage(content=message)],
                "message": message,
                "user_id": user_id,
                "session_id": actual_session_id,
                "tools_used": [],
                **_gate_state_fields(gate_result),
                "prefetched_intent": gate_prefetched_intent,
                "prefetched_user_context": gate_result.get("prefetched_user_context", ""),
                "prefetched_session_context": gate_result.get("prefetched_session_context", {}),
                "turn_type_guess": turn_type_guess,
                "previous_turn_context": dict(session_context_state),
                "latency_trace": latency_trace,
                "session_message_count": sum(
                    1 for m in prev_messages if getattr(m, "type", "") == "human"
                ) + 1,
            }
            if audio_file_path or voice_features:
                input_state["has_voice"] = True
                input_state["gate_needs_full_pipeline"] = True
                if audio_file_path:
                    input_state["audio_file_path"] = audio_file_path
                    print(f"[CHAT-STREAM] [AUDIO] Audio file path included: {audio_file_path[:60]}...")
            if voice_features:
                # Backward-compatible legacy path for callers that already have
                # route-approved voice features. Normal API voice flow passes
                # audio_file_path and extracts features inside the therapeutic path.
                input_state["voice_features"] = voice_features
                input_state["voice_feature_snapshot"] = voice_features
                input_state["transcription_confidence"] = _voice_confidence(voice_features.get("confidence", 0.0))
                input_state["voice_processed"] = True
                input_state["transcription"] = input_state.get("transcription") or message
                input_state["voice_distress_index"] = voice_features.get("distress_index", 0.0)
                input_state["voice_pause_density"] = voice_features.get("pause_density", 0.25)
                input_state["voice_mfcc_vector"] = voice_features.get("mfcc_vector", [0.0] * 13)
                print(f"[CHAT-STREAM] [AUDIO] Voice features injected | Emotion: {voice_features.get('emotion')} "
                      f"(conf={voice_features.get('confidence', 0):.0%})")

            print("[CHAT-STREAM] [LAUNCH] Invoking v6.0 graph via astream_events...")

            final_state = None
            got_tokens = False
            selection_prefix_buffer = ""
            selection_prefix_checked = False

            try:
                graph_stream_start = time.time()
                async for event in agent.astream_events(input_state, version="v2"):
                    kind = event["event"]
                    if kind == "on_chat_model_stream":
                        if "final_response_llm" in event.get("tags", []):
                            chunk = event["data"]["chunk"]
                            text = _extract_llm_str(chunk)
                            if text:
                                if not selection_prefix_checked:
                                    selection_prefix_buffer += text
                                    stripped = re.sub(
                                        r"^\s*SELECTED_TECHNIQUE_ID\s*:\s*[^\s]+\s*(?:\r?\n)?",
                                        "",
                                        selection_prefix_buffer,
                                        count=1,
                                        flags=re.IGNORECASE,
                                    )
                                    if stripped != selection_prefix_buffer:
                                        selection_prefix_checked = True
                                        if stripped:
                                            got_tokens = True
                                            await token_queue.put({"type": "token", "content": stripped})
                                        selection_prefix_buffer = ""
                                        continue
                                    if "\n" not in selection_prefix_buffer and len(selection_prefix_buffer) < 96:
                                        continue
                                    selection_prefix_checked = True
                                    text = selection_prefix_buffer
                                    selection_prefix_buffer = ""
                                got_tokens = True
                                await token_queue.put({"type": "token", "content": text})
                    elif kind == "on_chain_end":
                        output = event.get("data", {}).get("output")
                        if isinstance(output, dict) and (
                            "final_response" in output
                            or "messages" in output
                            or "conversation_strategy" in output
                        ):
                            final_state = output
                if not selection_prefix_checked and selection_prefix_buffer:
                    got_tokens = True
                    await token_queue.put({"type": "token", "content": selection_prefix_buffer})
                print(f"[LATENCY:STREAM] graph_pipeline_stream={_elapsed_s(graph_stream_start):.3f}s")
                _latency_mark(
                    latency_trace,
                    "stream.graph.pipeline_events",
                    graph_stream_start,
                    route=gate_route,
                    session_id=actual_session_id,
                    streamed_tokens=got_tokens,
                )
            except Exception as stream_err:
                print(f"[CHAT-STREAM] [WARN] astream_events error: {stream_err}, falling back to ainvoke")

            # Fallback: if no final state captured, re-run with ainvoke
            if not final_state:
                print("[CHAT-STREAM] [WARN] No final state from events  running ainvoke fallback")
                stage_start = time.time()
                final_state = await agent.ainvoke(input_state)
                print(f"[LATENCY:STREAM] graph_pipeline_fallback={_elapsed_s(stage_start):.3f}s")
                _latency_mark(
                    latency_trace,
                    "stream.graph.pipeline_fallback",
                    stage_start,
                    route=gate_route,
                    session_id=actual_session_id,
                )

            if final_state:
                merged_trace = list(final_state.get("latency_trace") or latency_trace)
                for item in latency_trace:
                    if item not in merged_trace:
                        merged_trace.append(item)
                latency_trace[:] = merged_trace

            # Fallback: if no streaming tokens received, simulate word-by-word streaming
            if not got_tokens:
                fallback_resp = final_state.get("final_response") or "I'm here to listen. [HEART]"
                if fallback_resp is None:
                    fallback_resp = "I'm here to listen. [HEART]"
                words = fallback_resp.split(" ")
                for i, word in enumerate(words):
                    await token_queue.put({"type": "token", "content": word if i == 0 else " " + word})
                    await asyncio.sleep(0.008)
            elif final_state.get("complement_offer_appended"):
                # The LLM token stream finished without the queued series complement.
                # generate_response appended it to final_response — stream it now so the
                # user actually sees the second exercise offered (was silently dropped before).
                _offer_line = _build_complement_offer_line(
                    final_state.get("pending_complement_technique"),
                    final_state.get("pending_complement_signal"),
                )
                if _offer_line:
                    await token_queue.put({"type": "token", "content": "\n\n" + _offer_line})

            processing_time = int((time.time() - start_time) * 1000)
            _latency_mark(latency_trace, "stream.total.worker", start_time, route=gate_route, session_id=actual_session_id)
            final_state["latency_trace"] = latency_trace
            final_state["latency_summary"] = _latency_summary(latency_trace, start_time)
            strategy = final_state.get("conversation_strategy", "")
            crisis_detected_fs = final_state.get("crisis_detected", False)
            crisis_pre_screened = final_state.get("crisis_pre_screened", False)

            if crisis_pre_screened and crisis_detected_fs:
                node_trace = ["parallel_intake", "crisis_handler"]
            elif strategy == "no_action":
                node_trace = ["parallel_intake", "analysis_and_planning", "response_generator"]
            else:
                node_trace = ["parallel_intake", "analysis_and_planning", "response_pipeline", "response_generator"]

            final_response = final_state.get("final_response", "I'm here to listen. How are you feeling? [HEART]")
            all_messages = list(final_state.get("messages", []))
            if final_response:
                all_messages.append(AIMessage(content=final_response))
            _message_store[thread_id] = all_messages[-_MAX_MESSAGE_HISTORY:]
            _remember_session_context(thread_id, final_state)

            print(f"[CHAT-STREAM] [OK] Streaming complete in {processing_time}ms")
            print(f"[CHAT-STREAM] [REFRESH] Node trace: {' -> '.join(node_trace)}")
            print(
                "[CHAT-STREAM] [MOOD] "
                f"core={final_state.get('fused_emotion', final_state.get('emotion', 'neutral'))} | "
                f"sub={final_state.get('primary_sub_emotion') or 'none'} | "
                f"secondary={_fmt_list(final_state.get('secondary_sub_emotions'))} | "
                f"symptoms={_fmt_list(final_state.get('detected_symptoms'))}"
            )

            if not _env_flag("SENTIMIND_DISABLE_BACKGROUND_PERSIST_FOR_TESTS"):
                try:
                    asyncio.create_task(_background_persist(final_state))
                except Exception as bg_err:
                    print(f"[CHAT-STREAM] [WARN] Background persist scheduling failed: {bg_err}")

            result_dict = _build_result_dict(final_state, actual_session_id, node_trace, processing_time)
            await token_queue.put({"type": "done", "metadata": result_dict})

        except Exception as e:
            print(f"[CHAT-STREAM] [ERR] Worker error: {e}")
            import traceback
            traceback.print_exc()
            fallback_msg = "I appreciate you reaching out. I'm here to support you. How are you feeling today? [HEART]"
            await token_queue.put({"type": "token", "content": fallback_msg})
            await token_queue.put({
                "type": "done",
                "metadata": {
                    "response": fallback_msg,
                    "session_id": session_id or f"user_{user_id}",
                    "emotion": "neutral",
                    "raw_emotion_label": "neutral",
                    "emotion_label": "neutral",
                    "primary_sub_emotion": "neutral",
                    "secondary_sub_emotions": [],
                    "detected_symptoms": [],
                    "detected_behaviors": [],
                    "detected_contexts": [],
                    "emotion_scores": {"neutral": 1.0},
                    "emotion_reasoning": "stream worker error fallback",
                    "sentiment": "neutral",
                    "intensity": 0.5,
                    "confidence": 0.5,
                    "crisis_detected": False,
                    "tools_used": [],
                    "recommended_techniques_by_category": {},
                    "processing_time_ms": 0,
                }
            })

    # Launch the worker and drain the queue
    worker_task = asyncio.create_task(_graph_worker())

    while True:
        try:
            item = await asyncio.wait_for(token_queue.get(), timeout=120.0)
            yield item
            if item.get("type") == "done":
                break
        except asyncio.TimeoutError:
            print("[CHAT-STREAM] [WARN] Token queue timeout (120s)  ending stream")
            break

    # Ensure the worker completes cleanly
    try:
        await worker_task
    except Exception:
        pass

# ============================================
# HEALTH CHECK
# ============================================

def check_agent_health() -> dict:
    """Check agent health and readiness."""
    try:
        agent = get_agent()
        return {
            "status": "healthy",
            "agent_ready": agent is not None,
            "architecture": "sentimind_v6.0_latency_optimized",
            "nodes": [
                "parallel_intake",          # 4-way: crisis || context || mood || intent
                "analysis_and_planning",    # FUSED: emotion_fusion + analysis + planner + activation
                "response_pipeline",        # FUSED: technique_selector + role_selector
                "crisis_handler",
                "optimized_response_generator",
            ],
            "post_graph": ["parallel_persist (fire-and-forget)"],
            "pre_graph": ["smart_pipeline_gate", "route bypasses"],
            "parallel_tiers": 3,
            "latency_profile": "smart gate + graph stages timed in logs",
            "checkpointer": "NONE (manual message store)",
            "version": "6.0.0",
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "agent_ready": False,
        }
