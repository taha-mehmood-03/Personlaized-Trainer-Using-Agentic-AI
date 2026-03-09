"""
Graph Builder - StateGraph construction and main entry points

ARCHITECTURE OVERVIEW (v5.0 — SentiMind v3 World-Class Intelligence):
The graph implements a 14-node deterministic hybrid pipeline:

MAIN PIPELINE (LangGraph):
  1.  Intake Node:                   Load context (history, prefs, psych profile)
  2.  Mood Analyzer Node:            DistilBERT emotion detection (Python, no LLM)
  3.  Emotion Fusion Node:           Merge text + voice emotion (Python, no LLM)
  4.  Cognitive Distortion Node:     CBT distortion pattern detection (Python) [v3 NEW]
  5.  Trend Analyzer Node:           Track emotional trajectory (Python/SQL)   
  6.  Conversation Planner:          Strategic decision-maker (Python, no LLM)
  7.  Behavioral Activation Node:    Real-world micro-action engine (Python)   [v3 NEW]
  8.  Technique Selector Node:       Database technique query (Python, no LLM)
  9.  Crisis Router:                 Conditional routing
  10. Role Selector Node:            Communication style (trend-aware)
  11. Crisis Handler OR Response Generator: Single LLM call ONLY
  12. Psych Profile Updater:         Persistent behavioral model update        [v3 NEW]
  13. Session Saver:                 Persist data + session summary
  14. Outcome Tracker:               Measure technique effectiveness (Python/SQL)

EDGE FLOW:
START → Intake → Mood → Fusion → Distortion → Trend → Planner → Activation → Technique → Router
      → (Crisis | Role → Response) → ProfileUpdater → Saver → Outcome → END
"""

import time
import uuid
from typing import Optional

from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from .state import MentalHealthState, get_initial_state
from ..nodes import (
    intake_node,
    crisis_handler_node,
    role_selector_node,
    session_saver_node
)
from ..nodes.mood_analyzer_node import mood_analyzer_node
from ..nodes.technique_selector_node import technique_selector_node
from ..nodes.optimized_response_generator import optimized_response_generator_node
from ..nodes.emotion_fusion_node import emotion_fusion_node
from ..nodes.trend_analyzer_node import trend_analyzer_node
from ..nodes.conversation_planner_node import conversation_planner_node
from ..nodes.cognitive_distortion_node import cognitive_distortion_node
from ..nodes.behavioral_activation_node import behavioral_activation_node
from ..nodes.psych_profile_updater import psych_profile_updater_node
from ..nodes.outcome_tracker_node import outcome_tracker_node
from ..db.client import ensure_user_exists, create_new_session


# ============================================
# FIX 1: DETERMINISTIC CRISIS PRE-SCREENER
# ============================================
# These keyword sets catch explicit self-harm language BEFORE the LLM runs.
# Critical: the emotion model and LLM can both misclassify these phrases.
# This deterministic layer is the mandatory safety net.

_CRISIS_KEYWORDS_HIGH = {
    "kill myself", "killing myself", "end my life", "ending my life",
    "end it all tonight", "going to kill myself", "i want to die",
    "take my life", "taking my life", "i will kill myself",
    "i'm going to kill", "commit suicide", "committing suicide",
    "take my own life", "end my own life", "hang myself",
    "shoot myself", "overdose on", "slit my wrists",
    "thinking about ending", "planning to end my life",
}
_CRISIS_KEYWORDS_MEDIUM = {
    "not wake up", "sleep forever", "don't want to live",
    "wish i was dead", "wish i were dead", "no reason to live",
    "better off dead", "better off without me", "disappear forever",
    "can't go on", "no point in living", "end the pain",
}


def crisis_pre_screener_node(state: MentalHealthState) -> dict:
    """
    FIX 1: DETERMINISTIC CRISIS PRE-SCREENER
    
    Runs BEFORE the LLM and emotion model.
    Matches explicit suicidal/self-harm phrases and short-circuits the pipeline
    by setting crisis_detected=True and crisis_level directly in state.
    
    This is the mandatory safety net — no LLM or emotion model is reliable
    enough to be the sole crisis detector.
    """
    messages = state.get("messages", [])
    msg = messages[-1].content.lower() if messages else ""
    
    for phrase in _CRISIS_KEYWORDS_HIGH:
        if phrase in msg:
            print(f"[CRISIS_SCREENER] HIGH RISK keyword match: '{phrase}'")
            return {
                "crisis_detected": True,
                "crisis_level": "high",
                "crisis_pre_screened": True,
            }
    
    for phrase in _CRISIS_KEYWORDS_MEDIUM:
        if phrase in msg:
            print(f"[CRISIS_SCREENER] MEDIUM RISK keyword match: '{phrase}'")
            return {
                "crisis_detected": True,
                "crisis_level": "medium",
                "crisis_pre_screened": True,
            }
    
    print("[CRISIS_SCREENER] No crisis keywords detected — continuing normal pipeline")
    return {"crisis_pre_screened": False}


