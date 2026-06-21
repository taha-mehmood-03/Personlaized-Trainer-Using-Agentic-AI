"""Session management endpoints: list, messages, rename, delete, new."""

from fastapi import APIRouter, HTTPException, Request

from src.mental_health_wellness.agent.graph import clear_session_context
from src.mental_health_wellness.api.helpers import (
    _clean_enum,
    _emotion_payload_from_message,
    schedule_audit_event,
)
from src.mental_health_wellness.api.models import SessionRenameRequest
from src.mental_health_wellness.db.client import get_prisma_client
from src.mental_health_wellness.security.compliance import enforce_user_scope, record_audit_event
from src.mental_health_wellness.services.cache_state import (
    invalidate_session_cache,
    invalidate_user_cache,
    session_cache_version,
    user_cache_version,
)

from typing import Any

router = APIRouter()

_USER_SESSIONS_CACHE: dict[tuple[str, int, bool, int], dict[str, Any]] = {}
_SESSION_MESSAGES_CACHE: dict[tuple[str, int], dict[str, Any]] = {}


@router.get("/api/user/{user_id}/sessions")
async def get_user_sessions(
    user_id: str, request: Request, limit: int = 10, include_messages: bool = False
):
    """Get a user's recent session summaries, optionally including messages."""
    try:
        enforce_user_scope(request, user_id)
        limit = max(1, min(limit, 100))
        cache_key = (user_id, limit, include_messages, user_cache_version(user_id))
        cached = _USER_SESSIONS_CACHE.get(cache_key)
        if cached:
            schedule_audit_event(
                event_type="DATA_ACCESS",
                action="sessions.read",
                subject_user_id=user_id,
                resource_type="session",
                purpose="user chat history",
                legal_basis="CONSENT",
                request=request,
                metadata={"limit": limit, "include_messages": include_messages, "cache": "hit"},
            )
            return cached

        prisma = await get_prisma_client()
        query: dict = {"where": {"userId": user_id}, "order": {"startedAt": "desc"}, "take": limit}
        if include_messages:
            query["include"] = {"messages": {"include": {"technique": True}}}

        sessions = await prisma.session.find_many(**query)

        user_ratings_map: dict = {}
        if include_messages:
            ratings = await prisma.usertechniquerating.find_many(where={"userId": user_id})
            for r in sorted(ratings, key=lambda x: 0 if x.sessionId is None else 1):
                user_ratings_map[(r.sessionId, r.techniqueId)] = r
                if not r.sessionId:
                    user_ratings_map[(None, r.techniqueId)] = r

        schedule_audit_event(
            prisma,
            event_type="DATA_ACCESS",
            action="sessions.read",
            subject_user_id=user_id,
            resource_type="session",
            purpose="user chat history",
            legal_basis="CONSENT",
            request=request,
            metadata={"limit": limit, "include_messages": include_messages},
        )

        result_sessions = []
        for s in sessions:
            session_messages = getattr(s, "messages", []) or []
            sorted_messages = sorted(session_messages, key=lambda m: m.createdAt) if include_messages else []
            result_sessions.append({
                "id": s.id,
                "title": s.title,
                "status": str(s.status),
                "mood_summary": str(s.moodSummary) if s.moodSummary else None,
                "started_at": s.startedAt.isoformat() if s.startedAt else None,
                "ended_at": s.endedAt.isoformat() if s.endedAt else None,
                "preview": sorted_messages[0].content[:100] if sorted_messages else None,
                "message_count": len(sorted_messages),
                "messages": [
                    {
                        "id": m.id,
                        "role": _clean_enum(m.role),
                        "content": m.content,
                        **_emotion_payload_from_message(m),
                        "createdAt": m.createdAt.isoformat() if m.createdAt else None,
                        "techniqueOfferedThisTurn": bool(getattr(m, "techniqueOfferedThisTurn", False)),
                        "technique": (
                            {
                                "id": m.technique.id,
                                "name": m.technique.name,
                                "brief": m.technique.brief,
                                "description": m.technique.description,
                                "steps": m.technique.steps,
                                "duration_minutes": m.technique.durationMinutes,
                                "difficulty": str(m.technique.difficulty),
                                "category": m.technique.category.name if m.technique.category else "General",
                                "why_it_works": m.technique.whyItWorks,
                                "avg_rating": m.technique.avgRating,
                                "effectiveness": m.technique.effectiveness,
                                "user_rating": (
                                    user_ratings_map.get((s.id, m.technique.id))
                                    or user_ratings_map.get((None, m.technique.id))
                                ).rating if (
                                    (s.id, m.technique.id) in user_ratings_map
                                    or (None, m.technique.id) in user_ratings_map
                                ) else None,
                                "user_completed": (
                                    user_ratings_map.get((s.id, m.technique.id))
                                    or user_ratings_map.get((None, m.technique.id))
                                ).completed if (
                                    (s.id, m.technique.id) in user_ratings_map
                                    or (None, m.technique.id) in user_ratings_map
                                ) else False,
                            }
                            if getattr(m, "technique", None) and getattr(m, "techniqueOfferedThisTurn", False)
                            else None
                        ),
                    }
                    for m in sorted_messages
                ] if include_messages else [],
            })

        response = {"status": "success", "sessions": result_sessions}
        for stale in [k for k in _USER_SESSIONS_CACHE if k[0] == user_id and k != cache_key]:
            _USER_SESSIONS_CACHE.pop(stale, None)
        _USER_SESSIONS_CACHE[cache_key] = response
        return response

    except Exception as e:
        print(f"[SESSIONS] Error fetching sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/session/{session_id}/messages")
