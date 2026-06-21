"""
Context Loader - Loads user context, preferences, and memory context

This module is used by the parallel intake node. It is not a standalone graph
node anymore; `parallel_intake.run_parallel_intake` calls `load_user_context`
concurrently with crisis screening, mood analysis, and intent prefetching.

RESPONSIBILITIES:
1. Load Session History (chat messages from current session)
2. Load User Stats & Preferences (from database) - CACHED for speed
3. Reuse compact memory context from the smart gate
4. Build context ready for the fused analysis/planning pipeline

Input:
  - user_id: User's unique identifier
  - session_id: Current session identifier
  - messages: Current message (for context)
  - voice_features: (optional) Voice analysis from pre-processing

Output:
  - is_new_user: Boolean
  - session_count: Number of previous sessions
  - most_common_emotion: User's typical emotion
  - user_preferences: Communication preferences
  - chat_history: Recent messages from current session
  - memory_context: Relevant facts/session summaries
  - voice_features: (passthrough) Voice data if provided
"""

from ..agent.state import MentalHealthState
from ..tools import get_user_history
import time
import asyncio
import os

# Simple in-memory cache for user data (5 min TTL)
_user_data_cache = {}
_cache_ttl = 300  # 5 minutes

def _get_cached_user_data(user_id: str):
    """Get cached user data if fresh, else None."""
    if user_id in _user_data_cache:
        cached = _user_data_cache[user_id]
        if time.time() - cached["timestamp"] < _cache_ttl:
            return cached["data"]
        else:
            del _user_data_cache[user_id]
    return None

def _set_cached_user_data(user_id: str, data: dict):
    """Cache user data with timestamp."""
    _user_data_cache[user_id] = {
        "data": data,
        "timestamp": time.time()
    }


