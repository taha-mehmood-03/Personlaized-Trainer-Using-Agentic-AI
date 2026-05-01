"""
Graph Builder - StateGraph construction and main entry points

ARCHITECTURE OVERVIEW (v6.0 — SentiMind Latency-Optimized):
The graph implements a 5-node deterministic hybrid pipeline with pre-graph
short-circuits for crisis keywords and casual chitchat.

PRE-GRAPH SHORT-CIRCUITS (before the graph runs):
  - Crisis keywords  → Hardcoded template (<300ms)
  - Casual chitchat   → Single Groq 8b call (<1,500ms)

MAIN PIPELINE (LangGraph, 5 nodes):
  1. Parallel Intake (v5.3):         4-way concurrent:
                                       • Crisis Pre-Screener (OpenRouter claude-3.5-sonnet)
                                       • Therapist Agent     (OpenRouter claude-3.5-sonnet)
                                       • Mood Analyzer       (OpenRouter claude-3-haiku)
                                       • Intent Pre-Check    (OpenRouter claude-3-haiku async)
                                       • Support Tools       (DuckDuckGo, Vector DB)
  2. Analysis & Planning [FUSED]:    emotion_fusion + parallel_analysis
                                     + conversation_planner + behavioral_activation
  3. Response Pipeline [FUSED]:      technique_selector + role_selector
  4. Response Generator:             Single async Groq LLM call
  5. Crisis Handler:                 Safety response with resources

POST-GRAPH (fire-and-forget):
  - Parallel Persist:  profile + saver + outcome (runs as background task)

v6.0 LATENCY FIXES:
  1. NO CHECKPOINTER — zero serialization overhead (was ~3-5s with MemorySaver)
  2. 5 graph nodes instead of 10 (4 fewer checkpoint events)
  3. parallel_persist runs as background task (user sees response immediately)
  4. ensure_user_exists cached (skips DB after first call)
  5. Batched Prisma writes in session_saver
  6. Pre-graph short-circuits for crisis keywords + chitchat
"""

import time
import uuid
import asyncio
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
from ..llm.llm_classifier import llm_crisis_check


# ============================================
# v6.0 FIX 1: NO CHECKPOINTER — MANUAL MESSAGE STORE
# ============================================
# Instead of MemorySaver (which serializes the full 40-field state at every
# node boundary), we manage multi-turn message history with a simple dict.
# This eliminates ~3-5s of checkpoint overhead per message.

_message_store: dict[str, list] = {}    # {thread_id: [BaseMessage, ...]}
_MAX_MESSAGE_HISTORY = 20               # Rolling window per thread


# ============================================
# v6.0 FIX 4: USER EXISTENCE CACHE
# ============================================
# ensure_user_exists_cached is imported from db/client.py — skips DB after first call.


# ============================================
# CRISIS DETECTION: LLM-BASED ONLY (v7.0+)
# ============================================
# All crisis detection is now semantic and LLM-powered.
# No keyword-based heuristics — pure language understanding.
# This ensures:
#   ✅ Catches nuanced crisis language
#   ✅ No false positives from figurative speech
#   ✅ Consistent with therapeutic standards


# ============================================
# v7.0 NOTE: KEYWORD-BASED FAST-PATHS REMOVED
# ============================================
# - No more _CHATCHAT_PATTERNS keyword matching
# - No more _EMOTIONAL_MARKERS fast-path
# - All routing decisions now use LLM for semantic understanding
# This ensures:
#   ✅ No false positives from metaphorical language
#   ✅ Exercises context preserved across conversations
#   ✅ Consistent, reliable decision making
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


# ============================================
# CRISIS PRE-SCREENER NODE (runs inside parallel_intake)
# ============================================

