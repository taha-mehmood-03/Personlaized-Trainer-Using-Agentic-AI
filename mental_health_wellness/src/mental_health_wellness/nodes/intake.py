"""
Intake Node - Loads user context, chat history, and semantic memories

ARCHITECTURE NODE 2:
Purpose: Prepare full context for agentic pipeline
Runs AFTER voice pre-processing (if applicable)

RESPONSIBILITIES:
1. Load Session History (chat messages from current session)
2. Load User Stats & Preferences (from database) - CACHED for speed
3. Retrieve Semantic Memories (from ChromaDB vector store)
4. Build Context ready for agentic analysis

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
  - memory_context: Semantically relevant memories
  - voice_features: (passthrough) Voice data if provided
"""

from ..agent.state import MentalHealthState
from ..tools import get_user_history
import time

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


async def intake_node(state: MentalHealthState) -> dict:
    """
    INTAKE NODE - Build comprehensive context before agent analysis.
    
    STEP-BY-STEP PROCESS:
    1. Load session history (current conversation messages)
    2. Load user stats & preferences (who they are, how they prefer responses)
    3. Retrieve semantic memories (relevant past conversations)
    4. Build full context object for agentic pipeline
    
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
        - memory_context: Semantically retrieved relevant memories
        - context_ready: Boolean - confirms context is ready
    """
    user_id = state.get("user_id", "")
    session_id = state.get("session_id", "")
    messages = state.get("messages", [])
    current_message = messages[-1].content if messages else ""
    voice_features = state.get("voice_features", {})
    intake_errors = []
    
    print(f"\n[NODE: INTAKE] 👤 Loading context for user: {user_id}, session: {session_id}")
    
    if not user_id:
        error_msg = "user_id is required in state"
        print(f"[NODE: INTAKE] ❌ FATAL: {error_msg}")
        raise ValueError(error_msg)
    
    # ============================================
    # STEP 1: LOAD USER STATS & PREFERENCES (CACHED)
    # ============================================
    
    print("[NODE: INTAKE] 📊 Step 1: Loading user stats & preferences")
    
    # Check cache first (OPTIMIZATION)
    cached_data = _get_cached_user_data(user_id)
    
    if cached_data:
        is_new = cached_data.get("is_new_user", True)
        sessions = cached_data.get("total_sessions", 0)
        emotion = cached_data.get("most_common_emotion", "neutral")
        user_prefs = cached_data.get("preferences", {})
        print(f"[NODE: INTAKE] ⚡ Using CACHED user data (fresh)")
    else:
        try:
            history = await get_user_history.ainvoke({"user_id": user_id})
            is_new = history.get("is_new_user", True)
            sessions = history.get("total_sessions", 0)
            emotion = history.get("most_common_emotion", "neutral")
            print(f"[NODE: INTAKE] ✅ User stats: new={is_new}, sessions={sessions}, mood={emotion}")
        except Exception as e:
            print(f"[NODE: INTAKE] ⚠️ Error loading user stats: {str(e)[:80]}")
            intake_errors.append(f"Failed to load user stats: {str(e)}")
            is_new = True
            sessions = 0
            emotion = "neutral"
        
        try:
            user_prefs = await _load_user_preferences(user_id)
            print(f"[NODE: INTAKE] ✅ Preferences loaded: {list(user_prefs.keys()) if user_prefs else 'none'}")
        except Exception as e:
            print(f"[NODE: INTAKE] ⚠️ Error loading preferences: {str(e)[:80]}")
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
    # STEP 2: SEMANTIC MEMORY REPLACES CHAT HISTORY
    # ============================================
    
    print("[NODE: INTAKE] 📝 Step 2: Skipping Prisma chat history (using semantic memory instead)")
    
    # Chat history is now handled via semantic memory from ChromaDB
    # This reduces database queries and prioritizes semantically relevant context
    chat_history = []  # Empty - semantic memory provides context
    print(f"[NODE: INTAKE] ✅ Chat history disabled (semantic memory active)")
    
    # ============================================
    # STEP 3: RETRIEVE SEMANTIC MEMORIES
    # ============================================
    
    print("[NODE: INTAKE] 🧠 Step 3: Retrieving semantic memories")
    
    memory_context = await _retrieve_semantic_memories(user_id, current_message, session_id)
    print(f"[NODE: INTAKE] ✅ Retrieved {len(memory_context)} chars of memory context")
    
    # ============================================
    # STEP 4: BUILD FULL CONTEXT
    # ============================================
    
    print("[NODE: INTAKE] 🔨 Step 4: Building full context object")
    
    # Context ready flag
    context_ready = True
    
    print(f"[NODE: INTAKE] ✅ Context ready: {context_ready}")
    print(f"[NODE: INTAKE] ⚙️ Preferences: {user_prefs}")
    if voice_features:
        print(f"[NODE: INTAKE] 🎤 Voice features included: emotion={voice_features.get('emotion')}")
    
    # CRITICAL: Pass through messages from state to avoid state corruption in LangGraph
    # LangGraph uses add_messages reducer, so we need to maintain this field
    #
    # FIX 1b: Quarantine historical mood from influencing current session emotion detection.
    # `most_common_emotion` is from user_stats (cross-session average/last session).
    # It must NEVER be used as the current-session emotion signal.
    # Stored separately as `historical_mood` so downstream nodes don't confuse it
    # with the current detected emotion. OUTCOME_TRACKER must use session_start_emotion instead.
    print(f"[NODE: INTAKE] 📋 Historical mood (cross-session): {emotion} → stored as 'historical_mood' (metadata only)")
    return {
        "is_new_user": is_new,
        "session_count": sessions,
        "most_common_emotion": emotion,   # kept for display/context purposes
        "historical_mood": emotion,        # FIX 1b: explicit quarantine — metadata only, NOT current session emotion
        "user_preferences": user_prefs,
        "chat_history": chat_history,
        "memory_context": memory_context,
        "context_ready": context_ready,
        "voice_features": voice_features,  # Passthrough if provided
        "intake_errors": intake_errors,  # Track any errors during intake
        # CRITICAL: Don't clear messages - LangGraph reducer needs this
        "messages": messages if messages else [],
        "audio_file_path": state.get("audio_file_path")  # Pass through audio file path
    }


