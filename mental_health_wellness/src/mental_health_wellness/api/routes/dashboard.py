"""Dashboard analytics and clinical history endpoints."""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from src.mental_health_wellness.db.client import get_prisma_client
from src.mental_health_wellness.security.compliance import enforce_user_scope

router = APIRouter()


@router.get("/api/dashboard/user/{user_id}")
@router.get("/dashboard/user/{user_id}")
async def get_user_dashboard(
    user_id: str,
    days: int = Query(30, ge=1, le=365, description="Rolling analytics window in days"),
) -> dict[str, Any]:
    """Return the advanced analytics dashboard payload for one user."""
    try:
        from src.mental_health_wellness.services.dashboard_analytics import build_user_dashboard
        return await build_user_dashboard(user_id=user_id, days=days)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/api/dashboard/health")
async def dashboard_health() -> dict[str, str]:
    return {"status": "ok", "dashboard": "available"}


@router.get("/api/dashboard/stats")
async def get_dashboard_stats(user_id: str):
    """Legacy dashboard stats endpoint — delegates to build_user_dashboard."""
    try:
        from src.mental_health_wellness.services.dashboard_analytics import build_user_dashboard

        dashboard = await build_user_dashboard(user_id=user_id, days=30)
        profile = dashboard.get("personalization", {}).get("profile", {})
        mood = dashboard.get("mood", {})
        overview = dashboard.get("overview", {})
        techniques = dashboard.get("techniques", {})
        sessions = dashboard.get("sessions", {})

        trend_label = (mood.get("trend") or {}).get("label")
        mood_trend = "up" if trend_label == "improving" else "down" if trend_label == "declining" else "stable"
        anxiety_value = float(profile.get("anxiety_baseline", 0.5) or 0.5)
        resilience_value = float(profile.get("resilience_score", 0.5) or 0.5)

        one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        sessions_this_week = sum(
            1
            for s in (sessions.get("recent") or [])
            if s.get("started_at")
            and datetime.fromisoformat(str(s["started_at"]).replace("Z", "+00:00")) >= one_week_ago
        )

        ranked = techniques.get("ranked") or []
        if ranked:
            top_techniques = [
                {
                    "name": item.get("name") or "Unnamed technique",
                    "category": item.get("category") or "general",
                    "usage_count": item.get("usageCount", 0),
                    "mean_effectiveness": item.get("meanEffectiveness"),
                    "composite_score": item.get("compositeScore"),
                }
                for item in ranked[:5]
            ]
        else:
            top_techniques = [
                {
                    "name": item.get("technique", {}).get("name") or item.get("technique_id") or "Unnamed technique",
                    "category": item.get("technique", {}).get("category") or "general",
                    "usage_count": 1,
                }
                for item in (techniques.get("ratings") or [])[:5]
            ]

        symptoms = profile.get("top_symptoms") or []
        secondary = profile.get("top_secondary_emotions") or []
        triggers = profile.get("emotional_triggers") or []
        distortions = profile.get("top_distortions") or []
        if symptoms and secondary:
            ai_insight = (
                f"Recent patterns connect {' and '.join(secondary[:2])} with "
                f"{symptoms[0].replace('_', ' ')}. "
                f"Track both the feeling and cognitive signal before deciding which support helps."
            )
        elif triggers and distortions:
            ai_insight = (
                f"Recent patterns connect {' and '.join(triggers[:2])} with {distortions[0]}. "
                f"Keep support focused on that trigger before choosing an exercise."
            )
        elif symptoms:
            ai_insight = (
                f"The clearest current signal is {symptoms[0].replace('_', ' ')}. "
                f"Improvement should be judged by whether that symptom eases."
            )
        elif triggers:
            ai_insight = (
                f"The clearest current trigger is {triggers[0]}. "
                f"Keep tracking what changes before and after that situation."
            )
        else:
            ai_insight = (
                "More check-ins will make the profile sharper. "
                "Current analytics are ready, but personalization improves with repeated mood and technique feedback."
            )

        return {
            "total_sessions": overview.get("total_sessions", 0),
            "sessions_this_week": sessions_this_week,
            "avg_mood": round(float(mood.get("average_score", 5.0) or 5.0) * 10),
            "streak": overview.get("current_checkin_streak", 0),
            "top_emotion": str(overview.get("most_common_emotion", "neutral")).lower(),
            "mood_trend": mood_trend,
            "techniques_tried": techniques.get("total_used", 0),
            "mood_timeline": mood.get("timeline", []),
            "emotion_distribution": [
                {"emotion": str(name).lower(), "count": count, "percentage": 0}
                for name, count in (mood.get("distribution") or {}).items()
            ],
            "top_techniques": top_techniques,
            "recent_sessions": sessions.get("recent", []),
            "psychological_profile": {
                "coping_style": profile.get("coping_style", "mixed"),
                "resilience": round(resilience_value * 100),
                "anxiety_baseline": "High" if anxiety_value >= 0.65 else "Low" if anxiety_value <= 0.35 else "Moderate",
                "ai_insight": ai_insight,
                "top_distortions": distortions,
                "emotional_triggers": triggers,
                "top_symptoms": symptoms,
                "top_behaviors": profile.get("top_behaviors") or [],
                "top_contexts": profile.get("top_contexts") or [],
            },
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        print(f"[DASHBOARD] Error computing dashboard stats for {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/user/{user_id}/clinical-history")
async def get_clinical_history(user_id: str, request: Request, days: int = 90):
    """PHQ-9/GAD-7 assessment history for dashboard trend visualization."""
    try:
        enforce_user_scope(request, user_id)
        days = max(1, min(int(days), 365))
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        prisma = await get_prisma_client()
        logs = await prisma.clinicalassessmentlog.find_many(
            where={"userId": user_id, "assessedAt": {"gte": cutoff}},
            order={"assessedAt": "asc"},
        )
        latest = logs[-1] if logs else None
        return {
            "user_id": user_id,
            "days": days,
            "assessments": [
                {
                    "assessed_at": log.assessedAt.isoformat() if log.assessedAt else None,
                    "severity": str(log.severity).split(".")[-1] if log.severity else "MINIMAL",
                    "phq9_score": float(log.phq9Score) if log.phq9Score is not None else 0.0,
                    "gad7_score": float(log.gad7Score) if log.gad7Score is not None else 0.0,
                    "indicators": list(log.indicators or []),
                    "confidence": float(log.confidence) if log.confidence is not None else 0.0,
                    "delta": float(log.clinicalDelta) if log.clinicalDelta is not None else None,
                }
                for log in logs
            ],
            "current_severity": str(latest.severity).split(".")[-1] if latest and latest.severity else "MINIMAL",
            "improving": (
                latest.clinicalDelta is not None and float(latest.clinicalDelta) < 0
            ) if latest else False,
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[CLINICAL_HISTORY] {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
