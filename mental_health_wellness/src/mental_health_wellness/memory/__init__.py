"""
Memory Module - Embedding-based semantic memory using ChromaDB
Provides long-term memory with semantic retrieval for conversation context
"""

import os
import json
import math
import hashlib
import logging
import io
import contextlib
from typing import Optional
from datetime import datetime

# Keep local semantic memory from making network probes during normal app use.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# Use lazy imports to avoid startup slowdown
_vectorstore_cache: dict = {}  # Cache per user_id to avoid reconnection overhead
_embeddings = None
logger = logging.getLogger("sentimind.memory")
_MEMORY_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "memory_store")
_FALLBACK_DIR = os.path.join(_MEMORY_DIR, "fallback_json")
_MIN_MEMORY_CHARS = 24
_LOW_VALUE_MESSAGES = {
    "yes", "yeah", "yep", "yup", "no", "nope", "ok", "okay", "k",
    "sure", "thanks", "thank you", "thx", "hi", "hello", "hey",
    "lol", "haha", "cool", "nice", "good", "great", "alright",
}
_MEMORY_SIGNAL_TERMS = {
    "feel", "feeling", "felt", "anxious", "anxiety", "depressed", "sad",
    "lonely", "alone", "stressed", "overwhelmed", "panic", "worried",
    "scared", "afraid", "angry", "grief", "trauma", "sleep", "eating",
    "job", "work", "school", "family", "friend", "partner", "relationship",
    "mother", "father", "brother", "sister", "goal", "want", "need",
    "struggle", "can't", "cannot", "diagnosed", "therapy", "medication",
    "suicide", "self harm", "hurt myself", "kill myself",
}


class _LocalSentenceTransformerEmbeddings:
    """Minimal LangChain-compatible local embedding adapter."""

    def __init__(self, model_name: str):
        try:
            from transformers.utils import logging as transformers_logging
            transformers_logging.set_verbosity_error()
        except Exception:
            pass

        from sentence_transformers import SentenceTransformer

        model_path = _resolve_local_model_path(model_name)
        if logger.isEnabledFor(logging.DEBUG):
            self.model = SentenceTransformer(
                model_path,
                device="cpu",
                local_files_only=True,
            )
        else:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.model = SentenceTransformer(
                    model_path,
                    device="cpu",
                    local_files_only=True,
                )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [vector.tolist() for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def _safe_user_id(user_id: str) -> str:
    """Make a stable filesystem-safe user key."""
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(user_id))
    return safe[:80] or "unknown"


def _resolve_local_model_path(model_name: str) -> str:
    """
    Return a cached snapshot path when available.

    Newer sentence-transformers versions may still ask Hugging Face for optional
    files when given a repo id. A direct snapshot path keeps startup fully local.
    """
    cache_home = os.environ.get("HF_HOME") or os.path.join(os.path.expanduser("~"), ".cache", "huggingface")
    repo_cache = os.path.join(
        cache_home,
        "hub",
        "models--" + model_name.replace("/", "--"),
    )
    ref_path = os.path.join(repo_cache, "refs", "main")
    try:
        with open(ref_path, "r", encoding="utf-8") as f:
            revision = f.read().strip()
        snapshot_path = os.path.join(repo_cache, "snapshots", revision)
        if os.path.isdir(snapshot_path):
            return snapshot_path
    except Exception:
        pass

    return model_name


def _fallback_path(user_id: str) -> str:
    return os.path.join(_FALLBACK_DIR, f"user_{_safe_user_id(user_id)}.jsonl")