async def _retrieve_semantic_memories(user_id: str, current_message: str, session_id: str = "") -> str:
    """
    Retrieve semantically relevant memories from the vector store.
    
    Args:
        user_id: User's unique identifier
        current_message: The current message to find relevant context for
        session_id: Current session ID to filter memories (optional)
        
    Returns:
        Formatted string of relevant memories for prompt injection
    """
    from ..memory import get_memory_context_for_prompt
    
    memory_context = await get_memory_context_for_prompt(
        user_id=user_id,
        current_message=current_message,
        max_memories=5
        # NOTE: No session_id filter — enables cross-session memory recall
    )
    
    return memory_context


async def _load_session_chat_history(session_id: str, limit: int = 10) -> list[dict]:
    """
    Load chat messages from the CURRENT session only.
    
    Args:
        session_id: Current session's unique identifier
        limit: Maximum number of message pairs to load
        
    Returns:
        List of message dictionaries with role and content
    """
    if not session_id:
        return []
    
    from ..db.client import get_prisma_client
    prisma = await get_prisma_client()
    
    # Get messages ONLY from the current session
    messages = await prisma.message.find_many(
        where={"sessionId": session_id},
        order={"createdAt": "asc"},
        take=limit * 2  # Limit to last N message pairs
    )
    
    if not messages:
        return []
    
    # Convert to chat history format
    chat_history = []
    for msg in messages:
        chat_history.append({
            "role": msg.role.lower(),  # "user" or "assistant"
            "content": msg.content
        })
    
    return chat_history


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
        print(f"[NODE: INTAKE] ⚠️ Failed to load preferences: {e}")
        return {}
