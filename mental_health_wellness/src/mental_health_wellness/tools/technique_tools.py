"""
Technique Tools - Smarter selection with intensity-based routing,
unused-first scoring, and top-3 alternatives.
"""

from langchain_core.tools import tool
from typing import Dict, List

# Intensity  preferred categories mapping
INTENSITY_CATEGORY_MAP = {
    "high":     ["Breathing", "DBT"],                            #  0.7: immediate physical relief
    "moderate": ["Mindfulness", "CBT", "DBT"],                   # 0.40.7
    "low":      ["Journaling", "Behavioral Activation", "CBT"],  # < 0.4: reflective
}


def _intensity_tier(intensity: float) -> str:
    if intensity >= 0.7:
        return "high"
    elif intensity >= 0.4:
        return "moderate"
    return "low"


def _score(technique, recently_used: set) -> float:
    """
    Priority scoring:
      Unused + has rating   avgRating          (best first)
      Unused + no rating    0.5                (neutral placeholder)
      Used recently         avgRating * 0.5    (penalise repetition)
    """
    rating = technique.avgRating or 0.0
    used = technique.id in recently_used
    if used:
        return rating * 0.5
    return rating if rating > 0 else 0.5


@tool
async def recommend_technique(
    emotion: str,
    intensity: float = 0.5,
    user_id: str = ""
) -> List[Dict]:
    """
    Return the top-3 ranked techniques for the given emotion and intensity.

    Selection logic:
      1. Prefer categories mapped to the intensity tier (high/moderate/low).
      2. Score each candidate: unused+rated > unused+unrated > used (penalised).
      3. Return top 3 sorted by score (desc).  Falls back to all categories if
         preferred ones yield < 3 results.

    Args:
        emotion:    Detected emotion string.
        intensity:  Fused emotion intensity 0.01.0.
        user_id:    For personalization (avoid recently recommended).

    Returns:
        List of up to 3 technique dicts, best first.  Empty list on error.
    """
    try:
        from ..db.client import get_prisma_client
        prisma = await get_prisma_client()

        emotion_map = {
            "fear": "FEAR", "anxiety": "ANXIETY", "sadness": "SADNESS",
            "anger": "ANGER", "joy": "JOY", "neutral": "NEUTRAL",
            "disgust": "DISGUST", "surprise": "SURPRISE",
        }
        target_emotion = emotion_map.get(emotion.lower(), emotion.upper())
        tier = _intensity_tier(intensity)
        preferred_cats = INTENSITY_CATEGORY_MAP[tier]

        print(f"[TOOL] recommend_technique: emotion={emotion.upper()} "
              f"intensity={intensity:.0%} tier={tier} preferred={preferred_cats}")

        #  Lookup tables 
        all_cats = await prisma.techniquecategory.find_many()
        cat_id_to_name = {c.id: c.name for c in all_cats}
        cat_name_to_id = {c.name: c.id for c in all_cats}

        #  Recently used (personalization) 
        recently_used: set = set()
        if user_id:
            try:
                # Find recent messages by this user's assistant that have a techniqueId
                recent_msgs = await prisma.message.find_many(
                    where={
                        "session": {"userId": user_id},
                        "role": "ASSISTANT",
                        "techniqueId": {"not": None}
                    },
                    order={"createdAt": "desc"},
                    take=10
                )
                for msg in recent_msgs:
                    if msg.techniqueId:
                        recently_used.add(msg.techniqueId)
                print(f"[TOOL]   recently_used: {len(recently_used)} techniques")
            except Exception as e:
                print(f"[TOOL]   WARNING  history fetch failed: {str(e)[:60]}")

        #  DB fetch (preferred categories first) 
        preferred_ids = [cat_name_to_id[n] for n in preferred_cats if n in cat_name_to_id]

        candidates = []
        if preferred_ids:
            preferred_hits = await prisma.technique.find_many(
                where={
                    "isActive": True,
                    "targetEmotions": {"hasSome": [target_emotion]},
                    "categoryId": {"in": preferred_ids},
                }
            )
            candidates = preferred_hits

        # Fall back to all categories if we don't have enough preferred results
        if len(candidates) < 3:
            all_hits = await prisma.technique.find_many(
                where={
                    "isActive": True,
                    "targetEmotions": {"hasSome": [target_emotion]},
                }
            )
            # De-duplicate: keep preferred hits + non-preferred ones
            seen_ids = {t.id for t in candidates}
            for t in all_hits:
                if t.id not in seen_ids:
                    candidates.append(t)

        # Final Fallback for Neutral/Joy: If STILL empty, just fetch ANY active technique
        # This handles cases where a user wants an exercise despite not feeling negative emotions.
        if not candidates:
            print(f"[TOOL]   No techniques mapped to {emotion}, falling back to general techniques")
            fallback_hits = await prisma.technique.find_many(
                where={"isActive": True},
                take=3
            )
            candidates.extend(fallback_hits)

        if not candidates:
            print(f"[TOOL]   CRITICAL: Database has no active techniques at all!")
            return []

        #  Score & rank 
        ranked = sorted(candidates, key=lambda t: _score(t, recently_used), reverse=True)
        top3 = ranked[:3]

        def _fmt(t) -> Dict:
            return {
                "id":               t.id,
                "name":             t.name,
                "brief":            t.brief,
                "description":      t.description,
                "steps":            t.steps,
                "duration_minutes": t.durationMinutes,
                "difficulty":       t.difficulty,
                "category":         cat_id_to_name.get(t.categoryId, "Unknown"),
                "why_it_works":     t.whyItWorks,
                "avg_rating":       t.avgRating,
                "effectiveness":    t.effectiveness,
            }

        result = [_fmt(t) for t in top3]
        for r in result:
            print(f"[TOOL]    {r['name']} ({r['category']}) score={_score(ranked[result.index(r)], recently_used):.2f}")

        return result

    except Exception as e:
        print(f"[TOOL] recommend_technique ERROR: {str(e)[:120]}")
        return []


async def get_technique_by_name(name: str) -> Dict | None:
    """
    Fetch a specific technique by exact or partial name match.
    Used when the user accepts a previously-offered technique.
    """
    try:
        from ..db.client import get_prisma_client
        prisma = await get_prisma_client()

        # Try exact match first (case insensitive)
        hits = await prisma.technique.find_many(
            where={
                "isActive": True,
                "name": {"equals": name, "mode": "insensitive"}
            }
        )

        if not hits:
            # Try partial match (contains)
            hits = await prisma.technique.find_many(
                where={
                    "isActive": True,
                    "name": {"contains": name, "mode": "insensitive"}
                }
            )

        if not hits:
            print(f"[TOOL] get_technique_by_name: No match found for '{name}'")
            return None

        t = hits[0]
        cat = await prisma.techniquecategory.find_unique(where={"id": t.categoryId})
        cat_name = cat.name if cat else "Unknown"

        print(f"[TOOL] get_technique_by_name: Found '{t.name}' for query '{name}'")
        return {
            "id":               t.id,
            "name":             t.name,
            "brief":            t.brief,
            "description":      t.description,
            "steps":            t.steps,
            "duration_minutes": t.durationMinutes,
            "difficulty":       t.difficulty,
            "category":         cat_name,
            "why_it_works":     t.whyItWorks,
            "avg_rating":       t.avgRating,
            "effectiveness":    t.effectiveness,
        }

    except Exception as e:
        print(f"[TOOL] get_technique_by_name ERROR: {str(e)[:120]}")
        return None

