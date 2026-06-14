"""
Small in-process cache version registry.

Read endpoints can cache by user/session version. Write paths bump the relevant
version so cached dashboard, profile, session list, and message reads refresh
on the next request.
"""

from __future__ import annotations


_user_versions: dict[str, int] = {}
_session_versions: dict[str, int] = {}


def user_cache_version(user_id: str | None) -> int:
    if not user_id:
        return 0
    return _user_versions.get(user_id, 0)


def session_cache_version(session_id: str | None) -> int:
    if not session_id:
        return 0
    return _session_versions.get(session_id, 0)


def invalidate_user_cache(user_id: str | None, *, session_id: str | None = None) -> None:
    if user_id:
        _user_versions[user_id] = _user_versions.get(user_id, 0) + 1
    if session_id:
        invalidate_session_cache(session_id)


def invalidate_session_cache(session_id: str | None) -> None:
    if session_id:
        _session_versions[session_id] = _session_versions.get(session_id, 0) + 1