async def load_user_context(state: MentalHealthState) -> dict:
    """
    Build comprehensive context before agent analysis.
    
    STEP-BY-STEP PROCESS:
    1. Load session history (current conversation messages)
    2. Load user stats & preferences (who they are, how they prefer responses)
    3. Retrieve relevant facts/session summaries
    4. Build full context object for the fused analysis/planning pipeline
    
    Input State:
        - user_id: User's unique identifier
        - session_id: Current session identifier
        - messages: Current message(s) to use for context
        - voice_features: (optional) Voice analysis data
    
    Output State:
        - is_new_user: Boolean
        - session_count: Number of previous sessions
        - most_common_emotion: User's typical emotion
        - user_preferences: User's communication preferences
        - chat_history: Recent messages for context (current session only)
        - memory_context: Relevant facts/session summaries
        - context_ready: Boolean - confirms context is ready
    """
    user_id = state.get("user_id", "")
    session_id = state.get("session_id", "")
    messages = state.get("messages", [])
    current_message = messages[-1].content if messages else ""
    voice_features = state.get("voice_features", {})
    prefetched_user_context = state.get("prefetched_user_context", "") or ""
    prefetched_session_context = state.get("prefetched_session_context", {}) or {}
    intake_errors = []
    
    print(f"\n[CONTEXT_LOADER]  Loading context for user: {user_id}, session: {session_id}")
    
    if not user_id:
        error_msg = "user_id is required in state"
        print(f"[CONTEXT_LOADER]  FATAL: {error_msg}")
        raise ValueError(error_msg)
    
    memory_task = asyncio.create_task(_retrieve_semantic_memories(
        user_id,
        current_message,
        session_id,
        prefetched_user_context=prefetched_user_context,
        prefetched_session_context=prefetched_session_context,
    ))
    handoff_task = asyncio.create_task(_load_previous_session_handoff(user_id, session_id))

    # ============================================
    # STEP 1: LOAD USER STATS & PREFERENCES (CACHED)
    # ============================================
    
    print("[CONTEXT_LOADER]  Step 1: Loading user stats & preferences")
    
    # Check cache first (OPTIMIZATION)
    cached_data = _get_cached_user_data(user_id)
    
    if cached_data:
        is_new = cached_data.get("is_new_user", True)
        sessions = cached_data.get("total_sessions", 0)
        emotion = cached_data.get("most_common_emotion", "neutral")
        user_prefs = cached_data.get("preferences", {})
        print(f"[CONTEXT_LOADER]  Using CACHED user data (fresh)")
    else:
        history_task = asyncio.create_task(get_user_history.ainvoke({"user_id": user_id}))
        preferences_task = asyncio.create_task(_load_user_preferences(user_id))

        try:
            history = await history_task
            is_new = history.get("is_new_user", True)
            sessions = history.get("total_sessions", 0)
            emotion = history.get("most_common_emotion", "neutral")
            print(f"[CONTEXT_LOADER]  User stats: new={is_new}, sessions={sessions}, mood={emotion}")
        except Exception as e:
            print(f"[CONTEXT_LOADER]  Error loading user stats: {str(e)[:80]}")
            intake_errors.append(f"Failed to load user stats: {str(e)}")
            is_new = True
            sessions = 0
            emotion = "neutral"
        
        try:
            user_prefs = await preferences_task
            print(f"[CONTEXT_LOADER]  Preferences loaded: {list(user_prefs.keys()) if user_prefs else 'none'}")
        except Exception as e:
            print(f"[CONTEXT_LOADER]  Error loading preferences: {str(e)[:80]}")
            intake_errors.append(f"Failed to load preferences: {str(e)}")
            user_prefs = {}
        
        # Cache for future requests
        _set_cached_user_data(user_id, {
            "is_new_user": is_new,
            "total_sessions": sessions,
            "most_common_emotion": emotion,
            "preferences": user_prefs
        })
    
    # ============================================
    # STEP 2: MEMORY ARCHITECTURE
    # ============================================
    # Layer 1 (Within-session): LangGraph `state["messages"]` accumulates all turns
    #   via the add_messages reducer  the response generator reads these directly.
    #   No DB query needed, no token bloat risk.
    # Layer 2 (Cross-session): smart-gate memory context provides relevant
    #   facts and summaries from prior sessions.
    # Prisma/Supabase Postgres remains the source of truth for stored messages,
    # summaries, facts, and analytics; raw DB messages are not injected here.
    chat_history = []  # Not used  see response generator for two-layer memory implementation
    print(f"[CONTEXT_LOADER]  Step 2: Memory handled via LangGraph state + smart-gate context (no raw DB history load)")
    
    # ============================================
    # STEP 3: RETRIEVE MEMORY CONTEXT
    # ============================================
    
    print("[CONTEXT_LOADER]  Step 3: Retrieving deduplicated memory context")
    try:
        memory_context = await memory_task
    except Exception as e:
        print(f"[CONTEXT_LOADER]  Memory task failed (non-fatal): {str(e)[:120]}")
        memory_context = ""

    try:
        previous_session_handoff = await handoff_task
    except Exception as e:
        print(f"[CONTEXT_LOADER]  Handoff task failed (non-fatal): {str(e)[:120]}")
        previous_session_handoff = {}

    handoff_text = _format_previous_session_handoff(previous_session_handoff)
    if handoff_text:
        memory_context = "\n\n".join(part for part in (memory_context, handoff_text) if part)

    # Background task: extract facts from user message (non-blocking)
    background_facts = (
        os.getenv("SENTIMIND_BACKGROUND_LLM_ENABLED", "0").lower() in {"1", "true", "yes", "on"}
        or os.getenv("SENTIMIND_BACKGROUND_FACT_EXTRACTION", "0").lower() in {"1", "true", "yes", "on"}
    )
    if background_facts and current_message and user_id:
        from ..memory.explicit_facts import extract_and_save_facts
        asyncio.create_task(extract_and_save_facts(
            user_id=user_id,
            message=current_message,
            session_id=session_id
        ))
        print(f"[CONTEXT_LOADER]  Fact extraction scheduled (background)")
    elif current_message and user_id:
        print("[CONTEXT_LOADER]  Fact extraction skipped (background LLM disabled)")

    print(f"[CONTEXT_LOADER]  Retrieved {len(memory_context)} chars of memory context")
    
    # ============================================
    # STEP 4: BUILD FULL CONTEXT
    # ============================================
    
    print("[CONTEXT_LOADER]  Step 4: Building full context object")
    
    # Context ready flag
    context_ready = True
    
    print(f"[CONTEXT_LOADER]  Context ready: {context_ready}")
    print(f"[CONTEXT_LOADER]  Preferences: {user_prefs}")
    if voice_features:
        print(f"[CONTEXT_LOADER]  Voice features included: emotion={voice_features.get('emotion')}")
    
    # CRITICAL: Pass through messages from state to avoid state corruption in LangGraph
    # LangGraph uses add_messages reducer, so we need to maintain this field
    #
    # FIX 1b: Quarantine historical mood from influencing current session emotion detection.
    # `most_common_emotion` is from user_stats (cross-session average/last session).
    # It must NEVER be used as the current-session emotion signal.
    # Stored separately as `historical_mood` so downstream nodes don't confuse it
    # with the current detected emotion. OUTCOME_TRACKER must use session_start_emotion instead.
    print(f"[CONTEXT_LOADER]  Historical mood (cross-session): {emotion}  stored as 'historical_mood' (metadata only)")
    return {
        "is_new_user": is_new,
        "session_count": sessions,
        "most_common_emotion": emotion,   # kept for display/context purposes
        "historical_mood": emotion,        # FIX 1b: explicit quarantine  metadata only, NOT current session emotion
        "user_preferences": user_prefs,
        "chat_history": chat_history,
        "memory_context": memory_context,
        "previous_session_handoff": previous_session_handoff,
        "context_ready": context_ready,
        "voice_features": voice_features,  # Passthrough if provided
        "intake_errors": intake_errors,  # Track any errors during intake
        # CRITICAL: Don't clear messages - LangGraph reducer needs this
        "messages": messages if messages else [],
        "audio_file_path": state.get("audio_file_path"),  # Pass through audio file path
        # RESET per-turn fields so stale data from previous turns never bleeds through
        "recommended_techniques_by_category": {},
        "recommended_technique": {},
        "final_response": "",
    }