def _memory_id(user_id: str, session_id: Optional[str], content: str) -> str:
    """Deterministic id prevents duplicate vector rows for retried saves."""
    raw = f"{user_id}|{session_id or 'unknown'}|{content.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _is_semantic_memory_worthy(message: str) -> bool:
    """
    Decide whether a user turn is worth semantic recall.

    Chroma should hold meaningful user context, not every acknowledgement.
    Prisma remains the full transcript source of truth.
    """
    text = (message or "").strip()
    lower = text.lower()
    if not lower:
        return False
    if lower in _LOW_VALUE_MESSAGES:
        return False
    if len(lower) < _MIN_MEMORY_CHARS:
        return any(term in lower for term in _MEMORY_SIGNAL_TERMS)
    if "?" in lower and len(lower) < 45 and not any(term in lower for term in _MEMORY_SIGNAL_TERMS):
        return False
    return True


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def _store_fallback_memory(
    user_id: str,
    user_message: str,
    emotion: str,
    session_id: Optional[str],
    timestamp: str,
) -> bool:
    """Append an embedded memory to a local JSONL fallback store."""
    os.makedirs(_FALLBACK_DIR, exist_ok=True)
    record_id = _memory_id(user_id, session_id, user_message)
    path = _fallback_path(user_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        existing = json.loads(line)
                        if existing.get("id") == record_id:
                            logger.debug("Fallback semantic memory already exists; skipping duplicate")
                            return True
                    except Exception:
                        continue
        except Exception:
            pass

    embedding = _get_embeddings().embed_query(user_message)

    record = {
        "id": record_id,
        "content": user_message,
        "embedding": embedding,
        "metadata": {
            "role": "user",
            "emotion": emotion,
            "timestamp": timestamp,
            "session_id": session_id or "unknown",
        },
    }

    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    logger.info("Stored user message in fallback semantic store | user=%s", user_id[:8])
    return True


async def _retrieve_fallback_memories(
    user_id: str,
    query: str,
    k: int,
    session_id: Optional[str],
    exclude_session_id: Optional[str],
) -> list[dict]:
    """Semantic retrieval from the JSONL fallback store."""
    path = _fallback_path(user_id)
    if not os.path.exists(path):
        return []

    query_embedding = _get_embeddings().embed_query(query)
    scored = []

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                metadata = record.get("metadata", {})
                if metadata.get("role") != "user":
                    continue
                if session_id and metadata.get("session_id") != session_id:
                    continue
                if exclude_session_id and metadata.get("session_id") == exclude_session_id:
                    continue

                similarity = _cosine_similarity(query_embedding, record.get("embedding", []))
                if similarity < 0.25:
                    continue

                recency_bonus = 0.0
                try:
                    ts = metadata.get("timestamp", "")
                    if ts:
                        mem_date = datetime.fromisoformat(ts)
                        days_ago = (datetime.now() - mem_date).days
                        if days_ago <= 7:
                            recency_bonus = 0.1 * (1 - days_ago / 7)
                except Exception:
                    pass

                scored.append((similarity + recency_bonus, record))
            except Exception:
                continue

    scored.sort(key=lambda item: item[0], reverse=True)

    memories = []
    for score, record in scored[:k]:
        metadata = record.get("metadata", {})
        content = record.get("content", "")[:200]
        if len(record.get("content", "")) > 200:
            content += "..."
        memories.append({
            "content": content,
            "role": metadata.get("role", "user"),
            "emotion": metadata.get("emotion", "neutral"),
            "timestamp": metadata.get("timestamp", ""),
            "relevance_score": round(min(score, 1.0), 2),
        })

    logger.info("Retrieved fallback semantic memories | count=%s", len(memories))
    return memories


async def _delete_fallback_session_memories(user_id: str, session_id: str) -> int:
    """Remove fallback JSONL memories belonging to a deleted session."""
    path = _fallback_path(user_id)
    if not os.path.exists(path):
        return 0

    kept: list[str] = []
    deleted = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                record = json.loads(line)
                metadata = record.get("metadata", {})
                if metadata.get("session_id") == session_id:
                    deleted += 1
                    continue
            except Exception:
                pass
            kept.append(line)

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(kept)

    return deleted


def _get_embeddings():
    """Get or create the embeddings model (lazy loading)."""
    global _embeddings
    
    if _embeddings is None:
        # Avoid repeated HuggingFace network probes after the model is cached.
        # If the model is not present locally, the exception is caught by callers
        # and semantic memory degrades gracefully.
        try:
            logger.info("Loading embedding model | model=all-MiniLM-L6-v2")
            _embeddings = _LocalSentenceTransformerEmbeddings("sentence-transformers/all-MiniLM-L6-v2")
            logger.info("Embedding model loaded")
            
        except ImportError:
            logger.warning("sentence-transformers not installed; falling back to langchain-huggingface")
            model_kwargs = {'device': 'cpu', 'local_files_only': True}
            from langchain_community.embeddings import HuggingFaceEmbeddings
            
            _embeddings = HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2",
                model_kwargs=model_kwargs,
                encode_kwargs={'normalize_embeddings': True}
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
    
    # Cache per-user to avoid repeated disk I/O
    if user_id in _vectorstore_cache:
        return _vectorstore_cache[user_id]

    embeddings = _get_embeddings()
    
    # Create user-specific collection
    collection_name = f"user_{_safe_user_id(user_id).replace('-', '_')[:50]}"
    
    vectorstore = Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=_MEMORY_DIR
    )
    
    _vectorstore_cache[user_id] = vectorstore
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
    if not _is_semantic_memory_worthy(user_message):
        logger.debug("Semantic memory skipped | reason=low_value_turn")
        return True

    try:
        vectorstore = _get_vectorstore(user_id)
        
        # Create a combined document for the conversation turn
        timestamp = datetime.now().isoformat()
        
        # Store ONLY user message  clean text, no prefix (no "User said:")
        user_doc = user_message  # Clean text for best embedding quality
        user_metadata = {
            "role": "user",
            "emotion": emotion,
            "timestamp": timestamp,
            "session_id": session_id or "unknown",
            "source": "conversation_turn",
        }
        doc_id = _memory_id(user_id, session_id, user_doc)
        
        # Add only user message (assistant responses never retrieved  no point storing them)
        vectorstore.add_texts(
            texts=[user_doc],
            metadatas=[user_metadata],
            ids=[doc_id],
        )
        
        logger.info("Stored semantic memory in ChromaDB | user=%s", user_id[:8])
        return True
        
    except Exception as e:
        if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
            logger.debug("Chroma semantic memory already exists; skipping duplicate")
            return True
        logger.warning("Chroma store failed; trying fallback semantic store | error=%s", str(e)[:100])
        try:
            timestamp = datetime.now().isoformat()
            return await _store_fallback_memory(
                user_id=user_id,
                user_message=user_message,
                emotion=emotion,
                session_id=session_id,
                timestamp=timestamp,
            )
        except Exception as fallback_err:
            logger.warning("Semantic memory store failed | error=%s", str(fallback_err)[:100])
            return False


