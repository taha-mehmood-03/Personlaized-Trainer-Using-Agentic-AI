"""
Memory Module - local embedding-based recall.

Prisma/Supabase remains the source of truth for sessions, messages, facts,
summaries, and analytics. This module indexes selected records into Supabase
pgvector behind the existing memory API, with a local JSONL fallback if the
database vector index is unavailable.
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
_embeddings = None
_embeddings_error: Optional[str] = None
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


class EmbeddingsUnavailable(RuntimeError):
    """Raised when the local semantic embedding model is not available."""


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
    Decide whether a user turn is worth lightweight recall.

    Store meaningful user context, not every acknowledgement. Prisma remains
    the full transcript source of truth.
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
    embedding: Optional[list[float]] = None,
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

    embedding = embedding or _get_embeddings().embed_query(user_message)

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
    global _embeddings, _embeddings_error
    
    if _embeddings_error:
        raise EmbeddingsUnavailable(_embeddings_error)

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
            try:
                model_kwargs = {'device': 'cpu', 'local_files_only': True}
                from langchain_community.embeddings import HuggingFaceEmbeddings

                _embeddings = HuggingFaceEmbeddings(
                    model_name="sentence-transformers/all-MiniLM-L6-v2",
                    model_kwargs=model_kwargs,
                    encode_kwargs={'normalize_embeddings': True}
                )
            except Exception as exc:
                _embeddings_error = str(exc)
                logger.warning(
                    "Semantic embeddings unavailable; semantic memory will be skipped until restart | error=%s",
                    _embeddings_error[:160],
                )
                raise EmbeddingsUnavailable(_embeddings_error) from exc
        except Exception as exc:
            _embeddings_error = str(exc)
            logger.warning(
                "Semantic embeddings unavailable; semantic memory will be skipped until restart | error=%s",
                _embeddings_error[:160],
            )
            raise EmbeddingsUnavailable(_embeddings_error) from exc
            
    return _embeddings


def preload_embeddings():
    """Eagerly preload embedding model on startup."""
    try:
        _get_embeddings()
        return True
    except EmbeddingsUnavailable:
        return False


async def store_conversation_memory(
    user_id: str,
    user_message: str,
    assistant_response: str,
    emotion: str = "neutral",
    session_id: Optional[str] = None
) -> bool:
    """
    Store a conversation turn in pgvector-backed recall.
    
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
        embedding = _get_embeddings().embed_query(user_message)
    except EmbeddingsUnavailable:
        logger.debug("Semantic memory skipped | reason=embedding_model_unavailable")
        return True
    except Exception as err:
        logger.warning("Semantic memory skipped | embedding error=%s", str(err)[:100])
        return True

    try:
        from .pgvector_store import upsert_embedding

        timestamp = datetime.now().isoformat()
        stored = await upsert_embedding(
            source_type="message",
            source_id=_memory_id(user_id, session_id, user_message),
            user_id=user_id,
            session_id=session_id,
            content=user_message,
            metadata={"role": "user", "emotion": emotion, "timestamp": timestamp},
            embedding=embedding,
        )
        if stored:
            logger.info("Stored message embedding in pgvector | user=%s", user_id[:8])
            return True

        logger.warning("pgvector message store returned false; using local fallback")
        return await _store_fallback_memory(
            user_id=user_id,
            user_message=user_message,
            emotion=emotion,
            session_id=session_id,
            timestamp=timestamp,
            embedding=embedding,
        )
    except Exception as err:
        logger.warning("pgvector memory store failed; using local fallback | error=%s", str(err)[:100])
        try:
            timestamp = datetime.now().isoformat()
            return await _store_fallback_memory(
                user_id=user_id,
                user_message=user_message,
                emotion=emotion,
                session_id=session_id,
                timestamp=timestamp,
                embedding=embedding,
            )
        except Exception as fallback_err:
            logger.warning("Memory store failed | error=%s", str(fallback_err)[:100])
            return False


async def store_fact_embedding(user_id: str, fact_id: str, fact: str, category: str = "context") -> bool:
    """Index a UserFact row in pgvector."""
    try:
        from .pgvector_store import upsert_embedding
        embedding = _get_embeddings().embed_query(fact)

        return await upsert_embedding(
            source_type="user_fact",
            source_id=fact_id,
            user_id=user_id,
            content=fact,
            metadata={"category": category},
            embedding=embedding,
        )
    except EmbeddingsUnavailable:
        logger.debug("Fact embedding skipped | reason=embedding_model_unavailable")
        return True
    except Exception as err:
        logger.warning("Fact embedding store failed | error=%s", str(err)[:100])
        return False


