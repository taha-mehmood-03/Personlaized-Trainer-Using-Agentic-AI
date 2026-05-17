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
from typing import Optional

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import StateGraph, START, END

from .state import MentalHealthState, get_initial_state
from ..nodes.crisis_handler import handle_crisis
from ..nodes.optimized_response_generator import generate_response
from ..nodes.parallel_intake import run_parallel_intake
from ..nodes.parallel_persist import run_parallel_persist
from ..nodes.analysis_and_planning import run_analysis_and_planning  # v6.0: fused
from ..nodes.response_pipeline import run_response_pipeline          # v6.0: fused
from ..db.client import ensure_user_exists_cached, create_new_session
from ..llm.llm_classifier import llm_crisis_check, smart_pipeline_gate

logger = logging.getLogger(__name__)


# ============================================
# v6.0 FIX 1: NO CHECKPOINTER  MANUAL MESSAGE STORE
# ============================================
# Instead of MemorySaver (which serializes the full 40-field state at every
# node boundary), we manage multi-turn message history with a simple dict.
# This eliminates ~3-5s of checkpoint overhead per message.

_message_store: dict[str, list] = {}    # {thread_id: [BaseMessage, ...]}
_MAX_MESSAGE_HISTORY = 20               # Rolling window per thread


def _elapsed_s(start: float) -> float:
    return time.time() - start


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
        response = await llm.ainvoke(msgs)
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


def _is_short_acceptance(message: str) -> bool:
    """True only for short affirmative replies that need prior context."""
    text = (message or "").lower().strip()
    if not text or len(text.split()) > 6:
        return False
    acceptance_signals = {
        "yes", "yes i do", "yeah", "yep", "yup", "sure", "ok", "okay",
        "please", "go ahead", "sounds good", "let's do it", "lets do it",
        "i'm ready", "im ready", "guide me", "show me",
    }
    return text in acceptance_signals or any(text.startswith(s + " ") for s in acceptance_signals)


async def _resolve_accepted_technique_name(
    accepted: Optional[str], message: str, prev_messages: list
) -> Optional[str]:
    """
    Validate that an accept_technique route points to a real DB technique.

    Generic replies like "yes i do" are only accepted when the previous assistant
    turn named an actual stored technique. This prevents random fallback delivery
    when the previous turn merely offered to "explore an idea" or do a reframe.
    """
    from ..tools.technique_tools import get_technique_by_name
    import re

    candidates: list[str] = []
    if accepted:
        candidates.append(str(accepted).strip())

    # If the user explicitly typed a name, try that too.
    if not _is_short_acceptance(message):
        candidates.append(message.strip())

    # For short yes/okay replies, inspect the last assistant turn for bolded or
    # offer-style technique names, then validate each candidate against the DB.
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
    return "venting"


async def _memory_query_response(
    message: str, user_id: str, session_id: str, prev_messages: list, start_time: float
) -> dict:
    """Load ChromaDB facts + session summaries and answer the user's memory question."""
    from ..llm.groq_llm import get_chat_llm
    from langchain_core.messages import SystemMessage as SysMsg

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

    resp  = await llm.ainvoke(msgs)
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

    resp  = await llm.ainvoke(msgs)
    reply = resp.content if hasattr(resp, "content") else str(resp)
    print(f"[GATE-BYPASS] list_techniques replied ({len(techniques)} items) in {int((time.time()-start_time)*1000)}ms")
    return _wrap_bypass_result(reply, session_id, "gate:list_techniques_bypass", start_time)


