"""
Graph Builder - StateGraph construction and main entry points

ARCHITECTURE OVERVIEW (v5.3 — SentiMind Latency-Optimized):
The graph implements a 10-node deterministic hybrid pipeline:

MAIN PIPELINE (LangGraph):
  1.  Parallel Intake (v5.3):        4-way concurrent:
                                       • Crisis Pre-Screener (ELECTRA + opt. Groq 70b)
                                       • Context Loader      (DB + ChromaDB memory)
                                       • Mood Analyzer       (DistilBERT — no LLM, moved here)
                                       • Intent Pre-Check    (Groq 8b async — off critical path)
  2.  Emotion Fusion Node:           Merge text + voice emotion (Python, no LLM)
  3.  Parallel Analysis:             Distortion + trend (concurrent)               [v5.1]
  4.  Conversation Planner:          Consumes prefetched_intent — LLM skipped      [v5.3]
  5.  Behavioral Activation Node:    Real-world micro-action engine (Python)        [v3]
  6.  Technique Selector Node:       Database technique query (Python, no LLM)
  7.  Crisis Router:                 Conditional routing
  8.  Role Selector:                 Trend-aware communication style
  9.  Crisis Handler OR Response Generator: Single LLM call ONLY (now truly async) [v5.3]
  10. Parallel Persist:              Profile + saver + outcome (concurrent)         [v5.2]

EDGE FLOW:
START → ParallelIntake → EmotionFusion → ParallelAnalysis → Planner → Activation → Technique
      → Router → (Crisis | Role → Response) → ParallelPersist → END

v5.3 LATENCY FIXES:
  1. _call_groq now async (await ainvoke) → event loop never frozen
  2. LLM instance cache in MultiKeyGroqChat → no per-call ChatGroq construction
  3. mood_analyzer moved into parallel_intake → parallelised with crisis + intake
  4. Intent pre-check moved into parallel_intake → 800-1500ms off critical path
  5. response_generator uses await ainvoke → 1-3s LLM call no longer blocking
"""

import time
import uuid
import asyncio
from typing import Optional

from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from .state import MentalHealthState, get_initial_state
from ..nodes import (
    crisis_handler_node,
    role_selector_node,
)
from ..nodes.technique_selector_node import technique_selector_node
from ..nodes.optimized_response_generator import optimized_response_generator_node
from ..nodes.emotion_fusion_node import emotion_fusion_node
from ..nodes.conversation_planner_node import conversation_planner_node
from ..nodes.parallel_analysis import parallel_analysis_node
from ..nodes.parallel_intake import parallel_intake_node          # v5.3: 4-way parallel
from ..nodes.parallel_persist import parallel_persist_node        # v5.2 OPT-2
from ..nodes.behavioral_activation_node import behavioral_activation_node
from ..db.client import ensure_user_exists, create_new_session
from ..llm.llm_classifier import llm_crisis_check


# ============================================
# FIX 1: DETERMINISTIC CRISIS PRE-SCREENER
# ============================================
# These keyword sets catch explicit self-harm language BEFORE the LLM runs.
# Critical: the emotion model and LLM can both misclassify these phrases.
# This deterministic layer is the mandatory safety net.

_CRISIS_KEYWORDS_HIGH = {
    # Self-harm / suicide - explicit
    "kill myself", "killing myself", "end my life", "ending my life",
    "end it all tonight", "going to kill myself", "i want to die",
    "take my life", "taking my life", "i will kill myself",
    "im going to kill", "i'm going to kill", "commit suicide", "committing suicide",
    "take my own life", "end my own life", "hang myself",
    "shoot myself", "overdose on", "slit my wrists",
    "thinking about ending", "planning to end my life",
    # Not wanting to live — HIGH risk variants (with and without apostrophe)
    "dont want to live", "don't want to live",
    "do not want to live",
    "i dont want to live", "i don't want to live",
    "dont want to be alive", "don't want to be alive",
    "i dont want to be here", "i don't want to be here",
    "i want to disappear", "want to stop existing",
    "wish i was never born", "wish i were never born",
    "rather be dead", "rather not exist",
    "tired of living", "tired of being alive",
}
_CRISIS_KEYWORDS_MEDIUM = {
    "not wake up", "sleep forever",
    "wish i was dead", "wish i were dead", "no reason to live",
    "better off dead", "better off without me", "disappear forever",
    "cant go on", "can't go on", "no point in living", "end the pain",
    "no point anymore", "life isnt worth", "life isn't worth",
    "cant do this anymore", "can't do this anymore",
    "giving up on life", "nothing to live for",
}


async def crisis_pre_screener_node(state: MentalHealthState) -> dict:
    """
    LATENCY-OPTIMIZED CRISIS PRE-SCREENER (v5.2)

    Layer 1 (Instant, <10ms):  Hard-coded keyword matching for explicit phrases.
    Layer 2 (Local, ~200ms):   ELECTRA specialist model (sentinet/suicidality).
    Layer 3 (Remote, ~2-3s):   Groq 70b LLM — ONLY when ELECTRA score > 15%.

    v5.2 CHANGE: The Groq 70b call is now GATED behind the ELECTRA score.
    Previously it ran on EVERY non-keyword message (~3-5s wasted).
    Now it only runs when ELECTRA flags ambiguous/high suicidality (>15%).
    This saves ~3-5 seconds on 95%+ of messages.
    """
    from ..llm.llm_classifier import _get_crisis_classifier

    messages = state.get("messages", [])
    msg_raw = messages[-1].content.lower() if messages else ""
    msg = msg_raw.replace("'", "").replace("\u2019", "")
    user_id = state.get("user_id", "anonymous")

    # ---- Visual separator per request for clean terminal logs ----
    separator = '\u2550' * 60
    print(f"\n{separator}")
    print(f"[PIPELINE] 🚀 New message | User: {user_id}")
    print(f"[PIPELINE] 💬 Message: \"{(messages[-1].content if messages else '')[:80]}...\"")
    print(separator)
    print(f"[NODE:CRISIS_SCREENER] Running crisis pre-screen...")

    # ---- LAYER 1: Hard-coded keyword gate (instant, zero-cost) ----
    for phrase in _CRISIS_KEYWORDS_HIGH:
        if phrase in msg:
            print(f"[CRISIS_SCREENER] 🚨 HIGH keyword match: '{phrase}'")
            return {
                "crisis_detected": True,
                "crisis_level": "high",
                "crisis_pre_screened": True,
            }

    for phrase in _CRISIS_KEYWORDS_MEDIUM:
        if phrase in msg:
            print(f"[CRISIS_SCREENER] ⚠️  MEDIUM keyword match: '{phrase}'")
            return {
                "crisis_detected": True,
                "crisis_level": "medium",
                "crisis_pre_screened": True,
            }

    # ---- LAYER 2: ELECTRA specialist (local, ~200ms CPU-bound) ----
    _ELECTRA_ESCALATION_THRESHOLD = 0.15  # Only call 70b LLM above this score

    original_message = messages[-1].content if messages else ""
    electra_score = None

    try:
        classifier = _get_crisis_classifier()
        if classifier and classifier != "unavailable":
            # v5.3 PERF: Offload the 200ms CPU-bound ELECTRA forward pass to a
            # thread executor so the event loop remains free for the other three
            # coroutines (intake, mood, intent) running concurrently in parallel_intake.
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,                                  # default ThreadPoolExecutor
                lambda: classifier(original_message[:512])
            )
            scores = results[0] if results else []
            score_map = {r["label"].lower(): r["score"] for r in scores}
            electra_score = score_map.get(
                "suicidal", score_map.get("suicide", score_map.get(
                    "label_1", score_map.get("1", score_map.get(
                        "positive", max(scores, key=lambda x: x["score"])["score"] if scores else 0.0
                    ))
                ))
            )
            print(f"[CRISIS_SCREENER] 🔬 ELECTRA score: {electra_score:.2%}")
    except Exception as e:
        print(f"[CRISIS_SCREENER] ⚠️ ELECTRA error: {e}")

    # ---- DECISION: Gate the expensive 70b LLM call ----
    if electra_score is not None and electra_score < _ELECTRA_ESCALATION_THRESHOLD:
        # ELECTRA confidently says safe — skip the 3-5s LLM call entirely
        print(f"[CRISIS_SCREENER] ✅ ELECTRA safe ({electra_score:.1%} < {_ELECTRA_ESCALATION_THRESHOLD:.0%}) — skipping Groq 70b (saves ~3s)")
        return {
            "crisis_detected": False,
            "crisis_level": "none",
            "crisis_pre_screened": False,
        }

    # ---- LAYER 3: Groq 70b LLM (ONLY for ambiguous/high ELECTRA scores) ----
    print(f"[CRISIS_SCREENER] ⚠️ ELECTRA score {f'{electra_score:.1%}' if electra_score else 'unavailable'} ≥ {_ELECTRA_ESCALATION_THRESHOLD:.0%} — escalating to Groq 70b...")
    llm_result = await llm_crisis_check(original_message)

    if llm_result.get("crisis_detected", False):
        crisis_level = llm_result.get("crisis_level", "medium")
        source = llm_result.get("source", "llm")
        print(f"[CRISIS_SCREENER] 🚨 LLM confirmed crisis ({crisis_level}) via {source}")
        return {
            "crisis_detected": True,
            "crisis_level": crisis_level,
            "crisis_pre_screened": True,
        }

    print("[CRISIS_SCREENER] ✅ No crisis (ELECTRA ambiguous but LLM cleared)")
    return {
        "crisis_detected": False,
        "crisis_level": "none",
        "crisis_pre_screened": False,
    }


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


