"""
Memory Module - Embedding-based semantic memory using ChromaDB
Provides long-term memory with semantic retrieval for conversation context
"""

import os
from typing import Optional
from datetime import datetime

# Use lazy imports to avoid startup slowdown
_vectorstore = None
_embeddings = None
_MEMORY_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "memory_store")


def _get_embeddings():
    """Get or create the embeddings model (lazy loading)."""
    global _embeddings
    
    if _embeddings is None:
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
            
            print("[MEMORY] 🧠 Loading embedding model (all-MiniLM-L6-v2)...")
            _embeddings = HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2",
                model_kwargs={'device': 'cpu'},
                encode_kwargs={'normalize_embeddings': True}
            )
            print("[MEMORY] ✅ Embedding model loaded")
            
        except ImportError:
            print("[MEMORY] ⚠️ langchain-huggingface not installed, falling back to sentence-transformers")
            from langchain_community.embeddings import HuggingFaceEmbeddings
            
            _embeddings = HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2"
            )
            
    return _embeddings


def preload_embeddings():
    """Eagerly preload embedding model on startup."""
    _get_embeddings()


def _get_vectorstore(user_id: str):
    """
    Get or create a ChromaDB vectorstore for a specific user.
    Each user has their own collection for privacy.
    """
    try:
        from langchain_chroma import Chroma
    except ImportError:
        from langchain_community.vectorstores import Chroma
    
    # Ensure memory directory exists
    os.makedirs(_MEMORY_DIR, exist_ok=True)
    
    embeddings = _get_embeddings()
    
    # Create user-specific collection
    collection_name = f"user_{user_id.replace('-', '_')[:50]}"
    
    vectorstore = Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=_MEMORY_DIR
    )
    
    return vectorstore


async def store_conversation_memory(
    user_id: str,
    user_message: str,
    assistant_response: str,
    emotion: str = "neutral",
    session_id: Optional[str] = None
) -> bool:
    """
    Store a conversation turn in the vector memory.
    
    Args:
        user_id: User's unique identifier
        user_message: What the user said
        assistant_response: What the assistant replied
        emotion: Detected emotion for context
        session_id: Optional session identifier
        
    Returns:
        True if stored successfully
    """
    try:
        vectorstore = _get_vectorstore(user_id)
        
        # Create a combined document for the conversation turn
        timestamp = datetime.now().isoformat()
        
        # Store user message with metadata
        user_doc = f"User said: {user_message}"
        user_metadata = {
            "role": "user",
            "emotion": emotion,
            "timestamp": timestamp,
            "session_id": session_id or "unknown"
        }
        
        # Store assistant response with metadata
        assistant_doc = f"Assistant replied: {assistant_response}"
        assistant_metadata = {
            "role": "assistant",
            "timestamp": timestamp,
            "session_id": session_id or "unknown"
        }
        
        # Add documents to vectorstore
        vectorstore.add_texts(
            texts=[user_doc, assistant_doc],
            metadatas=[user_metadata, assistant_metadata]
        )
        
        print(f"[MEMORY] 💾 Stored conversation in vector memory for user {user_id[:8]}...")
        return True
        
    except Exception as e:
        raise


async def retrieve_relevant_memories(
    user_id: str,
    query: str,
    k: int = 5,
    session_id: Optional[str] = None
) -> list[dict]:
    """
    Retrieve relevant past conversations based on semantic similarity.
    
    Args:
        user_id: User's unique identifier
        query: The current message to find relevant context for
        k: Number of relevant memories to retrieve
        session_id: Optional session ID to filter memories
        
    Returns:
        List of relevant memory documents with content and metadata
    """
    try:
        vectorstore = _get_vectorstore(user_id)
        
        # Build filter if session_id is provided
        filter_dict = None
        if session_id:
            filter_dict = {"session_id": session_id}
        
        # Search for similar documents with optional filter
        if filter_dict:
            results = vectorstore.similarity_search_with_score(
                query, 
                k=k,
                filter=filter_dict
            )
        else:
            results = vectorstore.similarity_search_with_score(query, k=k * 2)  # Fetch extra, filter below
        
        memories = []
        for doc, score in results:
            # Only include highly relevant results (stricter threshold prevents hallucinations)
            if score < 0.8:  # Tight threshold for quality
                # Only include user messages (avoid injecting assistant responses as context)
                if doc.metadata.get("role") != "user":
                    continue
                
                # Truncate long content to prevent context pollution
                content = doc.page_content[:200]
                if len(doc.page_content) > 200:
                    content += "..."
                
                # Calculate recency bonus (memories from last 7 days score higher)
                recency_bonus = 0.0
                try:
                    from datetime import datetime
                    ts = doc.metadata.get("timestamp", "")
                    if ts:
                        mem_date = datetime.fromisoformat(ts)
                        days_ago = (datetime.now() - mem_date).days
                        if days_ago <= 7:
                            recency_bonus = 0.1 * (1 - days_ago / 7)
                except Exception:
                    pass
                
                memories.append({
                    "content": content,
                    "role": doc.metadata.get("role", "unknown"),
                    "emotion": doc.metadata.get("emotion", "neutral"),
                    "timestamp": doc.metadata.get("timestamp", ""),
                    "relevance_score": round(1 - (score / 2) + recency_bonus, 2)
                })
                
                if len(memories) >= k:  # Cap at requested count
                    break
        
        print(f"[MEMORY] 🔍 Retrieved {len(memories)} relevant memories for query")
        return memories
        
    except Exception as e:
        raise


async def get_memory_context_for_prompt(
    user_id: str,
    current_message: str,
    max_memories: int = 3,
    session_id: Optional[str] = None
) -> str:
    """
    Get formatted memory context to include in LLM prompts.
    
    Args:
        user_id: User's unique identifier
        current_message: The user's current message
        max_memories: Maximum number of memories to include
        session_id: Optional session ID to filter memories to current session only
        
    Returns:
        Formatted string of relevant memories for prompt injection
    """
    memories = await retrieve_relevant_memories(
        user_id, 
        current_message, 
        k=max_memories,
        session_id=session_id
    )
    
    if not memories:
        return ""
    
    # Format memories for prompt
    context_parts = ["APPROXIMATE PAST CONTEXT (may not be exact — use as gentle reference only):"]
    
    # Sort by relevance score descending
    memories.sort(key=lambda m: m.get("relevance_score", 0), reverse=True)
    
    for i, mem in enumerate(memories, 1):
        content = mem["content"]
        emotion = mem.get("emotion", "")
        
        context_parts.append(f"{i}. {content}")
        if emotion and emotion != "neutral":
            context_parts.append(f"   (User was feeling: {emotion})")
    
    context_parts.append(
        "\nUse this as background context only. Do NOT repeat these memories verbatim to the user."
    )
    
    return "\n".join(context_parts)


def check_memory_health() -> dict:
    """Check if the memory system is working."""
    try:
        embeddings = _get_embeddings()
        
        # Test embedding generation
        test_embedding = embeddings.embed_query("test")
        
        return {
            "status": "healthy",
            "embedding_model": "all-MiniLM-L6-v2",
            "embedding_dim": len(test_embedding),
            "storage_path": _MEMORY_DIR
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }
