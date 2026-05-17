"""
Technique Tools - Smarter selection with intensity-based routing,
unused-first scoring, and top-3 alternatives.
"""

from langchain_core.tools import tool
from typing import Dict, List
import math


_TECHNIQUE_EMBED_CACHE: dict[str, list[float]] = {}
_EMBEDDINGS_MODEL = None

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


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


def _get_embeddings_model():
    global _EMBEDDINGS_MODEL
    if _EMBEDDINGS_MODEL is None:
        from ..memory import _get_embeddings
        _EMBEDDINGS_MODEL = _get_embeddings()
    return _EMBEDDINGS_MODEL


def _semantic_bonus(query_vec: list[float] | None, technique) -> float:
    """
    Lightweight semantic rerank bonus for natural-language needs.

    DB filters remain the source of truth; embeddings only reorder safe,
    already-eligible candidates.
    """
    if not query_vec:
        return 0.0
    try:
        cache_key = getattr(technique, "id", None) or getattr(technique, "name", "")
        t_vec = _TECHNIQUE_EMBED_CACHE.get(cache_key)
        if t_vec is None:
            text = " | ".join([
                getattr(technique, "name", "") or "",
                getattr(technique, "brief", "") or "",
                getattr(technique, "description", "") or "",
                getattr(technique, "whyItWorks", "") or "",
                " ".join(getattr(technique, "steps", []) or [])[:300],
            ])
            t_vec = _get_embeddings_model().embed_query(text)
            if cache_key:
                _TECHNIQUE_EMBED_CACHE[cache_key] = t_vec
        similarity = _cosine(query_vec, t_vec)
        # Keep this as a bonus, not the whole score, so ratings/recency still matter.
        return max(0.0, similarity) * 0.35
    except Exception as e:
        print(f"[TOOL]   Semantic rerank unavailable: {str(e)[:80]}")
        return 0.0


@tool
async def recommend_technique(
    emotion: str,
    intensity: float = 0.5,
    user_id: str = "",
    phq9_score: int = 0,
    severity: str = "minimal",
    clinical_indicators: list = None,
    query: str = "",
) -> List[Dict]:
    """
    Return the top-3 ranked techniques for the given emotion and intensity.

    Selection logic:
      1. Prefer categories mapped to the intensity tier (high/moderate/low).
      2. v9.0: Filter by clinical severity range (minPhq9/maxPhq9/safeAtSeverity).
      3. v9.0: Exclude techniques with contraindicated flags matching user indicators.
      4. Score each candidate: unused+rated > unused+unrated > used (penalised).
      5. Return top 3 sorted by score (desc).  Falls back to all categories if
         preferred ones yield < 3 results.

    Args:
        emotion:              Detected emotion string.
        intensity:            Fused emotion intensity 0.01.0.
        user_id:              For personalization (avoid recently recommended).
        phq9_score:           Estimated PHQ-9 score (0-27) from clinical check.
        severity:             Clinical severity level (minimal/mild/moderate/moderately_severe/severe).
        clinical_indicators:  List of active clinical indicators (e.g. ["anhedonia", "suicidal_ideation"]).

    Returns:
        List of up to 3 technique dicts, best first.  Empty list on error.
    """
    clinical_indicators = clinical_indicators or []

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

        # v9.0: Clinical severity gating info
        _sev_label = severity.upper() if severity else "MINIMAL"
        print(f"[TOOL] recommend_technique: emotion={emotion.upper()} "
              f"intensity={intensity:.0%} tier={tier} preferred={preferred_cats} "
              f"| clinical: severity={_sev_label} phq9={phq9_score} indicators={clinical_indicators}")

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

        #  DB fetch — build WHERE clause with clinical severity gating 
        preferred_ids = [cat_name_to_id[n] for n in preferred_cats if n in cat_name_to_id]

        # v9.0: Base clinical filter (applied when clinical data is available)
        clinical_where = {}
        if phq9_score > 0 or severity not in ("minimal", ""):
            clinical_where = {
                "minPhq9": {"lte": phq9_score},      # technique's min <= user's score
                "maxPhq9": {"gte": phq9_score},       # technique's max >= user's score
                "safeAtSeverity": {"hasSome": [_sev_label]},
            }
            print(f"[TOOL]   Clinical filter active: minPhq9<={phq9_score} AND maxPhq9>={phq9_score} AND safeAt={_sev_label}")

        candidates = []
        if preferred_ids:
            preferred_hits = await prisma.technique.find_many(
                where={
                    "isActive": True,
                    "targetEmotions": {"hasSome": [target_emotion]},
                    "categoryId": {"in": preferred_ids},
                    **clinical_where,
                }
            )
            candidates = preferred_hits

        # Fall back to all categories if we don't have enough preferred results
        if len(candidates) < 3:
            all_hits = await prisma.technique.find_many(
                where={
                    "isActive": True,
                    "targetEmotions": {"hasSome": [target_emotion]},
                    **clinical_where,
                }
            )
            # De-duplicate: keep preferred hits + non-preferred ones
            seen_ids = {t.id for t in candidates}
            for t in all_hits:
                if t.id not in seen_ids:
                    candidates.append(t)

        # v9.0: Post-filter — exclude techniques with contraindicated flags
        if clinical_indicators and candidates:
            indicator_set = set(clinical_indicators)
            pre_filter_count = len(candidates)
            candidates = [
                t for t in candidates
                if not (set(getattr(t, 'contraindicatedFlags', []) or []) & indicator_set)
            ]
            filtered_count = pre_filter_count - len(candidates)
            if filtered_count > 0:
                print(f"[TOOL]   Contraindication filter removed {filtered_count} techniques "
                      f"(indicators: {clinical_indicators})")

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

        query_vec = None
        if query and len(query.strip()) >= 8 and len(candidates) <= 25:
            try:
                query_vec = _get_embeddings_model().embed_query(query)
            except Exception as e:
                print(f"[TOOL]   Query embedding unavailable: {str(e)[:80]}")
                query_vec = None
        elif query and len(candidates) > 25:
            print(f"[TOOL]   Semantic rerank skipped ({len(candidates)} candidates)")

        #  Score & rank
        ranked = sorted(
            candidates,
            key=lambda t: _score(t, recently_used) + _semantic_bonus(query_vec, t),
            reverse=True,
        )
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