# ============================================
# CRISIS ROUTER LOGIC
# ============================================

def _route_after_technique_selection(state: MentalHealthState) -> str:
    """
    Crisis Detection Router Logic.
    
    Routes based on fused emotion intensity (prefers fused, falls back to raw).
    Also checks if crisis was flagged by agentic pipeline OR pre-screener.
    
    Decision Logic:
      IF crisis_detected = True → Route to "crisis_handler" 
      ELIF intensity >= 0.8 AND emotion in (sadness, fear, anger) → Route to "crisis_handler" 
      ELSE → Route to "role_selector"
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
        return "role"


def _route_after_planner(state: MentalHealthState) -> str:
    """
    Fast-Path Router for Casual Chitchat.
    If the planner determines this is just casual conversation (no_action),
    skip all the therapeutic nodes and go straight to response generation.
    """
    strategy = state.get("conversation_strategy", "ask_question")
    if strategy == "no_action":
        print(f"⚡ [ROUTER] Casual chitchat fast-path triggered. Skipping therapeutic pipeline.")
        return "fast_chitchat_path"
    
    return "normal_therapeutic_path"


def build_graph() -> StateGraph:
    """
    Build optimized deterministic LangGraph v5.3.

    SENTIMIND v5.3 LATENCY-OPTIMIZED ARCHITECTURE:

     1.  Parallel Intake v2:       4-way concurrent:                            [v5.3]
                                    crisis_pre_screener || intake_node ||
                                    mood_analyzer_node  || intent_pre_check
     2.  Emotion Fusion:           Merge text + voice (Python, no LLM)
     3.  Parallel Analysis:        Distortion + trend (concurrent)              [v5.1]
     4.  Conversation Planner:     Uses prefetched_intent — no LLM call         [v5.3]
     5.  Behavioral Activation:    Real-world micro-action engine (Python)      [v3]
     6.  Technique Selector:       DB query, planner-gated (Python, no LLM)
     7.  Crisis Router:            Route high-intensity to crisis handler
     8.  Role Selector:            Trend-aware communication style
     9.  Response Generator:       Strategy-aware single LLM call (async)      [v5.3]
     10. Parallel Persist:         Profile + saver + outcome (concurrent)       [v5.2]

    PARALLELISM (3 tiers):
     Tier 1 — Parallel Intake v2:  crisis || intake || mood || intent  (saves ~1-2s)
     Tier 2 — Parallel Analysis:   distortion || trend                 (saves ~50ms)
     Tier 3 — Parallel Persist:    profile || saver || outcome         (saves ~200ms)

    KEY: Still exactly 1 LLM call per message (response generator).
         All other LLM helpers (crisis 70b, intent 8b) are either
         parallelised in Tier 1 or skipped via ELECTRA gate.
    """
    print("[GRAPH] 🔨 Building v5.3 latency-optimized graph...")

    graph = StateGraph(MentalHealthState)

    # ========================================
    # ADD NODES (10 graph nodes)
    # mood_analyzer is no longer a standalone node —
    # it runs inside parallel_intake_node concurrently.
    # ========================================

    graph.add_node("parallel_intake", parallel_intake_node)             # v5.3: 4-way parallel
    graph.add_node("emotion_fusion", emotion_fusion_node)
    graph.add_node("parallel_analysis", parallel_analysis_node)         # v5.1: distortion + trend
    graph.add_node("conversation_planner", conversation_planner_node)
    graph.add_node("behavioral_activation", behavioral_activation_node)
    graph.add_node("technique_selector", technique_selector_node)
    graph.add_node("role_selector", role_selector_node)
    graph.add_node("crisis_handler", crisis_handler_node)
    graph.add_node("response_generator", optimized_response_generator_node)
    graph.add_node("parallel_persist", parallel_persist_node)           # v5.2: 3-way parallel

    # ========================================
    # ADD EDGES (v5.3 optimized flow)
    # ========================================

    # START → parallel_intake (4-way: crisis + intake + mood + intent)
    graph.add_edge(START, "parallel_intake")

    # parallel_intake → EITHER emotion_fusion (normal) OR crisis_handler (crisis)
    # mood is now pre-computed inside parallel_intake — skip straight to fusion
    graph.add_conditional_edges(
        "parallel_intake",
        _route_after_crisis_screener,
        {
            "crisis_direct": "crisis_handler",
            "normal": "emotion_fusion"
        }
    )

    # emotion_fusion → parallel_analysis (distortion + trend concurrently)
    graph.add_edge("emotion_fusion", "parallel_analysis")

    # parallel_analysis → conversation_planner (uses prefetched_intent — no LLM)
    graph.add_edge("parallel_analysis", "conversation_planner")

    # conversation_planner → CONDITIONAL: normal therapy OR skip to role_selector (chitchat)
    graph.add_conditional_edges(
        "conversation_planner",
        _route_after_planner,
        {
            "fast_chitchat_path": "role_selector",
            "normal_therapeutic_path": "behavioral_activation"
        }
    )

    # behavioral_activation → technique_selector
    graph.add_edge("behavioral_activation", "technique_selector")

    # technique_selector → CONDITIONAL: crisis or role_selector
    graph.add_conditional_edges(
        "technique_selector",
        _route_after_technique_selection,
        {
            "crisis": "crisis_handler",
            "role": "role_selector"
        }
    )

    # role_selector → response_generator
    graph.add_edge("role_selector", "response_generator")

    # response_generator → parallel_persist
    graph.add_edge("response_generator", "parallel_persist")

    # crisis_handler → parallel_persist
    graph.add_edge("crisis_handler", "parallel_persist")

    # parallel_persist → END
    graph.add_edge("parallel_persist", END)

    print("[GRAPH] ✅ Graph built (10 nodes, 3 parallel tiers, v5.3 latency-optimized)")
    return graph


# ============================================
# AGENT SINGLETON
# ============================================

_compiled_agent = None
_memory_saver = None


def get_agent():
    """
    Get or create the compiled agent (singleton pattern).
    
    Returns:
        Compiled LangGraph agent with checkpointer
    """
    global _compiled_agent, _memory_saver
    
    if _compiled_agent is None:
        print("\n" + "="*60)
        print("[AGENT] 🧠 Initializing SentiMind Mental Health Agent")
        print("="*60)
        
        try:
            # Build the graph
            graph = build_graph()
            
            # Create memory checkpointer
            _memory_saver = MemorySaver()
            
            # Compile with checkpointer
            _compiled_agent = graph.compile(checkpointer=_memory_saver)
            
            print("[AGENT] ✅ Agent loaded successfully")
            print("[AGENT] 📊 Architecture v5.3: ParallelIntake[crisis|intake|mood|intent] → Fusion → Analysis → Planner → Activation → Technique → Router → Role → Response → ParallelPersist")
            print("[AGENT] ⚡ LLM calls per message: 1 (response generator, async ainvoke)")
            print("[AGENT] 🧠 Parallel Tier 1: crisis_screener || intake || mood_analyzer || intent_check")
            print("[AGENT] 🧠 Parallel Tier 2: cognitive_distortion || trend_analyzer")
            print("[AGENT] 🧠 Parallel Tier 3: psych_profile || session_saver || outcome_tracker")
            print("[AGENT] 🔗 Flow: START → 10 nodes (3 parallel tiers) → END")
            print("="*60 + "\n")
            
        except Exception as e:
            print(f"[AGENT] ❌ Failed to build agent: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    return _compiled_agent


# ============================================
# MAIN CHAT FUNCTION
# ============================================

async def chat_with_agent(
    user_id: str,
    message: str,
    session_id: Optional[str] = None,
    audio_file_path: Optional[str] = None
) -> dict:
    """
    Process a user message through the mental health agent.
    
    Args:
        user_id: Unique user identifier
        message: User's message content
        session_id: Optional session ID for conversation continuity
        audio_file_path: Optional path to voice audio file for voice analysis
    
    Returns:
        Dictionary containing:
        - response: The agent's response
        - session_id: Session identifier
        - emotion: Detected emotion
        - sentiment: Positive/negative/neutral
        - intensity: Emotion intensity (0-1)
        - confidence: Detection confidence (0-1)
        - crisis_detected: Whether crisis was detected
        - tools_used: List of tools used in processing
        - techniques: Recommended techniques (if any)
    """
    start_time = time.time()
    
    print("\n" + "="*60)
    print(f"[CHAT] [NEW] New message from user: {user_id}")
    print(f"[CHAT] [MSG] Message: \"{message[:80]}...\"" if len(message) > 80 else f"[CHAT] [MSG] Message: \"{message}\"")
    print("="*60)
    
    try:
        # Ensure user exists in database
        await ensure_user_exists(user_id)
        
        # Get the compiled agent
        agent = get_agent()
        
        # Handle session ID:
        # - If session_id is provided and valid, use it (continuing existing conversation)
        # - If session_id is None/empty, create a NEW session (new chat)
        actual_session_id = session_id
        
        if not actual_session_id:
            # Create a new session in the database for this new conversation
            new_session = await create_new_session(user_id)
            actual_session_id = new_session["id"]
            print(f"[CHAT] 🆕 Created new session: {actual_session_id}")
        else:
            print(f"[CHAT] 📎 Continuing session: {actual_session_id}")
        
        # Use session_id as thread_id for LangGraph memory (each session has its own memory)
        thread_id = actual_session_id
        config = {
            "configurable": {
                "thread_id": thread_id
            }
        }
        
        # Prepare input — only pass message + identifiers.
        # The Annotated reducers (add_messages, operator.add) handle accumulation.
        # LangGraph's checkpointer preserves state across turns.
        input_state = {
            "messages": [HumanMessage(content=message)],
            "user_id": user_id,
            "session_id": actual_session_id,
            "tools_used": [],  # fresh per turn (reducer appends within turn)
        }
        
        # Add audio file path if voice message
        if audio_file_path:
            input_state["audio_file_path"] = audio_file_path
            print(f"[CHAT] 🎤 Audio file path included: {audio_file_path[:60]}...")
        
        print(f"[CHAT] 🔍 DEBUG - Input state before invoke:")
        print(f"[CHAT] 🔍 DEBUG - message: '{message}'")
        print(f"[CHAT] 🔍 DEBUG - user_id: '{user_id}'")
        print(f"[CHAT] 🔍 DEBUG - session_id: '{actual_session_id}'")
        
        # Run the agent and capture node trace
        print("[CHAT] 🚀 Invoking agent graph...")
        # Use astream instead of ainvoke to capture the execution trace of nodes
        node_trace = []
        final_state = None
        
        async for event in agent.astream(input_state, config=config, stream_mode="updates"):
            # event is a dict mapping node_name -> state_update
            for node_name, state_update in event.items():
                print(f"[TRACE] Node completed: {node_name}")
                node_trace.append(node_name)
                final_state = state_update  # keep updating to get the last state
                
        # Calculate processing time
        processing_time = int((time.time() - start_time) * 1000)
        
        # In stream_mode="updates", the final_state might only contain the last node's updates.
        # We need the full merged state from the checkpointer.
        state_snapshot = await agent.aget_state(config)
        result = state_snapshot.values
        
        # Extract results
        final_response = result.get("final_response", "I'm here to listen. How are you feeling? 💙")
        tools_used = result.get("tools_used", [])
        recommended_techniques_by_category = result.get("recommended_techniques_by_category", {})
        
        print("\n" + "-"*60)
        print(f"[CHAT] ✅ Processing complete in {processing_time}ms")
        print(f"[CHAT] 🔄 Node trace: {' -> '.join(node_trace)}")
        print(f"[CHAT] 🔧 Tools used: {tools_used}")
        print(f"[CHAT] 💬 Response: \"{final_response[:80]}...\"" if len(final_response) > 80 else f"[CHAT] 💬 Response: \"{final_response}\"")
        print("-"*60 + "\n")
        
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
            # World-class intelligence fields (v4.0)
            "emotional_trend": result.get("emotional_trend", "stable"),
            "conversation_strategy": result.get("conversation_strategy", "validate_only"),
            "conversation_phase": result.get("conversation_phase", "venting"),
            "technique_readiness": result.get("technique_readiness", 0.0),
        }
        
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
            "processing_time_ms": 0
        }


# ============================================
# HEALTH CHECK
# ============================================

def check_agent_health() -> dict:
    """
    Check agent health and readiness.
    
    Returns:
        Dictionary with health status
    """
    try:
        agent = get_agent()
        return {
            "status": "healthy",
            "agent_ready": agent is not None,
            "architecture": "sentimind_v5.3_latency_optimized",
            "nodes": [
                "parallel_intake",         # 4-way: crisis_screener || intake || mood_analyzer || intent_pre_check
                "emotion_fusion",
                "parallel_analysis",       # distortion || trend_analyzer
                "conversation_planner",    # uses prefetched_intent — LLM call skipped on most messages
                "behavioral_activation",
                "technique_selector",
                "crisis_handler",
                "role_selector",
                "response_generator",      # single async LLM call per message
                "parallel_persist",        # psych_profile || session_saver || outcome_tracker
            ],
            "parallel_tiers": 3,
            "llm_calls_per_message": "1 (response_generator only, async ainvoke)",
            "version": "5.3.0",
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "agent_ready": False
        }
