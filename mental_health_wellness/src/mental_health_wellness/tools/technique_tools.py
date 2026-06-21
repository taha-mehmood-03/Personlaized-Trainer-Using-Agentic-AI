"""
Technique Tools - Smarter selection with all-category ranking,
unused-first scoring, and top-3 alternatives.
"""

from langchain_core.tools import tool
from typing import Dict, List
import asyncio
import math
import re
from ..techniques.emotion_metadata import NO_TECHNIQUE_BY_DEFAULT_SUB_EMOTIONS


_TECHNIQUE_EMBED_CACHE: dict[str, list[float]] = {}
_PGVECTOR_TECHNIQUE_INDEXED: set[str] = set()
_EMBEDDINGS_MODEL = None

# Category -> technique family for diversity reranking.
# Prevents all top-3 from being the same clinical approach.
_TECHNIQUE_FAMILY = {
    "Breathing":             "body_regulation",
    "DBT":                   "dbt_distress",
    "Mindfulness":           "mindfulness_defusion",
    "CBT":                   "cognitive_reframing",
    "Journaling":            "journaling_reflection",
    "Behavioral Activation": "behavioral_activation",
}

_SLEEP_EXAM_CONTEXTS = {
    "sleep_difficulty", "sleep_disruption", "bedtime_rumination", "nighttime_worry",
    "exam_week", "exam_pressure", "academic_anxiety", "bedtime_racing_thoughts",
}
_CATASTROPHIC_CONTEXTS = {
    "academic_risk", "specific_exam_failure_belief", "catastrophic_exam_thought",
    "future_threat", "fear_of_failure",
}
_CATASTROPHIC_SUBS = {
    "catastrophizing", "catastrophising", "fortune_telling", "fear_of_failure",
    "academic_pressure", "future_threat",
}
_ENVIRONMENT_CONTEXTS = {
    "sleep_environment", "phone_distraction", "study_space_distraction",
    "environmental_trigger", "physical_setup",
}
_ENVIRONMENT_QUERY_TERMS = (
    "phone", "room", "noise", "noisy", "distract", "distraction",
    "study on my bed", "studying on my bed", "study space", "desk",
)
_RUMINATION_TECHNIQUE_BOOSTS = {
    "worry time": 4.0,
    "brain dump before sleep": 4.1,
    "constructive worry worksheet": 3.6,
    "sleep wind-down routine": 3.1,
    "leaves on a stream": 2.9,
    "thought defusion": 3.2,
    "stimulus control for sleep": 2.4,
    "stream of consciousness": 2.9,
    "mindfulness of thoughts": 3.2,
    "thought record": 2.2,
    "cognitive restructuring": 2.0,
}
_CATASTROPHIC_TECHNIQUE_BOOSTS = {
    "thought record": 4.3,
    "decatastrophizing questions": 4.1,
    "cognitive restructuring": 3.8,
    "coping card for catastrophic thoughts": 3.6,
    "thought defusion": 2.4,
    "constructive worry worksheet": 2.6,
    "worry time": 2.8,
    "exam coping plan": 2.5,
    "problem-solving worksheet": 2.4,
    "problem solving worksheet": 2.4,
    "mindfulness of thoughts": 1.6,
    "leaves on a stream": 1.5,
}
_SOCIAL_HUMILIATION_CONTEXTS = {
    "shame", "embarrassment", "rejection", "humiliation", "inadequacy",
    "self_criticism", "interpersonal_conflict", "authority_conflict",
    "teacher_conflict", "school_conflict", "social_humiliation",
}
_SOCIAL_HUMILIATION_QUERY_TERMS = (
    "insulted", "humiliated", "embarrassed", "shamed", "mocked",
    "laughed at", "rejected", "principal", "teacher", "classmate",
    "bully", "bullied", "scolded", "publicly", "in front of",
)
_SOCIAL_HUMILIATION_TECHNIQUE_BOOSTS = {
    "self-compassion letter": 4.3,
    "validation of self": 4.0,
    "thought record": 3.7,
    "cognitive restructuring": 3.5,
    "metta phrases for self": 2.6,
    "wise mind": 2.2,
    "self-soothing with five senses": 2.0,
}


def _as_list(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).lower().strip() for item in value if str(item).strip()]
    return [str(value).lower().strip()]


def _technique_attr_list(technique, name: str) -> list[str]:
    return _as_list(getattr(technique, name, []) or [])


def _contextual_selection_adjustment(
    technique,
    primary_sub_emotion: str = "",
    secondary_sub_emotions: list[str] | None = None,
    detected_symptoms: list[str] | None = None,
    detected_behaviors: list[str] | None = None,
    detected_contexts: list[str] | None = None,
    distortion_type: str = "",
    query: str = "",
) -> float:
    """
    Deterministic clinical rerank layer on top of DB metadata and embeddings.

    The table fields and semantic scores remain important, but this prevents a
    broad emotion like anxiety from outranking the actual active issue
    formulation (exam rumination at bedtime, catastrophic failure belief, etc.).
    """
    name = (getattr(technique, "name", "") or "").lower().strip()
    query_l = (query or "").lower()
    primary = (primary_sub_emotion or "").lower().strip()
    secondary = set(_as_list(secondary_sub_emotions))
    symptoms = set(_as_list(detected_symptoms))
    behaviors = set(_as_list(detected_behaviors))
    contexts = set(_as_list(detected_contexts))
    distortion = (distortion_type or "").lower().strip()
    tags = {primary, *secondary, *symptoms, *behaviors, *contexts} - {""}

    has_sleep_exam_rumination = bool(tags & _SLEEP_EXAM_CONTEXTS) or (
        any(term in query_l for term in ("exam", "test", "quiz", "final"))
        and any(term in query_l for term in ("sleep", "bed", "night"))
        and any(term in query_l for term in ("thought", "mind", "worry", "ruminat", "racing"))
    )
    has_catastrophic_belief = (
        distortion in {"catastrophizing", "catastrophising", "fortune_telling"}
        or bool(tags & _CATASTROPHIC_CONTEXTS)
        or bool(tags & _CATASTROPHIC_SUBS)
        or any(term in query_l for term in ("might fail", "will fail", "drop out", "dropout"))
    )
    has_environment_problem = bool(tags & _ENVIRONMENT_CONTEXTS) or any(term in query_l for term in _ENVIRONMENT_QUERY_TERMS)
    has_social_humiliation = bool(tags & _SOCIAL_HUMILIATION_CONTEXTS) or any(
        term in query_l for term in _SOCIAL_HUMILIATION_QUERY_TERMS
    )

    adjustment = 0.0
    if has_sleep_exam_rumination:
        adjustment += _RUMINATION_TECHNIQUE_BOOSTS.get(name, 0.0)
        if name == "environmental design" and not has_environment_problem:
            adjustment -= 5.0
        if name == "gratitude journaling":
            adjustment -= 5.0

    if has_catastrophic_belief:
        adjustment += _CATASTROPHIC_TECHNIQUE_BOOSTS.get(name, 0.0)
        if name == "gratitude journaling":
            adjustment -= 6.0
        if name == "environmental design" and not has_environment_problem:
            adjustment -= 4.5

    if has_environment_problem and name == "environmental design":
        adjustment += 3.8

    if has_social_humiliation:
        adjustment += _SOCIAL_HUMILIATION_TECHNIQUE_BOOSTS.get(name, 0.0)
        if name == "environmental design" and not has_environment_problem:
            adjustment -= 4.5
        if name == "activity-mood monitoring":
            adjustment -= 1.5

    return adjustment


def _emotion_fit_bonus(
    technique,
    primary_sub_emotion: str = "",
    secondary_sub_emotions: list[str] | None = None,
    detected_symptoms: list[str] | None = None,
    detected_behaviors: list[str] | None = None,
    detected_contexts: list[str] | None = None,
    intensity: float = 0.5,
) -> float:
    """Score how well a technique fits the nuanced emotional state.

    ``intensity`` is retained for API compatibility, but it does not affect
    technique ranking. Semantic/contextual fit should be free to win.
    """
    if isinstance(detected_symptoms, (int, float)) and detected_behaviors is None:
        detected_symptoms = None
    primary = (primary_sub_emotion or "").lower().strip()
    secondary = set(_as_list(secondary_sub_emotions))
    symptoms = set(_as_list(detected_symptoms))
    behaviors = set(_as_list(detected_behaviors))
    contexts = set(_as_list(detected_contexts))
    targets = set(_technique_attr_list(technique, "targetSubEmotions"))
    target_symptoms = set(_technique_attr_list(technique, "targetSymptoms"))
    target_behaviors = set(_technique_attr_list(technique, "targetBehaviors"))
    avoid = set(_technique_attr_list(technique, "avoidSubEmotions"))
    avoid_symptoms = set(_technique_attr_list(technique, "avoidSymptoms"))
    avoid_behaviors = set(_technique_attr_list(technique, "avoidBehaviors"))

    score = 0.0
    if primary and primary in targets:
        score += 3.0
    if secondary and targets:
        score += len(secondary & targets) * 1.2
    if symptoms and target_symptoms:
        score += len(symptoms & target_symptoms) * 1.4
    if behaviors and target_behaviors:
        score += len(behaviors & target_behaviors) * 1.4
    if primary and primary in avoid:
        score -= 4.0
    if secondary and avoid:
        score -= len(secondary & avoid) * 1.0
    if symptoms and avoid_symptoms:
        score -= len(symptoms & avoid_symptoms) * 4.0
    if behaviors and avoid_behaviors:
        score -= len(behaviors & avoid_behaviors) * 3.0

    return score