def _route_after_crisis_screener(state: MentalHealthState) -> str:
    """If pre-screener flagged crisis, skip LLM entirely and go to crisis handler."""
    if state.get("crisis_pre_screened") and state.get("crisis_detected", False):
        print("[CRISIS_SCREENER] Routing directly to crisis_handler (skipping LLM pipeline)")
        return "crisis_direct"
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
      ELIF intensity >= 0.8 (high distress) → Route to "crisis_handler" 
      ELSE → Route to "role_selector"
    """
    intensity = state.get("fused_intensity", state.get("intensity", 0.5))
    crisis_detected = state.get("crisis_detected", False)
    
    if crisis_detected:
        print(f"[ROUTER] Crisis detected — routing to crisis_handler")
        return "crisis"
    elif intensity >= 0.8:
        print(f"[ROUTER] High intensity route (intensity: {intensity:.0%})")
        return "crisis"
    else:
        print(f"[ROUTER] Normal route (intensity: {intensity:.0%})")
        return "role"


def build_graph() -> StateGraph:
    """
    Build optimized deterministic LangGraph v5.0.
    
    SENTIMIND v3 DETERMINISTIC HYBRID ARCHITECTURE:
    
     1.  Intake Node:               Load user context & psych profile
     2.  Mood Analyzer Node:        DistilBERT emotion detection (Python, no LLM)
     3.  Emotion Fusion Node:       Merge text + voice emotion (Python, no LLM)
     4.  Cognitive Distortion:      CBT pattern detection (Python, no LLM)        [v3]
     5.  Trend Analyzer Node:       Emotional trajectory analysis (Python/SQL)
     6.  Conversation Planner:      Strategic decision-maker (Python, no LLM)
     7.  Behavioral Activation:     Real-world micro-action engine (Python, no LLM)[v3]
     8.  Technique Selector Node:   DB query, planner-gated (Python, no LLM)
     9.  Crisis Router:             Route high-intensity to crisis handler
     10. Role Selector:             Trend-aware communication style
     11. Response Generator:        Strategy-aware single LLM call
     12. Psych Profile Updater:     Persistent psychological model update         [v3]
     13. Session Saver:             Persist + phase + summary
     14. Outcome Tracker:           Technique effectiveness (Python/SQL)
    
    KEY: Still exactly 1 LLM call per message.
    """
    print("[GRAPH] 🔨 Building world-class deterministic hybrid graph (v4.0)...")
    
    # Create graph with custom state
    graph = StateGraph(MentalHealthState)
    
    # ========================================
    # ADD NODES (15 total — SentiMind v3 + Safety)
    # ========================================
    
    graph.add_node("crisis_pre_screener", crisis_pre_screener_node)     # FIX 1: safety net
    graph.add_node("intake", intake_node)
    graph.add_node("mood_analyzer", mood_analyzer_node)
    graph.add_node("emotion_fusion", emotion_fusion_node)
    graph.add_node("cognitive_distortion", cognitive_distortion_node)   # v3 NEW
    graph.add_node("trend_analyzer", trend_analyzer_node)
    graph.add_node("conversation_planner", conversation_planner_node)
    graph.add_node("behavioral_activation", behavioral_activation_node) # v3 NEW
    graph.add_node("technique_selector", technique_selector_node)
    graph.add_node("role_selector", role_selector_node)
    graph.add_node("crisis_handler", crisis_handler_node)
    graph.add_node("response_generator", optimized_response_generator_node)
    graph.add_node("psych_profile_updater", psych_profile_updater_node) # v3 NEW
    graph.add_node("session_saver", session_saver_node)
    graph.add_node("outcome_tracker", outcome_tracker_node)
    
    # ========================================
    # ADD EDGES (v3 full flow)
    # ========================================
    
    # START → crisis_pre_screener (FIX 1: safety gate runs first)
    graph.add_edge(START, "crisis_pre_screener")
    
    # crisis_pre_screener → EITHER intake (normal) OR crisis_handler (keyword matched)
    graph.add_conditional_edges(
        "crisis_pre_screener",
        _route_after_crisis_screener,
        {
            "crisis_direct": "crisis_handler",
            "normal": "intake"
        }
    )
    
    # intake → mood_analyzer
    graph.add_edge("intake", "mood_analyzer")
    
    # mood_analyzer → emotion_fusion (merge text + voice)
    graph.add_edge("mood_analyzer", "emotion_fusion")
    
    # emotion_fusion → cognitive_distortion (detect CBT patterns) [v3 NEW]
    graph.add_edge("emotion_fusion", "cognitive_distortion")
    
    # cognitive_distortion → trend_analyzer
    graph.add_edge("cognitive_distortion", "trend_analyzer")
    
    # trend_analyzer → conversation_planner (uses distortion_type + trend)
    graph.add_edge("trend_analyzer", "conversation_planner")
    
    # conversation_planner → behavioral_activation [v3 NEW]
    graph.add_edge("conversation_planner", "behavioral_activation")
    
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
    
    # response_generator → psych_profile_updater [v3 NEW]
    graph.add_edge("response_generator", "psych_profile_updater")
    
    # crisis_handler → psych_profile_updater (skips response generator)
    graph.add_edge("crisis_handler", "psych_profile_updater")
    
    # psych_profile_updater → session_saver
    graph.add_edge("psych_profile_updater", "session_saver")
    
    # session_saver → outcome_tracker
    graph.add_edge("session_saver", "outcome_tracker")
    
    # outcome_tracker → END
    graph.add_edge("outcome_tracker", END)
    
    print("[GRAPH] Graph built (15 nodes, 1 LLM call, SentiMind v3 intelligence + crisis pre-screener)")
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
            print("[AGENT] 📊 Architecture v5.0: Intake → Mood → Fusion → Distortion → Trend → Planner → Activation → Technique → Router → Role → Response → Profile → Saver → Outcome")
            print("[AGENT] ⚡ LLM calls per message: 1 (all intelligence nodes are pure Python)")
            print("[AGENT] 🧠 Intelligence: Cognitive Distortion + Behavioral Activation + Psych Profile + Conversation Planner + Trend Analysis + Emotion Fusion")
            print("[AGENT] 🔗 Flow: START → 14 nodes → END")
            print("[AGENT] 🎤 Voice Pre-Processing handled in api_server.py")
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
        
        # Run the agent
        print("[CHAT] 🚀 Invoking agent graph...")
        result = await agent.ainvoke(input_state, config=config)
        
        # Calculate processing time
        processing_time = int((time.time() - start_time) * 1000)
        
        # Extract results
        final_response = result.get("final_response", "I'm here to listen. How are you feeling? 💙")
        tools_used = result.get("tools_used", [])
        recommended_techniques_by_category = result.get("recommended_techniques_by_category", {})
        
        print("\n" + "-"*60)
        print(f"[CHAT] ✅ Processing complete in {processing_time}ms")
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
            "recommended_technique": result.get("recommended_technique", {}),
            "recommended_techniques_by_category": recommended_techniques_by_category,
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
            "architecture": "world_class_deterministic_hybrid_v4",
            "nodes": [
                "intake",
                "mood_analyzer",
                "emotion_fusion",
                "cognitive_distortion",
                "trend_analyzer",
                "conversation_planner",
                "behavioral_activation",
                "technique_selector",
                "crisis_handler",
                "role_selector",
                "response_generator",
                "psych_profile_updater",
                "session_saver",
                "outcome_tracker"
            ],
            "version": "5.0.0"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "agent_ready": False
        }
