"""Health check endpoints."""

from datetime import datetime

from fastapi import APIRouter

from src.mental_health_wellness.agent import check_agent_health
from src.mental_health_wellness.api.models import HealthResponse
from src.mental_health_wellness.db.client import get_prisma_client

router = APIRouter()


@router.get("/", response_model=dict)
async def root():
    return {
        "message": "Mental Health Wellness API - Agent Version",
        "status": "healthy",
        "version": "3.0.0",
    }


@router.get("/health", response_model=HealthResponse)
async def health_check():
    db_connected = False
    agent_ready = False

    try:
        prisma = await get_prisma_client()
        await prisma.user.count()
        db_connected = True
    except Exception as e:
        print(f"[HEALTH] DB check failed: {e}")

    try:
        health = check_agent_health()
        agent_ready = health.get("agent_ready", False)
    except Exception as e:
        print(f"[HEALTH] Agent check failed: {e}")

    return HealthResponse(
        status="healthy" if db_connected and agent_ready else "degraded",
        version="3.0.0",
        agent_ready=agent_ready,
        database_connected=db_connected,
        timestamp=datetime.now().isoformat(),
    )