def _is_subemotion_compatible(
    technique,
    primary_sub_emotion: str = "",
    secondary_sub_emotions: list[str] | None = None,
    detected_symptoms: list[str] | None = None,
    detected_behaviors: list[str] | None = None,
    intensity: float = 0.5,
) -> bool:
    if isinstance(detected_symptoms, (int, float)) and detected_behaviors is None:
        detected_symptoms = None
    primary = (primary_sub_emotion or "").lower().strip()
    secondary = set(_as_list(secondary_sub_emotions))
    relevant_subs = {primary, *secondary} - {""}
    avoid = set(_technique_attr_list(technique, "avoidSubEmotions"))
    if relevant_subs and avoid and relevant_subs & avoid:
        return False
    symptoms = set(_as_list(detected_symptoms))
    behaviors = set(_as_list(detected_behaviors))
    avoid_symptoms = set(_technique_attr_list(technique, "avoidSymptoms"))
    avoid_behaviors = set(_technique_attr_list(technique, "avoidBehaviors"))
    if symptoms and avoid_symptoms and symptoms & avoid_symptoms:
        return False
    if behaviors and avoid_behaviors and behaviors & avoid_behaviors:
        return False

    # Intensity is intentionally ignored here; selection compatibility is based
    # on explicit avoid tags, symptoms, and behaviors.
    return True


def _score(
    technique,
    recently_used: set,
    personal_ratings: dict | None = None,
    personal_outcomes: dict | None = None,
    preferred_category_ids: set | None = None,
) -> float:
    """
    Priority scoring:
      - Global avg/effectiveness is the fallback signal.
      - Current user's ratings/completion/feedback dominate global popularity.
      - Current user's negative outcomes strongly penalize the technique.
      - Recently used techniques are penalized to avoid repetition.
      - User preferred categories receive a small boost.
    """
    personal_ratings = personal_ratings or {}
    personal_outcomes = personal_outcomes or {}
    preferred_category_ids = preferred_category_ids or set()

    rating = float(technique.avgRating or 0.0)
    effectiveness = float(getattr(technique, "effectiveness", 0.5) or 0.5)
    # Global fallback is intentionally weak; personal history can override it.
    score = rating if rating > 0 else 2.5 + (effectiveness - 0.5)

    rating_info = personal_ratings.get(technique.id)
    if rating_info:
        avg_user_rating = rating_info.get("avg_rating", 3.0)
        completed_rate = rating_info.get("completed_rate", 0.0)
        negative_feedback = rating_info.get("negative_feedback", False)
        positive_feedback = rating_info.get("positive_feedback", False)

        if avg_user_rating <= 2:
            score -= 4.0
        elif avg_user_rating < 3:
            score -= 1.5
        elif avg_user_rating >= 4:
            score += 2.0
        elif avg_user_rating > 3:
            score += 0.8

        score += completed_rate * 0.8
        if negative_feedback:
            score -= 1.5
        if positive_feedback:
            score += 0.7

    outcome_info = personal_outcomes.get(technique.id)
    if outcome_info:
        avg_effectiveness = outcome_info.get("avg_effectiveness", 0.0)
        score += max(-1.0, min(1.0, avg_effectiveness)) * 2.0

    if technique.categoryId in preferred_category_ids:
        score += 1.0

    used = technique.id in recently_used
    if used:
        score -= 1.2

    # Issue 4 fix: Hard ceiling for personally-disliked techniques.
    # Without this, contextual boosts (+4.3 for catastrophic context) can
    # override a user's explicit 1-star rating (−4.0 −1.5 = −5.5), netting
    # a positive score. The hard ceiling ensures explicit rejection is final.
    if _is_personally_disliked(technique.id, personal_ratings, personal_outcomes):
        score = min(score, -2.0)

    return score


def _is_personally_disliked(technique_id: str, personal_ratings: dict, personal_outcomes: dict) -> bool:
    rating_info = personal_ratings.get(technique_id)
    if rating_info and (rating_info.get("avg_rating", 3.0) <= 2 or rating_info.get("negative_feedback", False)):
        return True

    outcome_info = personal_outcomes.get(technique_id)
    if outcome_info and outcome_info.get("avg_effectiveness", 0.0) < -0.25:
        return True

    return False