async def store_session_summary_embedding(
    user_id: str,
    session_id: str,
    summary_id: str,
    title: str,
    summary: str,
    emotion: str = "neutral",
) -> bool:
    """Index a SessionSummary row in pgvector."""
    try:
        from .pgvector_store import upsert_embedding
        content = f"{title}\n{summary}".strip()
        embedding = _get_embeddings().embed_query(content)

        return await upsert_embedding(
            source_type="session_summary",
            source_id=summary_id,
            user_id=user_id,
            session_id=session_id,
            content=content,
            metadata={"title": title, "emotion": emotion},
            embedding=embedding,
        )
    except EmbeddingsUnavailable:
        logger.debug("Session summary embedding skipped | reason=embedding_model_unavailable")
        return True
    except Exception as err:
        logger.warning("Session summary embedding store failed | error=%s", str(err)[:100])
        return False


async def store_technique_embedding(technique) -> bool:
    """Index a Technique row in pgvector for semantic technique matching."""
    try:
        from .pgvector_store import upsert_embedding

        text = " | ".join([
            getattr(technique, "name", "") or "",
            getattr(technique, "brief", "") or "",
            getattr(technique, "description", "") or "",
            getattr(technique, "whyItWorks", "") or "",
            " ".join(getattr(technique, "steps", []) or [])[:500],
        ]).strip()
        if not text:
            return False
        embedding = _get_embeddings().embed_query(text)
        return await upsert_embedding(
            source_type="technique",
            source_id=getattr(technique, "id", ""),
            content=text,
            metadata={
                "name": getattr(technique, "name", ""),
                "categoryId": getattr(technique, "categoryId", ""),
            },
            embedding=embedding,
        )
    except EmbeddingsUnavailable:
        logger.debug("Technique embedding skipped | reason=embedding_model_unavailable")
        return True
    except Exception as err:
        logger.warning("Technique embedding store failed | error=%s", str(err)[:100])
        return False


async def retrieve_relevant_memories(
    user_id: str,
    query: str,
    k: int = 5,
    session_id: Optional[str] = None,
    exclude_session_id: Optional[str] = None,
) -> list[dict]:
    """
    Retrieve relevant past conversations/facts/summaries by pgvector similarity.

    Falls back to the local JSONL store if pgvector is unavailable.
    """
    try:
        _get_embeddings()
    except EmbeddingsUnavailable:
        logger.debug("Semantic memory retrieval skipped | reason=embedding_model_unavailable")
        return []
    except Exception as err:
        logger.warning("Semantic memory retrieval skipped | embedding error=%s", str(err)[:100])
        return []

    try:
        from .pgvector_store import search_embeddings

        rows = await search_embeddings(
            query=query,
            user_id=user_id,
            source_types=["message", "user_fact", "session_summary"],
            limit=k,
            exclude_session_id=exclude_session_id,
        )
        memories = []
        for row in rows:
            metadata = row.get("metadata") or {}
            content = (row.get("content") or "")[:200]
            if len(row.get("content") or "") > 200:
                content += "..."
            memories.append({
                "content": content,
                "role": metadata.get("role", row.get("sourceType", "memory")),
                "emotion": metadata.get("emotion", "neutral"),
                "timestamp": metadata.get("timestamp", ""),
                "relevance_score": round(float(row.get("similarity") or 0.0), 2),
            })
        if memories:
            logger.info("Retrieved pgvector memories | count=%s", len(memories))
            return memories
    except Exception as err:
        logger.warning("pgvector memory retrieve failed; using local fallback | error=%s", str(err)[:100])

    try:
        return await _retrieve_fallback_memories(user_id, query, k, session_id, exclude_session_id)
    except Exception as err:
        logger.warning("Memory retrieve failed | error=%s", str(err)[:100])
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
    Delete local recall records for a removed Prisma/Supabase session.

    This keeps recall aligned with the source-of-truth database. Non-fatal:
    callers should not fail user deletion if cleanup has an issue.
    """
    deleted = {"pgvector": 0, "local": 0}
    if not user_id or not session_id:
        return deleted

    try:
        from .pgvector_store import delete_embeddings

        deleted["pgvector"] = await delete_embeddings(user_id=user_id, session_id=session_id)
    except Exception as e:
        logger.warning("pgvector session cleanup failed | error=%s", str(e)[:100])

    try:
        deleted["local"] = await _delete_fallback_session_memories(user_id, session_id)
    except Exception as e:
        logger.warning("Memory session cleanup failed | error=%s", str(e)[:100])

    return deleted


async def delete_user_memories(user_id: str) -> dict:
    """
    Delete all local recall records for a user during account/data erasure.
    """
    deleted = {"pgvector": False, "local": False}
    if not user_id:
        return deleted

    try:
        from .pgvector_store import delete_embeddings

        await delete_embeddings(user_id=user_id)
        deleted["pgvector"] = True
    except Exception as e:
        logger.warning("pgvector user cleanup failed | error=%s", str(e)[:100])

    try:
        path = _fallback_path(user_id)
        if os.path.exists(path):
            os.remove(path)
        deleted["local"] = True
    except Exception as e:
        logger.warning("Memory user cleanup failed | error=%s", str(e)[:100])

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
    except EmbeddingsUnavailable as e:
        return {
            "status": "degraded",
            "error": f"embedding_model_unavailable: {str(e)[:160]}",
            "storage_path": _MEMORY_DIR,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }
