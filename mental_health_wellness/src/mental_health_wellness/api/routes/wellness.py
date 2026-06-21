"""Wellness tips, technique catalogue, and technique rating endpoints."""

from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Request

from src.mental_health_wellness.api.models import (
    TechniqueRatingRequest,
    TechniqueRatingResponse,
    WellnessTip,
)
from src.mental_health_wellness.db.client import get_prisma_client
from src.mental_health_wellness.security.compliance import enforce_user_scope
from src.mental_health_wellness.services.cache_state import invalidate_user_cache

router = APIRouter()

_TECHNIQUES_CACHE_VERSION = 0
_TECHNIQUES_CACHE: dict[tuple[str | None, str | None, int], dict[str, Any]] = {}


def invalidate_techniques_cache() -> None:
    global _TECHNIQUES_CACHE_VERSION
    _TECHNIQUES_CACHE_VERSION += 1
    _TECHNIQUES_CACHE.clear()


async def _update_personalized_technique_preferences(
    prisma,
    user_id: str,
    technique_id: str,
    rating: Optional[int],
    completed: bool,
) -> None:
    try:
        technique = await prisma.technique.find_unique(
            where={"id": technique_id},
            include={"category": True},
        )
        category_name = technique.category.name if technique and technique.category else None
        if not category_name:
            return

        pref = await prisma.userpreference.find_unique(where={"userId": user_id})
        existing = list(getattr(pref, "preferredCategories", []) or []) if pref else []
        updated = list(existing)

        if rating is not None and rating <= 2:
            updated = [name for name in updated if name != category_name]
        elif (rating is not None and rating >= 4) or completed:
            if category_name not in updated:
                updated.append(category_name)
        else:
            return

        if updated == existing:
            return

        if pref:
            await prisma.userpreference.update(where={"userId": user_id}, data={"preferredCategories": updated})
        else:
            await prisma.userpreference.create(data={"userId": user_id, "preferredCategories": updated})

    except Exception as e:
        print(f"[WELLNESS] Preference update skipped: {str(e)[:80]}")


@router.get("/api/wellness/tips", response_model=List[WellnessTip])
async def get_wellness_tips():
    """Return a curated list of wellness tips."""
    return [
        WellnessTip(id="1", title="Practice Gratitude", description="Note three things you're grateful for each day.", category="mindfulness"),
        WellnessTip(id="2", title="Deep Breathing", description="Try 4-7-8 breathing when stressed.", category="breathing"),
        WellnessTip(id="3", title="Stay Connected", description="Reach out to someone today.", category="social"),
        WellnessTip(id="4", title="Move Your Body", description="Even a 10-minute walk helps.", category="physical"),
        WellnessTip(id="5", title="Limit News", description="Set specific times for news/social media.", category="boundaries"),
    ]


@router.get("/api/techniques")
async def get_techniques(emotion: Optional[str] = None, category: Optional[str] = None):
    """Get available techniques, optionally filtered by emotion or category."""
    try:
        cache_key = (
            emotion.strip().lower() if emotion else None,
            category.strip().lower() if category else None,
            _TECHNIQUES_CACHE_VERSION,
        )
        cached = _TECHNIQUES_CACHE.get(cache_key)
        if cached:
            return cached

        prisma = await get_prisma_client()
        where_conditions: dict[str, Any] = {"isActive": True}

        if emotion:
            emotion_map = {
                "fear": "ANXIETY",
                "anxiety": "ANXIETY",
                "sadness": "SADNESS",
                "anger": "ANGER",
                "joy": "JOY",
                "neutral": "NEUTRAL",
                "disgust": "ANGER",
                "surprise": "JOY",
            }
            target_emotion = emotion_map.get(emotion.lower(), emotion.upper())
            where_conditions["targetEmotions"] = {"hasSome": [target_emotion]}

        techniques = await prisma.technique.find_many(
            where=where_conditions,
            include={"category": True},
            order={"avgRating": "desc"},
        )

        normalized_category = category.strip().lower() if category else None
        response = {
            "status": "success",
            "techniques": [
                {
                    "id": t.id,
                    "name": t.name,
                    "brief": t.brief,
                    "description": t.description,
                    "category": t.category.name if t.category else "General",
                    "duration_minutes": t.durationMinutes,
                    "difficulty": str(t.difficulty),
                    "steps": t.steps,
                    "why_it_works": t.whyItWorks,
                    "avg_rating": t.avgRating,
                    "total_ratings": t.totalRatings,
                    "effectiveness": t.effectiveness,
                }
                for t in techniques
                if not normalized_category
                or (t.category and t.category.name.lower() == normalized_category)
            ],
        }
        _TECHNIQUES_CACHE[cache_key] = response
        return response

    except Exception as e:
        print(f"[WELLNESS] Error fetching techniques: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching techniques: {str(e)}")


@router.post("/api/technique/rate", response_model=TechniqueRatingResponse)
async def rate_technique(request: TechniqueRatingRequest, http_request: Request):
    """Submit rating and feedback for a technique."""
    try:
        if request.rating is not None and not (1 <= request.rating <= 5):
            raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")
        enforce_user_scope(http_request, request.user_id)

        prisma = await get_prisma_client()
        existing = await prisma.usertechniquerating.find_first(
            where={
                "userId": request.user_id,
                "techniqueId": request.technique_id,
                "sessionId": request.session_id,
            }
        )

        if existing:
            update_data: dict[str, Any] = {
                "completed": request.completed or getattr(existing, "completed", False)
            }
            if request.rating is not None:
                update_data["rating"] = request.rating
            if request.feedback is not None:
                update_data["feedback"] = request.feedback
            await prisma.usertechniquerating.update(where={"id": existing.id}, data=update_data)
        else:
            await prisma.usertechniquerating.create(
                data={
                    "userId": request.user_id,
                    "techniqueId": request.technique_id,
                    "rating": request.rating,
                    "feedback": request.feedback,
                    "completed": request.completed,
                    "sessionId": request.session_id,
                }
            )

        technique = await prisma.technique.find_unique(where={"id": request.technique_id})
        if technique and request.rating is not None:
            old_total = int(getattr(technique, "totalRatings", 0) or 0)
            old_avg = float(getattr(technique, "avgRating", 0.0) or 0.0)
            if existing and getattr(existing, "rating", None) is not None:
                existing_rating = int(existing.rating)
                if old_total > 0:
                    new_avg = round(((old_avg * old_total) - existing_rating + request.rating) / old_total, 2)
                    new_total = old_total
                else:
                    new_avg = float(request.rating)
                    new_total = 1
            else:
                new_total = old_total + 1
                new_avg = round(((old_avg * old_total) + request.rating) / new_total, 2)
            await prisma.technique.update(
                where={"id": request.technique_id},
                data={"avgRating": new_avg, "totalRatings": new_total},
            )

        await _update_personalized_technique_preferences(
            prisma=prisma,
            user_id=request.user_id,
            technique_id=request.technique_id,
            rating=request.rating,
            completed=request.completed,
        )
        invalidate_user_cache(request.user_id)
        invalidate_techniques_cache()

        return TechniqueRatingResponse(
            status="success",
            message="Thank you for your feedback!",
            technique_id=request.technique_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[WELLNESS] Error rating technique: {e}")
        raise HTTPException(status_code=500, detail=f"Error saving rating: {str(e)}")
