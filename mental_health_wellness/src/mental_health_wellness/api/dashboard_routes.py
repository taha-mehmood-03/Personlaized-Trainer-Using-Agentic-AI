"""
Dashboard analytics API routes.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..services.dashboard_analytics import build_user_dashboard


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/user/{user_id}")
async def get_user_dashboard(
    user_id: str,
    days: int = Query(30, ge=1, le=365, description="Rolling analytics window in days"),
) -> dict[str, Any]:
    """
    Return the advanced analytics dashboard payload for one user.
    """
    try:
        return await build_user_dashboard(user_id=user_id, days=days)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/health")
async def dashboard_health() -> dict[str, str]:
    return {"status": "ok", "dashboard": "available"}