async def screen_for_crisis(state: MentalHealthState) -> dict:
    """
    LLM-BASED CRISIS PRE-SCREENER (v7.0 - NO KEYWORDS)

    Uses semantic LLM understanding instead of keyword matching.
    OpenRouter claude-3.5-sonnet is the sole authoritative decision maker.
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
    print(f"[PIPELINE] 🚀 New message | User: {user_id}")
    print(f"[PIPELINE] 💬 Message: \"{(messages[-1].content if messages else '')[:80]}...\"")
    print(separator)
    print(f"[NODE:CRISIS_SCREENER] Running LLM-based crisis analysis (no keywords)...")

    # ---- SINGLE LAYER: OpenRouter claude-3.5-sonnet (semantic understanding) ----
    original_message = messages[-1].content if messages else ""
    print(f"[CRISIS_SCREENER] 🤖 Running OpenRouter claude-3.5-sonnet semantic analysis...")
    llm_result = await llm_crisis_check(original_message)

    if llm_result.get("crisis_detected", False):
        crisis_level = llm_result.get("crisis_level", "medium")
        source = llm_result.get("source", "llm")
        reasoning = llm_result.get("reasoning", "")
        print(f"[CRISIS_SCREENER] 🚨 LLM detected crisis ({crisis_level})")
        if reasoning:
            print(f"[CRISIS_SCREENER]    Reasoning: {reasoning}")
        return {
            "crisis_detected": True,
            "crisis_level": crisis_level,
            "crisis_pre_screened": True,
        }

    print("[CRISIS_SCREENER] ✅ No crisis detected (LLM analysis clean)")
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
        print(f"[CRISIS_SCREENER] Low-level distress — routing to normal pipeline (not a crisis)")

    return "normal"


def _route_after_analysis_and_planning(state: MentalHealthState) -> str:
    """
    Route after fused analysis_and_planning node.
    - no_action (chitchat) → skip response_pipeline, go direct to response_generator
    - normal → continue to response_pipeline (technique + role selection)
    """
    strategy = state.get("conversation_strategy", "ask_question")
    if strategy == "no_action":
        print(f"⚡ [ROUTER] Casual chitchat fast-path triggered. Skipping response_pipeline.")
        return "fast_chitchat_path"
    return "normal_therapeutic_path"


def _route_after_response_pipeline(state: MentalHealthState) -> str:
    """
    Crisis Detection Router — runs after response_pipeline (fused technique + role).
    Checks fused emotion intensity for high-distress routing.
    """
    intensity = state.get("fused_intensity", state.get("intensity", 0.5))
    emotion = state.get("fused_emotion", state.get("emotion", "neutral"))
    crisis_detected = state.get("crisis_detected", False)

    if crisis_detected:
        print(f"[ROUTER] Crisis detected — routing to crisis_handler")
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
      1. parallel_intake           — 4-way concurrent: crisis || intake || mood || intent
      2. analysis_and_planning     — FUSED: emotion_fusion + analysis + planner + activation
      3. response_pipeline         — FUSED: technique_selector + role_selector
      4. response_generator        — Single async Groq LLM call
      5. crisis_handler            — Safety response (conditional)

     Post-Graph (background):
      parallel_persist             — Fire-and-forget: profile || saver || outcome

     NO CHECKPOINTER — zero serialization overhead.
     Message history managed via _message_store dict.
    """
    print("[GRAPH] 🔨 Building v6.0 latency-optimized graph (5 nodes, no checkpointer)...")

    graph = StateGraph(MentalHealthState)

    # ========================================
    # ADD NODES (5 graph nodes — down from 10)
    # ========================================

    graph.add_node("run_parallel_intake", run_parallel_intake)
    graph.add_node("run_analysis_and_planning", run_analysis_and_planning)      # v6.0 FUSED
    graph.add_node("run_response_pipeline", run_response_pipeline)              # v6.0 FUSED
    graph.add_node("handle_crisis", handle_crisis)
    graph.add_node("generate_response", generate_response)

    # ========================================
    # ADD EDGES (v6.0 optimized flow)
    # ========================================

    # START → run_parallel_intake (4-way: crisis + intake + mood + intent)
    graph.add_edge(START, "run_parallel_intake")

    # run_parallel_intake → EITHER run_analysis_and_planning (normal) OR handle_crisis
    graph.add_conditional_edges(
        "run_parallel_intake",
        _route_after_crisis_screener,
        {
            "crisis_direct": "handle_crisis",
            "normal": "run_analysis_and_planning"
        }
    )

    # run_analysis_and_planning → EITHER generate_response (chitchat) OR run_response_pipeline
    graph.add_conditional_edges(
        "run_analysis_and_planning",
        _route_after_analysis_and_planning,
        {
            "fast_chitchat_path": "generate_response",
            "normal_therapeutic_path": "run_response_pipeline"
        }
    )

    # run_response_pipeline → EITHER handle_crisis OR generate_response
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

    print("[GRAPH] ✅ Graph built (5 nodes, no checkpointer, v6.0 latency-optimized)")
    return graph


# ============================================
# AGENT SINGLETON (NO CHECKPOINTER)
# ============================================

_compiled_agent = None


def get_agent():
    """
    Get or create the compiled agent (singleton pattern).
    v6.0: NO checkpointer — zero serialization overhead.
    """
    global _compiled_agent

    if _compiled_agent is None:
        print("\n" + "="*60)
        print("[AGENT] 🧠 Initializing SentiMind Mental Health Agent v6.0")
        print("="*60)

        try:
            graph = build_graph()

            # v6.0: Compile WITHOUT checkpointer — zero serialization overhead.
            # Message history is managed via _message_store dict.
            _compiled_agent = graph.compile()

            print("[AGENT] ✅ Agent loaded successfully (NO CHECKPOINTER)")
            print("[AGENT] 📊 Architecture v6.0: ParallelIntake → AnalysisAndPlanning[fused] → ResponsePipeline[fused] → Response → Persist[bg]")
            print("[AGENT] ⚡ Pre-graph: crisis_shortcircuit + chitchat_shortcircuit")
            print("[AGENT] 🔗 Graph nodes: 5 (down from 10)")
            print("="*60 + "\n")

        except Exception as e:
            print(f"[AGENT] ❌ Failed to build agent: {e}")
            import traceback
            traceback.print_exc()
            raise

    return _compiled_agent