def _rating_maps(ratings) -> dict:
    by_technique: dict[str, dict] = {}
    negative_words = {
        "didn't help", "didnt help", "not helpful", "bad", "worse", "hate",
        "dislike", "too hard", "not for me", "uncomfortable", "stressful",
    }
    positive_words = {
        "helped", "useful", "good", "great", "calming", "better", "liked",
        "love", "effective", "worked",
    }

    for item in ratings or []:
        technique_id = getattr(item, "techniqueId", "")
        if not technique_id:
            continue
        bucket = by_technique.setdefault(
            technique_id,
            {"ratings": [], "completed": 0, "count": 0, "negative_feedback": False, "positive_feedback": False},
        )
        rating = int(getattr(item, "rating", 3) or 3)
        feedback = (getattr(item, "feedback", "") or "").lower()
        bucket["ratings"].append(rating)
        bucket["count"] += 1
        if getattr(item, "completed", False):
            bucket["completed"] += 1
        if rating <= 2 or any(word in feedback for word in negative_words):
            bucket["negative_feedback"] = True
        if rating >= 4 or any(word in feedback for word in positive_words):
            bucket["positive_feedback"] = True

    result = {}
    for technique_id, bucket in by_technique.items():
        count = bucket["count"] or 1
        result[technique_id] = {
            "avg_rating": sum(bucket["ratings"]) / len(bucket["ratings"]),
            "completed_rate": bucket["completed"] / count,
            "negative_feedback": bucket["negative_feedback"],
            "positive_feedback": bucket["positive_feedback"],
        }
    return result


def _outcome_maps(outcomes) -> dict:
    by_technique: dict[str, list[float]] = {}
    for item in outcomes or []:
        technique_id = getattr(item, "techniqueId", "")
        if not technique_id:
            continue
        effectiveness = getattr(item, "effectiveness", None)
        if effectiveness is None:
            continue
        by_technique.setdefault(technique_id, []).append(float(effectiveness))

    return {
        technique_id: {"avg_effectiveness": sum(values) / len(values)}
        for technique_id, values in by_technique.items()
        if values
    }


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


def _semantic_tier_bonus(similarity: float) -> float:
    """Convert raw cosine similarity to a tier-based semantic bonus score.

    Old flat cap (+0.35 max) was too small to break ties against the +3.0/+4.3
    clinical signals, making semantic rerank nearly irrelevant in practice.
    Tier-based scoring gives a meaningful +1.5 boost to genuinely close matches
    while still penalising near-zero similarity (< 0.25) very mildly.
    """
    if similarity >= 0.75:
        return 1.5
    elif similarity >= 0.65:
        return 0.8
    elif similarity >= 0.50:
        return 0.3
    elif similarity < 0.25:
        return -0.5  # near-zero: mild penalty, clinical signals still win
    return 0.0


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
        return _semantic_tier_bonus(max(0.0, similarity))
    except Exception as e:
        print(f"[TOOL]   Semantic rerank unavailable: {str(e)[:80]}")
        return 0.0


def _keyword_semantic_score(query: str, technique) -> float:
    """
    Keyword overlap fallback for when both pgvector and embedding models are unavailable.

    Without this, all candidates get semantic_score=0.00, leaving technique selection
    to tiny numeric gaps in the base score - making it feel arbitrary and inconsistent.

    Computes a simple word-overlap fraction between the query and the technique's
    searchable text fields, scaled to the same 0.0-0.35 range as _semantic_bonus.
    """
    if not query or not query.strip():
        return 0.0
    try:
        query_words = set(re.findall(r'\b[a-z]{3,}\b', query.lower()))
        _STOP = {
            "the", "and", "for", "that", "this", "with", "are", "not", "you",
            "have", "been", "was", "but", "they", "from", "can", "what",
            "when", "just", "about", "your", "its", "also", "all", "how",
        }
        query_words -= _STOP
        if not query_words:
            return 0.0
        tech_text = " ".join(filter(None, [
            getattr(technique, "name", "") or "",
            getattr(technique, "brief", "") or "",
            getattr(technique, "description", "") or "",
            getattr(technique, "whyItWorks", "") or "",
            " ".join((getattr(technique, "targetSubEmotions", []) or [])[:8]),
        ])).lower()
        tech_words = set(re.findall(r'\b[a-z]{3,}\b', tech_text)) - _STOP
        if not tech_words:
            return 0.0
        overlap = query_words & tech_words
        score = len(overlap) / max(len(query_words), 1)
        return min(score * 0.35, 0.35)
    except Exception:
        return 0.0



@tool
async def recommend_technique(
    emotion: str,
    intensity: float = 0.5,
    user_id: str = "",
    # PHQ-9 clinical gating removed — scores were estimated defaults (phq9=0,
    # severity=minimal) and created false filtering. Safety is handled downstream
    # via contraindicatedFlags post-filter.
    clinical_indicators: list = None,
    query: str = "",
    primary_sub_emotion: str = "",
    secondary_sub_emotions: list = None,
    detected_symptoms: list = None,
    detected_behaviors: list = None,
    detected_contexts: list = None,
    distortion_type: str = "",
    allow_general_fallback: bool = False,
    limit: int = 3,
) -> List[Dict]:
    """
    Return ranked technique candidates for the given emotion and context.

    Selection logic:
      1. Fetch all active techniques for the target emotion across categories.
      2. Exclude techniques with contraindicated flags matching user indicators.
      3. Score each candidate by user history, emotion fit, context, and semantics.
      4. Return the requested number of candidates sorted by score (desc).

    Args:
        emotion:              Detected emotion string.
        intensity:            Fused emotion intensity 0.0–1.0.
        user_id:              For personalization (avoid recently recommended).
        clinical_indicators:  List of active clinical indicators (e.g. ["anhedonia", "suicidal_ideation"]).
        primary_sub_emotion:  Nuanced feeling label used for personalization-aware matching.
        secondary_sub_emotions: Additional nuanced feeling labels.
        detected_symptoms:    Body/cognitive signals for safety/ranking.
        detected_behaviors:   Action patterns for matching.
        detected_contexts:    Situational tags for matching.
        distortion_type:      Cognitive distortion hint from context/LLM analysis.

        limit:                Number of ranked candidates to return.

    Returns:
        List of up to 3 technique dicts, best first.  Empty list on error.
    """
    clinical_indicators = clinical_indicators or []
    primary_sub_emotion = (primary_sub_emotion or "").lower().strip()
    secondary_sub_emotions = _as_list(secondary_sub_emotions)
    detected_symptoms = _as_list(detected_symptoms)
    detected_behaviors = _as_list(detected_behaviors)
    detected_contexts = _as_list(detected_contexts)
    distortion_type = (distortion_type or "").lower().strip()
    try:
        result_limit = max(1, min(int(limit or 3), 10))
    except (TypeError, ValueError):
        result_limit = 3

    try:
        from ..db.client import get_prisma_client
        prisma = await get_prisma_client()

        emotion_map = {
            "fear": "FEAR", "anxiety": "ANXIETY", "sadness": "SADNESS",
            "anger": "ANGER", "joy": "JOY", "neutral": "NEUTRAL",
            "disgust": "DISGUST", "surprise": "SURPRISE",
        }
        target_emotion = emotion_map.get(emotion.lower(), emotion.upper())

        print(f"[TOOL] recommend_technique: emotion={emotion.upper()} "
              f"intensity={intensity:.0%} all-category ranking "
              f"sub={primary_sub_emotion or 'n/a'} "
              f"symptoms={detected_symptoms or []} behaviors={detected_behaviors or []} "
              f"contexts={detected_contexts or []} distortion={distortion_type or 'none'} "
              f"| indicators={clinical_indicators}")

        if (
            primary_sub_emotion in NO_TECHNIQUE_BY_DEFAULT_SUB_EMOTIONS
            and target_emotion in {"NEUTRAL", "JOY", "SURPRISE"}
            and not allow_general_fallback
        ):
            print(
                f"[TOOL]   Sub-emotion '{primary_sub_emotion}' is conversation-first; "
                "returning no technique without explicit request"
            )
            return []

        #  Lookup tables 
        all_cats = await prisma.techniquecategory.find_many()
        cat_id_to_name = {c.id: c.name for c in all_cats}
        cat_name_to_id = {c.name: c.id for c in all_cats}

        preferred_names: set[str] = set()
        preferred_category_ids: set[str] = set()
        if user_id:
            try:
                pref = await prisma.userpreference.find_unique(where={"userId": user_id})
                preferred_names = set(getattr(pref, "preferredCategories", []) or []) if pref else set()
                preferred_category_ids = {
                    cat_name_to_id[name] for name in preferred_names if name in cat_name_to_id
                }
                if preferred_category_ids:
                    print(f"[TOOL]   Preferred categories included in pool: {sorted(preferred_names)}")
            except Exception as e:
                print(f"[TOOL]   WARNING  preference fetch failed: {str(e)[:60]}")

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

        # Fetch all active techniques for the target emotion across categories.
        # Intensity must not choose or rank the technique pool.
        candidates = await prisma.technique.find_many(
            where={
                "isActive": True,
                "targetEmotions": {"hasSome": [target_emotion]},
            },
            take=20,
        )
        print(f"[TOOL]   All-category fetch: {len(candidates)} candidates for {target_emotion}")

        # Stage 3b: sub-emotion / distortion expansion fallback.
        if len(candidates) < 3 and (primary_sub_emotion or secondary_sub_emotions):
            sub_targets = [
                s for s in [primary_sub_emotion] + list(secondary_sub_emotions or [])
                if s
            ][:4]
            if sub_targets:
                sub_hits = await prisma.technique.find_many(
                    where={
                        "isActive": True,
                        "targetSubEmotions": {"hasSome": sub_targets},
                    }
                )
                seen_ids = {t.id for t in candidates}
                added_sub = [t for t in sub_hits if t.id not in seen_ids]
                candidates.extend(added_sub)
                if added_sub:
                    print(
                        f"[TOOL]   Stage 3b sub-emotion expansion: +{len(added_sub)} candidates "
                        f"(sub_targets={sub_targets[:2]})"
                    )

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

        if candidates:
            pre_sub_filter_count = len(candidates)
            compatible = [
                t for t in candidates
                if _is_subemotion_compatible(
                    t,
                    primary_sub_emotion=primary_sub_emotion,
                    secondary_sub_emotions=secondary_sub_emotions,
                    detected_symptoms=detected_symptoms,
                    detected_behaviors=detected_behaviors,
                )
            ]
            if compatible:
                removed = pre_sub_filter_count - len(compatible)
                if removed:
                    print(
                        f"[TOOL]   Sub-emotion/safety filter removed {removed} technique(s)"
                    )
                candidates = compatible
            else:
                print(
                    "[TOOL]   No exact sub-emotion/safety-compatible candidates; "
                    "falling back to core-emotion candidates with scoring penalty"
                )

        personal_ratings = {}
        personal_outcomes = {}
        if user_id and candidates:
            candidate_ids = [t.id for t in candidates]
            try:
                user_ratings = await prisma.usertechniquerating.find_many(
                    where={
                        "userId": user_id,
                        "techniqueId": {"in": candidate_ids},
                    },
                    order={"usedAt": "desc"},
                    take=50,
                )
                personal_ratings = _rating_maps(user_ratings)
                if user_ratings:
                    disliked = sum(
                        1 for tech_id in candidate_ids
                        if _is_personally_disliked(tech_id, personal_ratings, {})
                    )
                    print(f"[TOOL]   Personal ratings loaded: {len(user_ratings)} records, disliked={disliked}")
            except Exception as e:
                print(f"[TOOL]   WARNING  personal ratings fetch failed: {str(e)[:60]}")

            try:
                outcomes = await prisma.techniqueoutcome.find_many(
                    where={
                        "techniqueId": {"in": candidate_ids},
                        "session": {"userId": user_id},
                    },
                    order={"createdAt": "desc"},
                    take=50,
                )
                personal_outcomes = _outcome_maps(outcomes)
                if outcomes:
                    print(f"[TOOL]   Personal outcomes loaded: {len(outcomes)} records")
            except Exception as e:
                print(f"[TOOL]   WARNING  personal outcomes fetch failed: {str(e)[:60]}")

            non_disliked = [
                t for t in candidates
                if not _is_personally_disliked(t.id, personal_ratings, personal_outcomes)
            ]
            if len(non_disliked) >= 3:
                removed = len(candidates) - len(non_disliked)
                if removed:
                    print(f"[TOOL]   Personalization removed {removed} disliked/negative-outcome technique(s)")
                candidates = non_disliked

        # Final fallback: only use unrelated general techniques when an upstream
        # node has an explicit action signal. Low-signal neutral follow-ups
        # should never invent exercise readiness just because context is complete.
        if not candidates:
            if target_emotion in {"NEUTRAL", "JOY"} and not allow_general_fallback:
                print(
                    f"[TOOL]   No techniques mapped to {emotion}; "
                    "general fallback blocked without explicit action signal"
                )
                return []
            print(f"[TOOL]   No techniques mapped to {emotion}, falling back to general techniques")
            fallback_hits = await prisma.technique.find_many(
                where={"isActive": True},
                take=3
            )
            candidates.extend(fallback_hits)

        if not candidates:
            print(f"[TOOL]   CRITICAL: Database has no active techniques at all!")
            return []

        pgvector_scores: dict[str, float] = {}
        if query and len(query.strip()) >= 8 and candidates:
            try:
                from ..memory import store_technique_embedding
                from ..memory.pgvector_store import rank_source_ids

                unindexed = [t for t in candidates if t.id not in _PGVECTOR_TECHNIQUE_INDEXED]
                if unindexed:
                    index_results = await asyncio.gather(
                        *[store_technique_embedding(t) for t in unindexed],
                        return_exceptions=True,
                    )
                    for t, ok in zip(unindexed, index_results):
                        if ok is True:
                            _PGVECTOR_TECHNIQUE_INDEXED.add(t.id)
                pgvector_scores = await rank_source_ids(
                    query=query,
                    source_type="technique",
                    source_ids=[t.id for t in candidates],
                    limit=min(len(candidates), 25),
                )
                if pgvector_scores:
                    print(f"[TOOL]   pgvector technique rerank active: {len(pgvector_scores)} matches")
            except Exception as e:
                print(f"[TOOL]   pgvector technique rerank unavailable: {str(e)[:80]}")

        query_vec = None
        if not pgvector_scores and query and len(query.strip()) >= 8 and len(candidates) <= 25:
            try:
                query_vec = _get_embeddings_model().embed_query(query)
            except Exception as e:
                print(f"[TOOL]   Query embedding unavailable: {str(e)[:80]}")
                query_vec = None
        elif not pgvector_scores and query and len(candidates) > 25:
            print(f"[TOOL]   Semantic rerank skipped ({len(candidates)} candidates)")

        # Compute semantic rerank scores candidate-by-candidate.
        # Priority: pgvector → local embedding → keyword overlap fallback.
        # Keyword fallback prevents a flat 0.00 semantic score when both vector
        # stores are unavailable, which otherwise creates tiny score gaps that
        # make technique selection feel arbitrary.
        semantic_scores = {}
        _semantic_tier_used = "none"  # tracks which tier fired — for infrastructure monitoring
        for t in candidates:
            if pgvector_scores and t.id in pgvector_scores:
                semantic_scores[t.id] = _semantic_tier_bonus(max(0.0, float(pgvector_scores[t.id])))
                _semantic_tier_used = "pgvector"
            elif query_vec is not None:
                semantic_scores[t.id] = _semantic_bonus(query_vec, t)
                _semantic_tier_used = "local_embedding"
            else:
                semantic_scores[t.id] = _keyword_semantic_score(query, t)
                _semantic_tier_used = "keyword_fallback"
        # ⚠ Regular keyword_fallback hits in production = pgvector is down; fix at source.
        print(f"[TOOL]   Semantic rerank tier: {_semantic_tier_used} ({len(semantic_scores)} candidates scored)")

        contextual_adjustments = {
            t.id: _contextual_selection_adjustment(
                t,
                primary_sub_emotion=primary_sub_emotion,
                secondary_sub_emotions=secondary_sub_emotions,
                detected_symptoms=detected_symptoms,
                detected_behaviors=detected_behaviors,
                detected_contexts=detected_contexts,
                distortion_type=distortion_type,
                query=query,
            )
            for t in candidates
        }

        # Issue 7 fix: Cold-start amplification for new users.
        # When personal_ratings is empty, all candidates cluster at ~2.5 base score.
        # Amplify emotion fit and contextual signals so clinical matching dominates
        # over near-zero score noise from global ratings.
        _fit_weight = 1.0 if personal_ratings else 1.5

        # Helper to compute total score with sort-time dislike ceiling.
        # The hard ceiling must be applied AFTER all signals (contextual, semantic,
        # emotion fit) are combined, otherwise a +4.3 contextual boost can override
        # a user's explicit 1-star rating.
        def _total_score(t):
            base = _score(
                t,
                recently_used,
                personal_ratings,
                personal_outcomes,
                preferred_category_ids,
            )
            fit = _fit_weight * _emotion_fit_bonus(
                t,
                primary_sub_emotion=primary_sub_emotion,
                secondary_sub_emotions=secondary_sub_emotions,
                detected_symptoms=detected_symptoms,
                detected_behaviors=detected_behaviors,
                detected_contexts=detected_contexts,
            )
            sem = semantic_scores.get(t.id, 0.0)
            ctx = _fit_weight * contextual_adjustments.get(t.id, 0.0)

            total = base + fit + sem + ctx
            # Sort-time hard ceiling: if the user has explicitly disliked this
            # technique, cap the TOTAL score so no combination of boosts can
            # resurrect it above the penalty floor.
            if _is_personally_disliked(t.id, personal_ratings, personal_outcomes):
                total = min(total, -2.0)
            return total

        #  Score & rank
        ranked = sorted(candidates, key=_total_score, reverse=True)
        selected = list(ranked[:result_limit])

        # Diversity rerank: avoid returning only one technique family when possible.
        # Only fires when there are spare candidates to pull from.
        if len(ranked) > len(selected) and len(selected) >= 3:
            families_top3 = [
                _TECHNIQUE_FAMILY.get(cat_id_to_name.get(t.categoryId, ""), "other")
                for t in selected[:3]
            ]
            if len(set(families_top3)) == 1:  # all identical family
                dominant = families_top3[0]
                for candidate in ranked[3:]:
                    cand_family = _TECHNIQUE_FAMILY.get(
                        cat_id_to_name.get(candidate.categoryId, ""), "other"
                    )
                    if cand_family != dominant:
                        print(
                            f"[TOOL]   Diversity rerank: swapped '{selected[-1].name}' ({dominant}) "
                            f"-> '{candidate.name}' ({cand_family})"
                        )
                        selected[-1] = candidate
                        break

        def _compute_score_reasons(t) -> list[str]:
            """Return human-readable signals that elevated this technique."""
            reasons: list[str] = []
            ctx = contextual_adjustments.get(t.id, 0.0)
            if ctx >= 2.0:
                t_name = (getattr(t, "name", "") or "").lower()
                if t_name in _SOCIAL_HUMILIATION_TECHNIQUE_BOOSTS:
                    reasons.append(f"social_humiliation_context (+{ctx:.1f})")
                elif t_name in _CATASTROPHIC_TECHNIQUE_BOOSTS:
                    reasons.append(f"catastrophic_belief_context (+{ctx:.1f})")
                elif t_name in _RUMINATION_TECHNIQUE_BOOSTS:
                    reasons.append(f"rumination_context (+{ctx:.1f})")
                else:
                    reasons.append(f"contextual_boost (+{ctx:.1f})")
            primary_lc = (primary_sub_emotion or "").lower().strip()
            targets = set(_technique_attr_list(t, "targetSubEmotions"))
            if primary_lc and primary_lc in targets:
                reasons.append(f"sub_emotion_match: {primary_lc} (+3.0)")
            sem = semantic_scores.get(t.id, 0.0)
            if sem >= 0.8:
                reasons.append(f"semantic: high (+{sem:.1f})")
            elif sem >= 0.3:
                reasons.append(f"semantic: moderate (+{sem:.1f})")
            r_info = personal_ratings.get(t.id)
            if r_info and r_info.get("avg_rating", 3.0) >= 4:
                reasons.append(f"user_rated: {r_info['avg_rating']:.1f}/5")
            return reasons

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
                "target_sub_emotions": _technique_attr_list(t, "targetSubEmotions"),
                "target_symptoms": _technique_attr_list(t, "targetSymptoms"),
                "target_behaviors": _technique_attr_list(t, "targetBehaviors"),
                "avoid_sub_emotions": _technique_attr_list(t, "avoidSubEmotions"),
                "avoid_symptoms": _technique_attr_list(t, "avoidSymptoms"),
                "avoid_behaviors": _technique_attr_list(t, "avoidBehaviors"),
                "min_intensity":    float(getattr(t, "minIntensity", 0.0) or 0.0),
                "max_intensity":    float(getattr(t, "maxIntensity", 1.0) or 1.0),
                "pacing_tier":      getattr(t, "pacingTier", "normal") or "normal",
                "delivery_mode":    getattr(t, "deliveryMode", "exercise") or "exercise",
                "best_for_contexts": _technique_attr_list(t, "bestForContexts"),
                "score_reasons":    _compute_score_reasons(t),
            }

        result = [_fmt(t) for t in selected]
        for t, r in zip(selected, result):
            personal_note = ""
            if t.id in personal_ratings:
                personal_note += f" user_rating={personal_ratings[t.id].get('avg_rating', 0):.1f}"
            if t.id in personal_outcomes:
                personal_note += f" outcome={personal_outcomes[t.id].get('avg_effectiveness', 0):+.2f}"
            print(f"[TOOL]    {r['name']} ({r['category']}) score="
                  f"{(_score(t, recently_used, personal_ratings, personal_outcomes, preferred_category_ids) + _emotion_fit_bonus(t, primary_sub_emotion, secondary_sub_emotions, detected_symptoms, detected_behaviors, detected_contexts) + semantic_scores.get(t.id, 0.0) + contextual_adjustments.get(t.id, 0.0)):.2f}"
                  f" semantic={semantic_scores.get(t.id, 0.0):+.2f} context={contextual_adjustments.get(t.id, 0.0):+.2f}"
                  f"{personal_note}")

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
            "target_sub_emotions": _technique_attr_list(t, "targetSubEmotions"),
            "target_symptoms": _technique_attr_list(t, "targetSymptoms"),
            "target_behaviors": _technique_attr_list(t, "targetBehaviors"),
            "avoid_sub_emotions": _technique_attr_list(t, "avoidSubEmotions"),
            "avoid_symptoms": _technique_attr_list(t, "avoidSymptoms"),
            "avoid_behaviors": _technique_attr_list(t, "avoidBehaviors"),
            "min_intensity":    float(getattr(t, "minIntensity", 0.0) or 0.0),
            "max_intensity":    float(getattr(t, "maxIntensity", 1.0) or 1.0),
            "pacing_tier":      getattr(t, "pacingTier", "normal") or "normal",
            "delivery_mode":    getattr(t, "deliveryMode", "exercise") or "exercise",
            "best_for_contexts": _technique_attr_list(t, "bestForContexts"),
        }

    except Exception as e:
        print(f"[TOOL] get_technique_by_name ERROR: {str(e)[:120]}")
        return None

