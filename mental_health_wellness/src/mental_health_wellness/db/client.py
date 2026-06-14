"""
Prisma Client - Database connection management
Uses prisma-client-py for type-safe database operations
"""

import os
from typing import Optional
from prisma import Prisma

# Global client instance
_prisma_client: Optional[Prisma] = None

# v6.0 FIX 4: Process-level cache for ensure_user_exists.
# After the first successful check, skip the DB call entirely.
_known_users: set = set()


async def get_prisma_client() -> Prisma:
    """
    Get or create Prisma client instance (singleton pattern)
    """
    global _prisma_client
    
    if _prisma_client is None:
        print("[DB] Initializing Prisma client...")
        _prisma_client = Prisma()
        try:
            print("[DB] Connecting to Prisma...")
            if not _prisma_client.is_connected():
                await _prisma_client.connect()
                print("[DB] Prisma client connected successfully")
            else:
                print("[DB] Prisma client already connected, reusing connection.")
        except Exception as e:
            print(f"[DB] Prisma connection failed: {e}")
            _prisma_client = None
            raise
    
    return _prisma_client


async def close_prisma_client():
    """
    Close Prisma client connection
    """
    global _prisma_client
    
    if _prisma_client is not None:
        await _prisma_client.disconnect()
        _prisma_client = None
        print("[DB] Prisma client disconnected")


async def ensure_user_exists_cached(user_id: str, email: str = None, name: str = None) -> dict:
    """
    v6.0 FIX 4: Cached ensure_user_exists  skips DB after first successful check.
    Saves ~200-500ms per message for returning users.
    """
    if user_id in _known_users:
        return {"id": user_id, "created": False}
    result = await ensure_user_exists(user_id, email, name)
    _known_users.add(user_id)
    return result


async def ensure_user_exists(user_id: str, email: str = None, name: str = None) -> dict:
    """
    Ensure a user exists in the database, create if not
    """
    prisma = await get_prisma_client()
    
    # Try to find existing user
    user = await prisma.user.find_unique(where={"id": user_id})
    
    if user:
        return {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "created": False
        }
    
    # Create new user
    user = await prisma.user.create(
        data={
            "id": user_id,
            "email": email or f"{user_id}@example.com",
            "name": name or f"User {user_id[:8]}"
        }
    )
    
    # Also create default preferences and statistics
    await prisma.userpreference.create(
        data={"userId": user.id}
    )
    
    await prisma.userstatistics.create(
        data={"userId": user.id}
    )
    
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "created": True
    }


async def create_new_session(user_id: str, title: str = None) -> dict:
    """
    Create a new session for a user in the database.
    
    Args:
        user_id: The user's unique identifier
        title: Optional title for the session
        
    Returns:
        Dictionary with session id and status
    """
    from datetime import datetime
    
    prisma = await get_prisma_client()
    
    # Create new session with ACTIVE status
    session = await prisma.session.create(
        data={
            "userId": user_id,
            "title": title or f"Chat - {datetime.now().strftime('%b %d, %H:%M')}",
            "status": "ACTIVE",
            "moodSummary": "NEUTRAL"
        }
    )
    
    print(f"[DB] Created new session: {session.id} for user: {user_id}")

    try:
        await prisma.userstatistics.upsert(
            where={"userId": user_id},
            data={
                "create": {
                    "userId": user_id,
                    "totalSessions": 1,
                    "lastSessionAt": session.startedAt,
                },
                "update": {
                    "totalSessions": {"increment": 1},
                    "lastSessionAt": session.startedAt,
                },
            },
        )
    except Exception as e:
        print(f"[DB] UserStatistics session refresh skipped: {str(e)[:100]}")

    try:
        from ..services.cache_state import invalidate_user_cache

        invalidate_user_cache(user_id, session_id=session.id)
    except Exception as cache_err:
        print(f"[DB] Session cache invalidation skipped: {str(cache_err)[:100]}")
    
    return {
        "id": session.id,
        "title": session.title,
        "status": str(session.status),
        "created": True
    }