async def _accept_technique_response(
    technique_name: Optional[str],
    user_id: str,
    session_id: str,
    prev_messages: list,
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
        duration = technique.get("duration_minutes", technique.get("durationMinutes", "N/A"))
        tech_block = (
            f"Name: {technique.get('name')}\n"
            f"Duration: {duration} min\n"
            f"Category: {technique.get('category', 'N/A')}\n"
            f"Why it works: {technique.get('why_it_works', technique.get('whyItWorks', ''))}\n"
            f"Step count available in DB/sidebar: {len(steps) if isinstance(steps, list) else 0}"
        )
        system_content = (
            f"You are SentiMind. The user just said YES to trying {technique.get('name')}.\n\n"
            f"TECHNIQUE TO ACKNOWLEDGE:\n{tech_block}\n\n"
            "1. Respond warmly in 1 sentence (e.g. 'Great, let\u2019s do this together!')\n"
            "2. Name the technique and tell them the steps are ready in the exercise panel/sidebar.\n"
            "3. Do NOT suggest a different technique.\n"
            "4. Do NOT list, paraphrase, or generate steps. The database/sidebar handles steps."
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
    msgs.append(HumanMessage(content="yes"))

    resp  = await llm.ainvoke(msgs)
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

    resp  = await llm.ainvoke(msgs)
    reply = resp.content if hasattr(resp, "content") else str(resp)
    print(f"[GATE-BYPASS] rejection replied in {int((time.time()-start_time)*1000)}ms")
    return _wrap_bypass_result(reply, session_id, "gate:rejection_bypass", start_time)



async def _background_extract_facts(user_id: str, message: str, session_id: str) -> None:
    """Fire-and-forget wrapper for fact extraction on bypass routes."""
    try:
        from ..memory.explicit_facts import extract_and_save_facts
        await extract_and_save_facts(user_id, message, session_id)
    except Exception as e:
        print(f"[MEMORY:FACTS] Background extraction failed (non-fatal): {str(e)[:80]}")


async def _execute_gate_route(
    gate_result: dict,
    message: str,
    user_id: str,
    actual_session_id: str,
    prev_messages: list,
    start_time: float,
) -> Optional[dict]:
    """
    Dispatcher: maps the gate route to the right bypass handler.
    Returns a completed result dict (bypass ran), or None (run full pipeline).
    Also updates _message_store for every bypass route.
    """
    route    = gate_result.get("route", "therapeutic")
    conf     = gate_result.get("confidence", 0.5)
    metadata = gate_result.get("metadata") or {}

    result: Optional[dict] = None

    if route == "chitchat":
        if _is_short_acceptance(message):
            print("[GATE-ROUTE] Chitchat rejected: short agreement needs conversation-state handling")
            return None
        # Fire-and-forget fact extraction even on bypass — LLM decides if there's a fact
        asyncio.create_task(_background_extract_facts(user_id, message, actual_session_id))
        print(f"[GATE-ROUTE] Chitchat bypass — LLM decision trusted directly (conf={conf:.0%})")
        reply  = await _fast_casual_response(message, prev_messages)
        result = _wrap_bypass_result(reply, actual_session_id, "gate:chitchat_bypass", start_time)

    elif route == "memory_query":
        asyncio.create_task(_background_extract_facts(user_id, message, actual_session_id))
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
            start_time,
            metadata.get("exercise_data"),
        )

    elif route == "rejection":
        asyncio.create_task(_background_extract_facts(user_id, message, actual_session_id))
        print(f"[GATE-ROUTE] Rejection bypass — LLM trusted (conf={conf:.0%})")
        result = await _rejection_response(
            message, actual_session_id, prev_messages, start_time
        )

    if result is not None:
        # Persist the new turn into the in-memory message store
        _update_message_store(actual_session_id, prev_messages, message, result["response"])

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
        "crisis_pre_screened": False,
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
    Crisis Detection Router  runs after response_pipeline (fused technique + role).
    Checks fused emotion intensity for high-distress routing.
    """
    intensity = state.get("fused_intensity", state.get("intensity", 0.5))
    emotion = state.get("fused_emotion", state.get("emotion", "neutral"))
    crisis_detected = state.get("crisis_detected", False)

    if crisis_detected:
        print(f"[ROUTER] Crisis detected  routing to crisis_handler")
        return "crisis"
    elif intensity >= 0.8 and emotion in ["sadness", "fear", "anger"]:
        print(f"[ROUTER] High intensity distress route (emotion: {emotion}, intensity: {intensity:.0%})")
        return "crisis"
    else:
        print(f"[ROUTER] Normal route (emotion: {emotion}, intensity: {intensity:.0%})")
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

    graph.add_node("run_parallel_intake", run_parallel_intake)
    graph.add_node("run_analysis_and_planning", run_analysis_and_planning)      # v6.0 FUSED
    graph.add_node("run_response_pipeline", run_response_pipeline)              # v6.0 FUSED
    graph.add_node("handle_crisis", handle_crisis)
    graph.add_node("generate_response", generate_response)

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

    return {
        "response": final_response,
        "session_id": actual_session_id,
        "emotion": result.get("fused_emotion", result.get("emotion", "neutral")),
        "sentiment": result.get("sentiment", "neutral"),
        "intensity": result.get("fused_intensity", result.get("intensity", 0.5)),
        "confidence": result.get("confidence", 0.8),
        "crisis_detected": result.get("crisis_detected", False),
        "crisis_level": result.get("crisis_level", "low"),
        "tools_used": tools_used,
        "node_trace": node_trace,
        "recommended_technique": result.get("recommended_technique", {}),
        "recommended_techniques_by_category": recommended_techniques_by_category,
        "alternative_techniques": result.get("alternative_techniques", []),
        "technique_reasoning": result.get("technique_reasoning", ""),
        "processing_time_ms": processing_time,
        "emotional_trend": result.get("emotional_trend", "stable"),
        "conversation_strategy": result.get("conversation_strategy", "validate_only"),
        "conversation_phase": result.get("conversation_phase", "venting"),
        "technique_readiness": result.get("technique_readiness", 0.0),
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
            get_session_summaries(uid),
            return_exceptions=True
        )
        
        parts = []
        
        if isinstance(facts, str) and facts.strip():
            parts.append(f"USER BACKGROUND:\n{facts.strip()}")
        
        if isinstance(summaries, str) and summaries.strip():
            summary_lines = summaries.strip().splitlines()
            parts.append(f"PREVIOUS SESSIONS:\n" + "\n".join(summary_lines[:16]))
        
        # Load CURRENT session messages from database (if session_id provided)
        # This is the CRITICAL addition - gate now sees what's been discussed in THIS conversation
        if session_id:
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
    gate_result = await smart_pipeline_gate(message, recent_context, user_context, session_context)
    gate_result["prefetched_user_context"] = user_context
    gate_result["prefetched_session_context"] = session_context
    return gate_result


# ============================================
# MAIN CHAT FUNCTION (v6.0)
# ============================================

async def chat_with_agent(
    user_id: str,
    message: str,
    session_id: Optional[str] = None,
    audio_file_path: Optional[str] = None
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

        stage_start = time.time()
        gate_result = await _execute_smart_gate(message, user_id, session_id, prev_messages)
        print(f"[LATENCY] smart_gate={_elapsed_s(stage_start):.3f}s")

        # ── Setup session (needed for all paths) ─────────────────────────────
        stage_start = time.time()
        await ensure_user_task
        actual_session_id = session_id
        if not actual_session_id:
            new_session = await create_new_session(user_id)
            actual_session_id = new_session["id"]
        print(f"[LATENCY] session_setup={_elapsed_s(stage_start):.3f}s")

        # ── Bypass dispatcher (chitchat / memory / list / accept / rejection) ─
        stage_start = time.time()
        bypass_result = await _execute_gate_route(
            gate_result, message, user_id, actual_session_id, prev_messages, start_time
        )
        print(f"[LATENCY] gate_route_dispatch={_elapsed_s(stage_start):.3f}s")
        if bypass_result is not None:
            proc_time = int((time.time() - start_time) * 1000)
            bypass_result["processing_time_ms"] = proc_time
            print(f"[GATE] Bypass replied in {proc_time}ms | trace={bypass_result.get('node_trace')}")
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

        input_state = {
            "messages": prev_messages_full + [HumanMessage(content=message)],
            "user_id": user_id,
            "session_id": actual_session_id,
            "tools_used": [],
            "gate_route": gate_route,
            "prefetched_intent": gate_prefetched_intent,  #  skips duplicate LLM call
            "prefetched_user_context": gate_result.get("prefetched_user_context", ""),
            "prefetched_session_context": gate_result.get("prefetched_session_context", {}),
            "session_message_count": len(prev_messages_full) + 1,
        }

        if audio_file_path:
            input_state["audio_file_path"] = audio_file_path
            print(f"[CHAT] [AUDIO] Audio file path included: {audio_file_path[:60]}...")

        print(f"[CHAT] [SEARCH] Messages in context: {len(input_state['messages'])} (prev: {len(prev_messages_full)})")

        #  Run the graph (no checkpointer, no aget_state needed) 
        print("[CHAT] [LAUNCH] Invoking v6.0 graph (5 nodes, no checkpointer)...")

        # Use ainvoke  returns the full merged final state directly.
        # No checkpoint serialization at node boundaries = massive speedup.
        stage_start = time.time()
        result = await agent.ainvoke(input_state)
        print(f"[LATENCY] graph_pipeline={_elapsed_s(stage_start):.3f}s")

        processing_time = int((time.time() - start_time) * 1000)

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

        print("\n" + "-"*60)
        print(f"[CHAT] [OK] Processing complete in {processing_time}ms")
        print(f"[CHAT] [REFRESH] Node trace: {' -> '.join(node_trace)}")
        print(f"[CHAT] [MSG] Response: \"{final_response[:80]}...\"" if len(final_response) > 80 else f"[CHAT] [MSG] Response: \"{final_response}\"")
        print("-"*60 + "\n")

        # v6.0 FIX 3: Fire-and-forget persist  user gets response NOW.
        # parallel_persist runs as a background task.
        try:
            asyncio.create_task(_background_persist(result))
        except Exception as bg_err:
            print(f"[CHAT] [WARN] Background persist scheduling failed: {bg_err}")

        return _build_result_dict(result, actual_session_id, node_trace, processing_time)

    except Exception as e:
        print(f"[CHAT] [ERR] Error: {e}")
        import traceback
        traceback.print_exc()

        return {
            "response": "I appreciate you reaching out. I'm here to support you. How are you feeling today? [HEART]",
            "session_id": session_id or f"user_{user_id}",
            "emotion": "neutral",
            "sentiment": "neutral",
            "intensity": 0.5,
            "confidence": 0.5,
            "crisis_detected": False,
            "tools_used": [],
            "recommended_techniques_by_category": {},
            "processing_time_ms": 0,
        }


async def _background_persist(state: dict):
    """
    v6.0 FIX 3: Run parallel_persist as a background task.
    The user already has their response  this just saves to DB.
    """
    try:
        await run_parallel_persist(state)
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

            thread_id = actual_session_id
            stage_start = time.time()
            prev_messages = await _load_messages_with_db_fallback(thread_id)
            print(f"[LATENCY:STREAM] message_history={_elapsed_s(stage_start):.3f}s")

            stage_start = time.time()
            gate_result = await _execute_smart_gate(message, user_id, actual_session_id, prev_messages)
            print(f"[LATENCY:STREAM] smart_gate={_elapsed_s(stage_start):.3f}s")

            gate_route = gate_result.get("route", "therapeutic")
            gate_conf  = gate_result.get("confidence", 0.5)

            # ── Bypass dispatcher (all non-pipeline routes) ───────────────────
            stage_start = time.time()
            bypass_result = await _execute_gate_route(
                gate_result, message, user_id, actual_session_id, prev_messages, start_time
            )
            print(f"[LATENCY:STREAM] gate_route_dispatch={_elapsed_s(stage_start):.3f}s")
            if bypass_result is not None:
                proc_time = int((time.time() - start_time) * 1000)
                bypass_result["processing_time_ms"] = proc_time
                reply = bypass_result["response"]
                # Stream the bypass reply word-by-word (uniform UX across all routes)
                words = reply.split(" ") if reply else []
                for i, word in enumerate(words):
                    await token_queue.put({"type": "token", "content": word if i == 0 else " " + word})
                    await asyncio.sleep(0.01)
                await token_queue.put({"type": "done", "metadata": bypass_result})
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

            input_state = {
                "messages": prev_messages + [HumanMessage(content=message)],
                "user_id": user_id,
                "session_id": actual_session_id,
                "tools_used": [],
                "gate_route": gate_route,
                "prefetched_intent": gate_prefetched_intent,
                "prefetched_user_context": gate_result.get("prefetched_user_context", ""),
                "prefetched_session_context": gate_result.get("prefetched_session_context", {}),
                "session_message_count": len(prev_messages) + 1,
            }
            if audio_file_path:
                input_state["audio_file_path"] = audio_file_path
            if voice_features:
                # Inject pre-extracted voice features directly so parallel_intake
                # and emotion_fusion_node can use them without re-processing audio
                input_state["voice_features"] = voice_features
                input_state["voice_processed"] = True
                input_state["voice_distress_index"] = voice_features.get("distress_index", 0.0)
                input_state["voice_pause_density"] = voice_features.get("pause_density", 0.25)
                input_state["voice_mfcc_vector"] = voice_features.get("mfcc_vector", [0.0] * 13)
                input_state["has_voice"] = True
                print(f"[CHAT-STREAM] [AUDIO] Voice features injected | Emotion: {voice_features.get('emotion')} "
                      f"(conf={voice_features.get('confidence', 0):.0%})")

            print("[CHAT-STREAM] [LAUNCH] Invoking v6.0 graph via astream_events...")

            final_state = None
            got_tokens = False

            try:
                graph_stream_start = time.time()
                async for event in agent.astream_events(input_state, version="v2"):
                    kind = event["event"]
                    if kind == "on_chat_model_stream":
                        if "final_response_llm" in event.get("tags", []):
                            chunk = event["data"]["chunk"]
                            if chunk.content:
                                got_tokens = True
                                await token_queue.put({"type": "token", "content": chunk.content})
                    elif kind == "on_chain_end":
                        output = event.get("data", {}).get("output")
                        if isinstance(output, dict) and (
                            "final_response" in output
                            or "messages" in output
                            or "conversation_strategy" in output
                        ):
                            final_state = output
                print(f"[LATENCY:STREAM] graph_pipeline_stream={_elapsed_s(graph_stream_start):.3f}s")
            except Exception as stream_err:
                print(f"[CHAT-STREAM] [WARN] astream_events error: {stream_err}, falling back to ainvoke")

            # Fallback: if no final state captured, re-run with ainvoke
            if not final_state:
                print("[CHAT-STREAM] [WARN] No final state from events  running ainvoke fallback")
                stage_start = time.time()
                final_state = await agent.ainvoke(input_state)
                print(f"[LATENCY:STREAM] graph_pipeline_fallback={_elapsed_s(stage_start):.3f}s")

            # Fallback: if no streaming tokens received, simulate word-by-word streaming
            if not got_tokens:
                fallback_resp = final_state.get("final_response") or "I'm here to listen. [HEART]"
                if fallback_resp is None:
                    fallback_resp = "I'm here to listen. [HEART]"
                words = fallback_resp.split(" ")
                for i, word in enumerate(words):
                    await token_queue.put({"type": "token", "content": word if i == 0 else " " + word})
                    await asyncio.sleep(0.008)

            processing_time = int((time.time() - start_time) * 1000)
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

            print(f"[CHAT-STREAM] [OK] Streaming complete in {processing_time}ms")
            print(f"[CHAT-STREAM] [REFRESH] Node trace: {' -> '.join(node_trace)}")

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