async def get_session_messages(session_id: str, request: Request):
    """Get all messages from a specific session."""
    try:
        cache_key = (session_id, session_cache_version(session_id))
        cached = _SESSION_MESSAGES_CACHE.get(cache_key)
        if cached:
            enforce_user_scope(request, cached["user_id"])
            schedule_audit_event(
                event_type="DATA_ACCESS",
                action="session.messages.read",
                subject_user_id=cached["user_id"],
                resource_type="session",
                resource_id=session_id,
                purpose="user chat history",
                legal_basis="CONSENT",
                request=request,
            )
            return cached["response"]

        prisma = await get_prisma_client()
        session = await prisma.session.find_unique(where={"id": session_id})
        if session:
            enforce_user_scope(request, session.userId)

        messages = await prisma.message.find_many(
            where={"sessionId": session_id},
            order={"createdAt": "asc"},
            include={"technique": True},
        )

        user_ratings_map: dict = {}
        if session:
            ratings = await prisma.usertechniquerating.find_many(
                where={"userId": session.userId, "OR": [{"sessionId": session_id}, {"sessionId": None}]}
            )
            for r in sorted(ratings, key=lambda x: 0 if x.sessionId is None else 1):
                user_ratings_map[r.techniqueId] = r

        if session:
            schedule_audit_event(
                prisma,
                event_type="DATA_ACCESS",
                action="session.messages.read",
                subject_user_id=session.userId,
                resource_type="session",
                resource_id=session_id,
                purpose="user chat history",
                legal_basis="CONSENT",
                request=request,
            )

        response = {
            "status": "success",
            "session_id": session_id,
            "messages": [
                {
                    "id": m.id,
                    "role": _clean_enum(m.role),
                    "content": m.content,
                    **_emotion_payload_from_message(m),
                    "createdAt": m.createdAt.isoformat() if m.createdAt else None,
                    "techniqueOfferedThisTurn": bool(getattr(m, "techniqueOfferedThisTurn", False)),
                    "technique": (
                        {
                            "id": m.technique.id,
                            "name": m.technique.name,
                            "brief": m.technique.brief,
                            "description": m.technique.description,
                            "steps": m.technique.steps,
                            "duration_minutes": m.technique.durationMinutes,
                            "difficulty": str(m.technique.difficulty),
                            "category": m.technique.category.name if m.technique and m.technique.category else "General",
                            "why_it_works": m.technique.whyItWorks,
                            "avg_rating": m.technique.avgRating,
                            "effectiveness": m.technique.effectiveness,
                            "user_rating": user_ratings_map.get(m.technique.id).rating if m.technique.id in user_ratings_map else None,
                            "user_completed": user_ratings_map.get(m.technique.id).completed if m.technique.id in user_ratings_map else False,
                        }
                        if getattr(m, "technique", None) and getattr(m, "techniqueOfferedThisTurn", False)
                        else None
                    ),
                }
                for m in messages
            ],
        }

        if session:
            for stale in [k for k in _SESSION_MESSAGES_CACHE if k[0] == session_id and k != cache_key]:
                _SESSION_MESSAGES_CACHE.pop(stale, None)
            _SESSION_MESSAGES_CACHE[cache_key] = {"user_id": session.userId, "response": response}
        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/api/session/{session_id}/rename")
async def rename_session(session_id: str, request: SessionRenameRequest, http_request: Request):
    """Rename a chat session."""
    try:
        prisma = await get_prisma_client()
        session = await prisma.session.find_unique(where={"id": session_id})
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        enforce_user_scope(http_request, session.userId)

        title = request.title.strip()[:80]
        if not title:
            raise HTTPException(status_code=400, detail="Session title cannot be empty")

        updated = await prisma.session.update(where={"id": session_id}, data={"title": title})
        await record_audit_event(
            prisma,
            event_type="DATA_ACCESS",
            action="session.rename",
            subject_user_id=session.userId,
            resource_type="session",
            resource_id=session_id,
            purpose="user session management",
            legal_basis="CONSENT",
            request=http_request,
        )
        invalidate_user_cache(session.userId, session_id=session_id)
        return {"status": "success", "session_id": session_id, "title": updated.title}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/session/{session_id}")
async def delete_session(session_id: str, request: Request):
    """Delete a chat session and all its messages."""
    try:
        prisma = await get_prisma_client()
        session = await prisma.session.find_unique(where={"id": session_id})
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        enforce_user_scope(request, session.userId)

        try:
            from src.mental_health_wellness.memory import delete_session_memories
            cleanup = await delete_session_memories(session.userId, session_id)
            print(f"[SESSION-DELETE] Semantic memory cleanup: {cleanup}")
        except Exception as mem_err:
            print(f"[SESSION-DELETE] Memory cleanup failed (non-fatal): {str(mem_err)[:100]}")

        deleted_msgs = await prisma.message.delete_many(where={"sessionId": session_id})
        await prisma.session.delete(where={"id": session_id})
        await record_audit_event(
            prisma,
            event_type="SESSION_DELETE",
            action="session.delete",
            subject_user_id=session.userId,
            resource_type="session",
            resource_id=session_id,
            purpose="user initiated deletion",
            legal_basis="CONSENT",
            request=request,
            metadata={"deleted_messages": deleted_msgs},
        )
        invalidate_user_cache(session.userId, session_id=session_id)
        invalidate_session_cache(session_id)
        clear_session_context(session_id)

        return {"status": "success", "session_id": session_id, "message": "Session and all messages permanently deleted"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/session/new")
async def create_new_chat_session(request: Request):
    """Create a fresh session with clean in-memory context."""
    try:
        body = await request.json()
        user_id = body.get("user_id") or body.get("userId")
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")

        from src.mental_health_wellness.db.client import create_new_session as _db_create_session
        new_session = await _db_create_session(user_id)
        session_id = new_session["id"]

        clear_session_context(session_id)
        invalidate_user_cache(user_id)

        return {"status": "ok", "session_id": session_id, "message": "New session created with clean context"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