async def retrieve_relevant_memories(
    user_id: str,
    query: str,
    k: int = 5,
    session_id: Optional[str] = None,
    exclude_session_id: Optional[str] = None,
) -> list[dict]:
    """
    Retrieve relevant past conversations based on semantic similarity.
    
    Args:
        user_id: User's unique identifier
        query: The current message to find relevant context for
        k: Number of relevant memories to retrieve
        session_id: Optional session ID to filter memories
        exclude_session_id: Optional session ID to skip, usually the active
            session because LangGraph already has those messages
        
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
            results = vectorstore.similarity_search_with_score(query, k=k * 4)  # Fetch extra, filter below
        
        memories = []
        for doc, score in results:
            # Threshold: normalized embeddings use L2 distance in roughly 0-2.
            # 1.3 keeps adjacent emotional/work themes while filtering weak matches.
            if score < 1.3:
                # Skip non-user messages (we no longer store assistant messages,
                # but guard against old data in the store)
                if doc.metadata.get("role") != "user":
                    continue
                if exclude_session_id and doc.metadata.get("session_id") == exclude_session_id:
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
        
        logger.info("Retrieved semantic memories | count=%s", len(memories))
        return memories
        
    except Exception as e:
        logger.warning("Chroma retrieve failed; trying fallback semantic store | error=%s", str(e)[:100])
        try:
            return await _retrieve_fallback_memories(user_id, query, k, session_id, exclude_session_id)
        except Exception as fallback_err:
            logger.warning("Semantic memory retrieve failed | error=%s", str(fallback_err)[:100])
            return []


async def get_memory_context_for_prompt(
    user_id: str,
    current_message: str,
    max_memories: int = 3,
    session_id: Optional[str] = None,
    exclude_session_id: Optional[str] = None,
) -> str:
    """
    Get formatted memory context to include in LLM prompts.
    
    Args:
        user_id: User's unique identifier
        current_message: The user's current message
        max_memories: Maximum number of memories to include
        session_id: Optional session ID to filter memories to current session only
        exclude_session_id: Optional session ID to omit from recall
        
    Returns:
        Formatted string of relevant memories for prompt injection
    """
    memories = await retrieve_relevant_memories(
        user_id, 
        current_message, 
        k=max_memories,
        session_id=session_id,
        exclude_session_id=exclude_session_id,
    )
    
    if not memories:
        return ""
    
    # Format memories for prompt
    context_parts = ["APPROXIMATE PAST CONTEXT (may not be exact  use as gentle reference only):"]
    
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


async def delete_session_memories(user_id: str, session_id: str) -> dict:
    """
    Delete semantic memories for a removed Prisma/Supabase session.

    This keeps the semantic index aligned with the source-of-truth database.
    Non-fatal: callers should not fail user deletion if Chroma cleanup has an issue.
    """
    deleted = {"chroma": 0, "fallback": 0}
    if not user_id or not session_id:
        return deleted

    try:
        vectorstore = _get_vectorstore(user_id)
        collection = getattr(vectorstore, "_collection", None)
        if collection is not None:
            collection.delete(where={"session_id": session_id})
            deleted["chroma"] = -1  # Chroma delete does not reliably return a count
            logger.info("Deleted Chroma memories for session | session=%s", session_id[:12])
    except Exception as e:
        logger.warning("Chroma session cleanup failed | error=%s", str(e)[:100])

    try:
        deleted["fallback"] = await _delete_fallback_session_memories(user_id, session_id)
    except Exception as e:
        logger.warning("Fallback session cleanup failed | error=%s", str(e)[:100])

    return deleted


async def delete_user_memories(user_id: str) -> dict:
    """
    Delete all semantic memories for a user during account/data erasure.
    """
    deleted = {"chroma": False, "fallback": False}
    if not user_id:
        return deleted

    try:
        vectorstore = _get_vectorstore(user_id)
        collection = getattr(vectorstore, "_collection", None)
        if collection is not None:
            ids = collection.get(include=[]) or {}
            id_list = ids.get("ids", [])
            if id_list:
                collection.delete(ids=id_list)
            deleted["chroma"] = True
            _vectorstore_cache.pop(user_id, None)
            logger.info("Deleted Chroma memories for user | user=%s", user_id[:8])
    except Exception as e:
        logger.warning("Chroma user cleanup failed | error=%s", str(e)[:100])

    try:
        path = _fallback_path(user_id)
        if os.path.exists(path):
            os.remove(path)
        deleted["fallback"] = True
    except Exception as e:
        logger.warning("Fallback user cleanup failed | error=%s", str(e)[:100])

    return deleted


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
