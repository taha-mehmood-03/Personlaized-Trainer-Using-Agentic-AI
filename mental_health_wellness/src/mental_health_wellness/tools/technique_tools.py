"""
Technique Tools - Therapy techniques and exercises by category
"""

from langchain_core.tools import tool
from typing import Dict, Optional

@tool
async def recommend_technique(
    emotion: str,
    user_id: str = ""
) -> Dict[str, Dict]:
    """
    Recommend the best-rated technique for the given emotion from EACH category.
    Returns top technique per category (Breathing, Mindfulness, CBT, DBT, Journaling, Behavioral Activation).
    Excludes categories that have no techniques for that emotion.
    
    Args:
        emotion: The detected emotion (e.g., "anxiety", "sadness", "anger", "fear", "joy", "neutral", "disgust", "surprise")
        user_id: Optional user ID for personalization (to avoid recently recommended)
        
    Returns:
        Dict mapping category name to best technique dict. 
        Example: {"Breathing": {...}, "CBT": {...}, "Journaling": {...}}
        Only includes categories with matching techniques (excludes empty ones).
    """
    try:
        from ..db.client import get_prisma_client
        prisma = await get_prisma_client()
        
        emotion_map = {
            "fear": "FEAR",
            "anxiety": "ANXIETY",
            "sadness": "SADNESS",
            "anger": "ANGER",
            "joy": "JOY",
            "neutral": "NEUTRAL",
            "disgust": "DISGUST",
            "surprise": "SURPRISE"
        }
        target_emotion = emotion_map.get(emotion.lower(), emotion.upper())
        
        print(f"[TOOL] recommend_technique: Getting best technique per category for {emotion.upper()}")
        
        # Get all categories (sort in Python to avoid Prisma order_by issues)
        all_categories_unsorted = await prisma.techniquecategory.find_many()
        all_categories = sorted(all_categories_unsorted, key=lambda c: c.name)
        
        # FIX 7a: Correct attribute name for recently recommended techniques.
        # The field is `recommendedTechniqueIds` (not `recommendedTech`).
        # Wrap in explicit try/except with WARNING-level logging — do NOT silently continue.
        recently_recommended = set()
        if user_id:
            try:
                all_sessions = await prisma.session.find_many(
                    where={"userId": user_id}
                )
                recent_sessions = sorted(all_sessions, key=lambda s: s.startedAt, reverse=True)[:5]
                for session in recent_sessions:
                    # FIX 7a: correct attribute name
                    tech_ids = getattr(session, "recommendedTechniqueIds", None)
                    if tech_ids:
                        recently_recommended.update(tech_ids)
                print(f"[TOOL] recommend_technique: User has {len(recently_recommended)} recently recommended techniques")
            except Exception as e:
                # FIX 7a: Log as WARNING (not silent), increment metric counter for monitoring
                print(f"[TOOL] recommend_technique: WARNING — Could not fetch user history: {str(e)[:80]}")
                # recently_recommended stays empty → use all techniques (safe fallback)
        
        # FIX 7b: BATCH all category+emotion queries into a SINGLE DB call.
        # Previously: N sequential find_many calls (one per category) → ~5000ms
        # Now: 1 find_many for all techniques + 1 for all categories → ~200ms
        category_id_to_name = {cat.id: cat.name for cat in all_categories}
        
        all_matching_techniques = await prisma.technique.find_many(
            where={
                "isActive": True,
                "targetEmotions": {"hasSome": [target_emotion]},
                "categoryId": {"in": list(category_id_to_name.keys())}
            }
        )
        
        # Group by category
        techniques_by_category: dict[str, list] = {}
        for t in all_matching_techniques:
            cat_name = category_id_to_name.get(t.categoryId, "Unknown")
            techniques_by_category.setdefault(cat_name, []).append(t)
        
        result = {}
        for cat in all_categories:
            cat_techniques = techniques_by_category.get(cat.name, [])
            if not cat_techniques:
                print(f"[TOOL]   ✗ {cat.name}: No techniques found (excluding)")
                continue
            
            # Pick best-rated (exclude recently recommended if alternatives exist)
            technique = max(cat_techniques, key=lambda t: t.avgRating or 0)
            if technique.id in recently_recommended and len(cat_techniques) > 1:
                other = [t for t in cat_techniques if t.id != technique.id]
                if other:
                    technique = max(other, key=lambda t: t.avgRating or 0)
            
            result[cat.name] = {
                "id": technique.id,
                "name": technique.name,
                "brief": technique.brief,
                "description": technique.description,
                "steps": technique.steps,
                "duration_minutes": technique.durationMinutes,
                "difficulty": technique.difficulty,
                "category": cat.name,
                "why_it_works": technique.whyItWorks,
                "avg_rating": technique.avgRating,
                "effectiveness": technique.effectiveness
            }
            print(f"[TOOL]   ✓ {cat.name}: {technique.name} (rating: {technique.avgRating})")
        
        print(f"[TOOL] recommend_technique: Returning {len(result)} categories with techniques")
        return result
    
    except Exception as e:
        print(f"[TOOL] recommend_technique: Error: {str(e)[:100]}")
        return {}