async def _retrieve_semantic_memories(
    user_id: str,
    current_message: str,
    session_id: str = "",
    prefetched_user_context: str = "",
    prefetched_session_context: dict | None = None,
) -> str:
    """
    Retrieve deduplicated prompt memory context.
    Falls back to empty string if memory builder fails.

    Smart-gate context provides facts and broad session summaries.
    Raw Prisma message history is deliberately not injected here to avoid
    duplicate context with current-session history.
    """
    try:
        sections = []
        if prefetched_user_context and prefetched_user_context.strip():
            sections.append(prefetched_user_context.strip())
        if prefetched_session_context and prefetched_session_context.get("formatted_context"):
            sections.append(prefetched_session_context["formatted_context"].strip())

        # v9.5: pgvector recall supplements the smart-gate facts/session context
        # with only the most relevant cross-session snippets.
        from ..memory import get_memory_context_for_prompt

        vector_context = ""
        if current_message and current_message.strip():
            vector_context = await get_memory_context_for_prompt(
                user_id,
                current_message,
                max_memories=3,
                exclude_session_id=session_id or None,
            )
        if vector_context and vector_context.strip():
            sections.insert(0, vector_context.strip())

        if sections:
            print("[CONTEXT_LOADER]  Reusing smart-gate memory context + pgvector recall")
            return "\n\n".join(sections) + "\n\nUse above as context. Do not repeat verbatim. Only reference if directly relevant."

        return ""
    except Exception as e:
        print(f"[CONTEXT_LOADER]  Memory builder failed (non-fatal): {str(e)[:120]}")
        return ""


async def _load_previous_session_handoff(user_id: str, current_session_id: str = "") -> dict:
    if not user_id:
        return {}
    try:
        from ..db.client import get_prisma_client

        prisma = await get_prisma_client()
        where: dict = {"userId": user_id}
        if current_session_id:
            where["sessionId"] = {"not": current_session_id}
        summaries = await prisma.sessionsummary.find_many(
            where=where,
            order={"createdAt": "desc"},
            take=1,
        )
        for summary in summaries:
            return {
                "session_id": getattr(summary, "sessionId", None),
                "title": getattr(summary, "title", None),
                "summary": getattr(summary, "summary", None),
                "final_emotion": getattr(summary, "finalEmotion", None) or getattr(summary, "emotion", None),
                "final_intensity": getattr(summary, "finalIntensity", None),
                "technique_offered": getattr(summary, "techniqueOffered", None),
                "turn_type_counts": getattr(summary, "turnTypeCounts", None),
                "outcome": getattr(summary, "outcome", None),
            }
    except Exception as e:
        print(f"[CONTEXT_LOADER]  Previous handoff load failed (non-fatal): {str(e)[:120]}")
    return {}


def _format_previous_session_handoff(handoff: dict) -> str:
    if not handoff:
        return ""
    parts = ["PREVIOUS SESSION HANDOFF:"]
    if handoff.get("title"):
        parts.append(f"- Title: {handoff['title']}")
    if handoff.get("summary"):
        parts.append(f"- Summary: {handoff['summary']}")
    if handoff.get("final_emotion"):
        intensity = handoff.get("final_intensity")
        if intensity is not None:
            try:
                parts.append(f"- Final state: {handoff['final_emotion']} ({float(intensity):.0%})")
            except (TypeError, ValueError):
                parts.append(f"- Final state: {handoff['final_emotion']}")
        else:
            parts.append(f"- Final state: {handoff['final_emotion']}")
    if handoff.get("outcome"):
        parts.append(f"- Outcome: {handoff['outcome']}")
    if handoff.get("turn_type_counts"):
        parts.append(f"- Turn counts: {handoff['turn_type_counts']}")
    return "\n".join(parts)


async def _load_user_preferences(user_id: str) -> dict:
    """
    Load user preferences from the database for personalized responses.
    
    Args:
        user_id: User's unique identifier
        
    Returns:
        Dictionary with communication preferences
    """
    if not user_id:
        return {}
    
    try:
        from ..db.client import get_prisma_client
        prisma = await get_prisma_client()
        
        pref = await prisma.userpreference.find_unique(
            where={"userId": user_id}
        )
        
        if not pref:
            return {}
        
        return {
            "communicationStyle": pref.communicationStyle,
            "detailLevel": pref.detailLevel,
            "tone": pref.tone,
            "preferredCategories": pref.preferredCategories or [],
        }
    except Exception as e:
        print(f"[CONTEXT_LOADER]  Failed to load preferences: {e}")
        return {}