# ============================================
# HELPER: Build result dict from graph state
# ============================================

def _build_result_dict(result: dict, actual_session_id: str, node_trace: list, processing_time: int) -> dict:
    """Extract standardized result dict from graph state."""
    final_response = result.get("final_response", "I'm here to listen. How are you feeling? 💙")
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
      1. Short-circuit check: crisis keywords → hardcoded template (<300ms)
      2. Short-circuit check: obvious chitchat → single LLM call (<1,500ms)
      3. Full pipeline: 5-node LangGraph graph → response
      4. Fire-and-forget: parallel_persist runs as background task
    """
    start_time = time.time()

    print("\n" + "="*60)
    print(f"[CHAT] [NEW] New message from user: {user_id}")
    print(f"[CHAT] [MSG] Message: \"{message[:80]}...\"" if len(message) > 80 else f"[CHAT] [MSG] Message: \"{message}\"")
    print("="*60)

    try:
        # ──── v7.0: All routing now uses LLM for semantic understanding ────
        # No more keyword-based short-circuits - LLM handles all decision-making
        # This ensures consistent, reliable routing regardless of message phrasing

        # ──── FULL PIPELINE ────
        # v6.0 FIX 4: cached user check
        await ensure_user_exists_cached(user_id)

        agent = get_agent()

        # Handle session ID
        actual_session_id = session_id
        if not actual_session_id:
            new_session = await create_new_session(user_id)
            actual_session_id = new_session["id"]
            print(f"[CHAT] 🆕 Created new session: {actual_session_id}")
        else:
            print(f"[CHAT] 📎 Continuing session: {actual_session_id}")

        thread_id = actual_session_id

        # v6.0 FIX 1: Manual message history (no checkpointer).
        # Load previous messages from our lightweight in-memory store.
        prev_messages = _message_store.get(thread_id, [])

        input_state = {
            "messages": prev_messages + [HumanMessage(content=message)],
            "user_id": user_id,
            "session_id": actual_session_id,
            "tools_used": [],
        }

        if audio_file_path:
            input_state["audio_file_path"] = audio_file_path
            print(f"[CHAT] 🎤 Audio file path included: {audio_file_path[:60]}...")

        print(f"[CHAT] 🔍 Messages in context: {len(input_state['messages'])} (prev: {len(prev_messages)})")

        # ──── Run the graph (no checkpointer, no aget_state needed) ────
        print("[CHAT] 🚀 Invoking v6.0 graph (5 nodes, no checkpointer)...")

        # Use ainvoke — returns the full merged final state directly.
        # No checkpoint serialization at node boundaries = massive speedup.
        result = await agent.ainvoke(input_state)

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

        final_response = result.get("final_response", "I'm here to listen. How are you feeling? 💙")

        # v6.0 FIX 1: Store messages for multi-turn continuity
        all_messages = list(result.get("messages", []))
        if final_response:
            all_messages.append(AIMessage(content=final_response))
        _message_store[thread_id] = all_messages[-_MAX_MESSAGE_HISTORY:]

        print("\n" + "-"*60)
        print(f"[CHAT] ✅ Processing complete in {processing_time}ms")
        print(f"[CHAT] 🔄 Node trace: {' -> '.join(node_trace)}")
        print(f"[CHAT] 💬 Response: \"{final_response[:80]}...\"" if len(final_response) > 80 else f"[CHAT] 💬 Response: \"{final_response}\"")
        print("-"*60 + "\n")

        # v6.0 FIX 3: Fire-and-forget persist — user gets response NOW.
        # parallel_persist runs as a background task.
        try:
            asyncio.create_task(_background_persist(result))
        except Exception as bg_err:
            print(f"[CHAT] ⚠️ Background persist scheduling failed: {bg_err}")

        return _build_result_dict(result, actual_session_id, node_trace, processing_time)

    except Exception as e:
        print(f"[CHAT] ❌ Error: {e}")
        import traceback
        traceback.print_exc()

        return {
            "response": "I appreciate you reaching out. I'm here to support you. How are you feeling today? 💙",
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
    The user already has their response — this just saves to DB.
    """
    try:
        await run_parallel_persist(state)
        print("[PERSIST] ✅ Background persist complete")
    except Exception as e:
        print(f"[PERSIST] ⚠️ Background persist error: {e}")


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
            # ──── PRE-GRAPH SHORT-CIRCUIT 1: Crisis keywords → Routes through LLM pipeline ────
            # Note: Crisis keywords no longer bypass the pipeline; they route through LLM for response
            # The graph will detect crisis and route to response generator with LLM
            
            # ──── PRE-GRAPH SHORT-CIRCUIT 2: Obvious chitchat ────
            if _is_obvious_chitchat(message):
                result = await _fast_chitchat_response(user_id, message, session_id)
                result["processing_time_ms"] = int((time.time() - start_time) * 1000)
                words = result["response"].split(" ") if result["response"] else []
                for i, word in enumerate(words):
                    await token_queue.put({"type": "token", "content": word if i == 0 else " " + word})
                    await asyncio.sleep(0.01)
                await token_queue.put({"type": "done", "metadata": result})
                return

            # ──── FULL PIPELINE ────
            await ensure_user_exists_cached(user_id)
            agent = get_agent()

            actual_session_id = session_id
            if not actual_session_id:
                new_session = await create_new_session(user_id)
                actual_session_id = new_session["id"]

            thread_id = actual_session_id
            prev_messages = _message_store.get(thread_id, [])

            input_state = {
                "messages": prev_messages + [HumanMessage(content=message)],
                "user_id": user_id,
                "session_id": actual_session_id,
                "tools_used": [],
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
                print(f"[CHAT-STREAM] 🎤 Voice features injected | Emotion: {voice_features.get('emotion')} "
                      f"(conf={voice_features.get('confidence', 0):.0%})")

            print("[CHAT-STREAM] 🚀 Invoking v6.0 graph via astream_events...")

            final_state = None
            got_tokens = False

            try:
                async for event in agent.astream_events(input_state, version="v2"):
                    kind = event["event"]
                    if kind == "on_chat_model_stream":
                        if "final_response_llm" in event.get("tags", []):
                            chunk = event["data"]["chunk"]
                            if chunk.content:
                                got_tokens = True
                                await token_queue.put({"type": "token", "content": chunk.content})
                    elif kind == "on_chain_end":
                        if getattr(agent, "name", "LangGraph") == event["name"]:
                            final_state = event["data"].get("output")
            except Exception as stream_err:
                print(f"[CHAT-STREAM] ⚠️ astream_events error: {stream_err}, falling back to ainvoke")

            # Fallback: if no final state captured, re-run with ainvoke
            if not final_state:
                print("[CHAT-STREAM] ⚠️ No final state from events — running ainvoke fallback")
                final_state = await agent.ainvoke(input_state)

            # Fallback: if no streaming tokens received, simulate word-by-word streaming
            if not got_tokens:
                fallback_resp = final_state.get("final_response") or "I'm here to listen. 💙"
                if fallback_resp is None:
                    fallback_resp = "I'm here to listen. 💙"
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

            final_response = final_state.get("final_response", "I'm here to listen. How are you feeling? 💙")
            all_messages = list(final_state.get("messages", []))
            if final_response:
                all_messages.append(AIMessage(content=final_response))
            _message_store[thread_id] = all_messages[-_MAX_MESSAGE_HISTORY:]

            print(f"[CHAT-STREAM] ✅ Streaming complete in {processing_time}ms")
            print(f"[CHAT-STREAM] 🔄 Node trace: {' -> '.join(node_trace)}")

            try:
                asyncio.create_task(_background_persist(final_state))
            except Exception as bg_err:
                print(f"[CHAT-STREAM] ⚠️ Background persist scheduling failed: {bg_err}")

            result_dict = _build_result_dict(final_state, actual_session_id, node_trace, processing_time)
            await token_queue.put({"type": "done", "metadata": result_dict})

        except Exception as e:
            print(f"[CHAT-STREAM] ❌ Worker error: {e}")
            import traceback
            traceback.print_exc()
            fallback_msg = "I appreciate you reaching out. I'm here to support you. How are you feeling today? 💙"
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
            print("[CHAT-STREAM] ⚠️ Token queue timeout (120s) — ending stream")
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
                "parallel_intake",          # 4-way: crisis || intake || mood || intent
                "analysis_and_planning",    # FUSED: emotion_fusion + analysis + planner + activation
                "response_pipeline",        # FUSED: technique_selector + role_selector
                "crisis_handler",
                "response_generator",       # single async LLM call per message
            ],
            "post_graph": ["parallel_persist (fire-and-forget)"],
            "pre_graph": ["crisis_shortcircuit", "chitchat_shortcircuit"],
            "parallel_tiers": 3,
            "llm_calls_per_message": "1 (response_generator only, async ainvoke)",
            "checkpointer": "NONE (manual message store)",
            "version": "6.0.0",
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "agent_ready": False,
        }
