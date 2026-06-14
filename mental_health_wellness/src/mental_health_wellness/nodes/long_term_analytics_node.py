"""
Long-term analytics updater for SentiMind.

This node runs only in the post-response/background path. It refreshes the
analytics tables that power dashboards and personalization without adding user
response latency.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Any, Iterable

from ..agent.preprocessing import normalize_emotion
from ..agent.state import MentalHealthState
from ..db.prisma_json import prisma_json
from ..utils.turn_lifecycle import normalize_turn_type, refine_turn_type


_EMOTION_TO_PRISMA = {
    "anger": "ANGER",
    "disgust": "DISGUST",
    "fear": "FEAR",
    "joy": "JOY",
    "neutral": "NEUTRAL",
    "sadness": "SADNESS",
    "surprise": "SURPRISE",
    "anxiety": "ANXIETY",
    "happy": "JOY",
    "sad": "SADNESS",
    "angry": "ANGER",
    "anxious": "ANXIETY",
    "worried": "ANXIETY",
    "scared": "FEAR",
    "frustrated": "ANGER",
    "hopeless": "SADNESS",
    "stressed": "ANXIETY",
    "depressed": "SADNESS",
    "overwhelmed": "ANXIETY",
}

_NEGATIVE_EMOTIONS = {"ANGER", "DISGUST", "FEAR", "SADNESS", "ANXIETY"}
_POSITIVE_EMOTIONS = {"JOY", "SURPRISE"}
_QUALIFYING_TURN_TYPES = {
    "INITIAL_DISCLOSURE",
    "FOLLOW_UP_DISCLOSURE",
    "POST_RECOMMENDATION_REACTION",
    "CRISIS_DISCLOSURE",
}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _db_emotion(value: Any) -> str:
    normalized = normalize_emotion(str(value or "neutral")).lower()
    return _EMOTION_TO_PRISMA.get(normalized, "NEUTRAL")


def _db_sentiment(emotion: str, explicit: Any = None) -> str:
    explicit_value = str(explicit or "").upper()
    if explicit_value in {"POSITIVE", "NEGATIVE", "NEUTRAL"}:
        return explicit_value
    if emotion in _POSITIVE_EMOTIONS:
        return "POSITIVE"
    if emotion in _NEGATIVE_EMOTIONS:
        return "NEGATIVE"
    return "NEUTRAL"


def _db_phase(value: Any) -> str | None:
    phase = str(value or "").lower().strip()
    phase_map = {
        "venting": "VENTING",
        "reflection": "REFLECTION",
        "understanding": "REFLECTION",
        "discovery": "REFLECTION",
        "solution": "SOLUTION",
        "intervention": "SOLUTION",
        "follow_up": "RECOVERY",
        "follow-up": "RECOVERY",
        "recovery": "RECOVERY",
    }
    return phase_map.get(phase)


def _get_created_at(record: Any) -> datetime | None:
    value = getattr(record, "createdAt", None)
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _unique_dates(records: Iterable[Any]) -> list:
    dates = set()
    for record in records:
        created = _get_created_at(record)
        if created:
            dates.add(created.date())
    return sorted(dates)


def _qualifying_turn_record(record: Any) -> bool:
    if not hasattr(record, "turnType"):
        return True
    turn_type = normalize_turn_type(str(getattr(record, "turnType", "") or ""))
    return bool(turn_type in _QUALIFYING_TURN_TYPES)


def _build_profile_signal_records(mood_logs: list[Any], snapshots: list[Any]) -> list[Any]:
    mood_session_ids = {
        getattr(log, "sessionId", None)
        for log in mood_logs
        if getattr(log, "sessionId", None)
    }
    records = list(mood_logs)
    records.extend(
        snapshot for snapshot in snapshots
        if _qualifying_turn_record(snapshot)
        and getattr(snapshot, "sessionId", None) not in mood_session_ids
    )
    return sorted(
        records,
        key=lambda item: _get_created_at(item) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )


def _current_streak(dates: list) -> int:
    if not dates:
        return 0
    today = datetime.now(timezone.utc).date()
    most_recent = dates[-1]
    if (today - most_recent).days > 1:
        return 0

    streak = 0
    expected = most_recent
    date_set = set(dates)
    while expected in date_set:
        streak += 1
        expected -= timedelta(days=1)
    return streak


def _longest_streak(dates: list) -> int:
    if not dates:
        return 0

    longest = 1
    current = 1
    for previous, current_date in zip(dates, dates[1:]):
        if (current_date - previous).days == 1:
            current += 1
            longest = max(longest, current)
        elif current_date != previous:
            current = 1
    return longest


def _mood_score(record: Any) -> float:
    emotion = str(getattr(record, "emotion", "NEUTRAL") or "NEUTRAL").upper()
    sentiment = str(getattr(record, "sentiment", "") or "").upper()
    intensity = _clamp(_to_float(getattr(record, "intensity", 0.5), 0.5))

    if sentiment == "POSITIVE" or emotion in _POSITIVE_EMOTIONS:
        return round(5.0 + (intensity * 5.0), 2)
    if sentiment == "NEGATIVE" or emotion in _NEGATIVE_EMOTIONS:
        return round(5.0 - (intensity * 4.0), 2)
    return round(5.0, 2)


def _mode(values: Iterable[Any], default: str = "NEUTRAL") -> str:
    cleaned = [str(value).upper() for value in values if value]
    if not cleaned:
        return default
    return Counter(cleaned).most_common(1)[0][0]


def _merge_limited(existing: Iterable[str] | None, new_items: Iterable[str], limit: int = 8) -> list[str]:
    merged: list[str] = []
    for item in list(existing or []) + list(new_items or []):
        text = str(item or "").strip()
        if text and text.lower() not in {value.lower() for value in merged}:
            merged.append(text[:80])
        if len(merged) >= limit:
            break
    return merged


def _extract_trigger_candidates(state: MentalHealthState) -> list[str]:
    candidates = []
    for key in ("primary_concern", "current_topic", "triggering_subject", "triggering_context"):
        value = state.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())
    for key in ("detected_contexts", "detected_behaviors", "detected_symptoms"):
        for item in state.get(key) or []:
            text = str(item or "").replace("_", " ").strip()
            if text:
                candidates.append(text)
    flags = state.get("gate_context_flags") or state.get("context_flags") or []
    for flag in flags:
        text = str(flag or "").replace("_", " ").strip()
        if text and any(word in text for word in ("exam", "work", "family", "sleep", "presentation", "relationship")):
            candidates.append(text)
    return candidates


def _message_depth_score(state: MentalHealthState) -> float:
    messages = state.get("messages") or []
    latest = getattr(messages[-1], "content", "") if messages else ""
    word_count = len(str(latest or "").split())
    if word_count >= 60:
        return 0.85
    if word_count >= 30:
        return 0.7
    if word_count >= 12:
        return 0.55
    return 0.35


def _social_dependency_score(state: MentalHealthState) -> float:
    messages = state.get("messages") or []
    latest = str(getattr(messages[-1], "content", "") if messages else "").lower()
    if not latest:
        return 0.5
    social_terms = ("people", "teacher", "friend", "family", "class", "others", "everyone", "relationship")
    hits = sum(1 for term in social_terms if term in latest)
    return _clamp(0.35 + (hits * 0.15))


def _classify_turn_type(state: MentalHealthState) -> str:
    """
    Classifies the conversation turn type deterministically.
    Returns one of the TurnType enum values.
    """
    final = normalize_turn_type(state.get("turn_type"), default=None)
    if final:
        return final

    guess = normalize_turn_type(state.get("turn_type_guess"), default=None)
    if guess:
        return refine_turn_type(
            state=dict(state),
            previous_context=state.get("previous_turn_context") or {},
        )

    try:
        turn = int(state.get("session_message_count") or 0)
    except (TypeError, ValueError):
        turn = 0

    messages = state.get("messages") or []
    user_msg_content = ""
    last_assistant_msg = ""

    # Extract last user message and last assistant message content
    for msg in reversed(messages):
        role_raw = getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else None)
        if not role_raw:
            continue
        role_str = str(role_raw.name if hasattr(role_raw, "name") else role_raw).upper()
        content = getattr(msg, "content", "") if not isinstance(msg, dict) else msg.get("content", "")

        if "USER" in role_str and not user_msg_content:
            user_msg_content = str(content)
        elif "ASSISTANT" in role_str and not last_assistant_msg:
            last_assistant_msg = str(content)

    user_words = user_msg_content.split()
    user_word_count = len(user_words)

    # 1. INITIAL_DISCLOSURE: First user message in the session (turn <= 2)
    if turn <= 2:
        return "INITIAL_DISCLOSURE"

    # 2. POST_RECOMMENDATION_REACTION: Immediately after technique recommendation
    strategy = str(state.get("conversation_strategy") or "").lower()
    gate_route = str(state.get("gate_route") or "").lower()
    assistant_recommended = False
    if last_assistant_msg:
        lowered = last_assistant_msg.lower()
        if "try" in lowered or "exercise" in lowered or "practice" in lowered or "technique" in lowered:
            assistant_recommended = True

    if "suggest" in strategy or "technique" in strategy or "follow_up" in gate_route or "positive_feedback" in gate_route or assistant_recommended:
        return "POST_RECOMMENDATION_REACTION"

    # 3. CONTEXT_GATHERING: System asked a question, user replied briefly without new symptoms
    has_question = "?" in last_assistant_msg
    symptoms = state.get("detected_symptoms") or []
    if (user_word_count < 12 and not symptoms) or (has_question and user_word_count < 15 and not symptoms):
        return "CONTEXT_GATHERING"

    # 4. Fallback: FOLLOW_UP_DISCLOSURE
    return "FOLLOW_UP_DISCLOSURE"


async def _save_emotion_snapshot(prisma: Any, state: MentalHealthState, emotion: str, sentiment: str, intensity: float) -> bool:
    user_id = state.get("user_id")
    session_id = state.get("session_id")
    if not user_id or not session_id:
        return False

    try:
        turn = int(state.get("session_message_count") or 0)
    except (TypeError, ValueError):
        turn = 0

    if turn <= 0:
        try:
            turn = await prisma.emotionsnapshot.count(where={"sessionId": session_id}) + 1
        except Exception:
            turn = 1

    distortions = state.get("all_distortions") or []
    distortion = None
    if isinstance(distortions, list) and distortions:
        distortion = str(distortions[0])[:80]
    elif state.get("distortion_type"):
        distortion = str(state.get("distortion_type"))[:80]

    phase = _db_phase(state.get("conversation_phase") or state.get("conversation_stage"))
    turn_type = _classify_turn_type(state)
    recommended_technique = state.get("recommended_technique") or {}
    technique_id = (
        recommended_technique.get("id")
        or recommended_technique.get("technique_id")
        or recommended_technique.get("techniqueId")
        if isinstance(recommended_technique, dict)
        else None
    )
    technique_offered = bool(state.get("technique_offered_this_turn") and technique_id)

    data = {
        "sessionId": session_id,
        "userId": user_id,
        "turn": turn,
        "emotion": emotion,
        "intensity": intensity,
        "sentiment": sentiment,
        "primarySubEmotion": state.get("primary_sub_emotion"),
        "secondarySubEmotions": state.get("secondary_sub_emotions") or [],
        "detectedSymptoms": state.get("detected_symptoms") or [],
        "detectedBehaviors": state.get("detected_behaviors") or [],
        "detectedContexts": state.get("detected_contexts") or [],
        "emotionScores": prisma_json(state.get("emotion_scores") or {}),
        "distortionType": distortion,
        "turnType": turn_type,
        "conversationPhase": str(state.get("conversation_phase") or state.get("conversation_stage") or "")[:80] or None,
        "responseStrategy": str(state.get("conversation_strategy") or "")[:80] or None,
        "techniqueOfferedThisTurn": technique_offered,
        "techniqueId": technique_id if technique_offered else None,
        "mismatch": bool(state.get("mismatch", False)),
        "possibleMasking": bool(state.get("possible_masking", False)),
        "fusionConfidence": state.get("fusion_confidence"),
        "transcriptionConfidence": state.get("transcription_confidence"),
        "voiceFeatureSnapshot": prisma_json(state.get("voice_feature_snapshot") or state.get("voice_features") or {}),
    }
    if phase:
        data["phase"] = phase

    await prisma.emotionsnapshot.create(data=data)
    try:
        existing = await prisma.session.find_unique(where={"id": session_id})
        current_peak = _to_float(getattr(existing, "peakIntensity", None), 0.0) if existing else 0.0
        if intensity >= current_peak:
            await prisma.session.update(
                where={"id": session_id},
                data={
                    "peakIntensity": intensity,
                    "peakIntensityTurnType": turn_type,
                },
            )
    except Exception as peak_err:
        print(f"[LONG_TERM] Session peak update skipped: {str(peak_err)[:100]}")
    return True


async def _refresh_user_statistics(prisma: Any, user_id: str) -> dict:
    (
        sessions,
        total_sessions,
        mood_logs,
        total_checkins,
        snapshots,
        ratings,
        existing,
    ) = await asyncio.gather(
        prisma.session.find_many(
            where={"userId": user_id},
            order={"startedAt": "desc"},
            take=500,
        ),
        prisma.session.count(where={"userId": user_id}),
        prisma.moodlog.find_many(
            where={"userId": user_id},
            order={"createdAt": "desc"},
            take=180,
        ),
        prisma.moodlog.count(where={"userId": user_id}),
        prisma.emotionsnapshot.find_many(
            where={"userId": user_id},
            order={"createdAt": "desc"},
            take=240,
        ),
        prisma.usertechniquerating.find_many(
            where={"userId": user_id},
            order={"usedAt": "desc"},
            take=250,
        ),
        prisma.userstatistics.find_unique(where={"userId": user_id}),
    )
    session_ids = [session.id for session in sessions]

    total_messages = 0
    if session_ids:
        try:
            total_messages = await prisma.message.count(where={"sessionId": {"in": session_ids}})
        except Exception:
            message_counts = await asyncio.gather(
                *(
                    prisma.message.count(where={"sessionId": session_id})
                    for session_id in session_ids[:100]
                )
            )
            total_messages = sum(message_counts)

    dates = _unique_dates(mood_logs)
    current_streak = _current_streak(dates)
    longest_streak = _longest_streak(dates)
    profile_records = _build_profile_signal_records(mood_logs, snapshots)
    mood_scores = [_mood_score(log) for log in profile_records]
    average_mood_rating = round(sum(mood_scores) / len(mood_scores), 2) if mood_scores else 5.0
    most_common_emotion = _mode((getattr(log, "emotion", None) for log in profile_records), "NEUTRAL")

    technique_ids = [getattr(rating, "techniqueId", None) for rating in ratings if getattr(rating, "techniqueId", None)]
    most_used_technique_id = Counter(technique_ids).most_common(1)[0][0] if technique_ids else None
    avg_technique_rating = (
        round(sum(_to_float(getattr(rating, "rating", 0), 0.0) for rating in ratings) / len(ratings), 2)
        if ratings
        else 0.0
    )

    existing_longest = int(getattr(existing, "longestCheckInStreak", 0) or 0) if existing else 0
    update_data = {
        "totalSessions": total_sessions,
        "totalMessages": total_messages,
        "totalCheckIns": total_checkins,
        "currentCheckInStreak": current_streak,
        "longestCheckInStreak": max(existing_longest, longest_streak),
        "averageMoodRating": average_mood_rating,
        "mostCommonEmotion": most_common_emotion,
        "totalTechniquesUsed": len(ratings),
        "avgTechniqueRating": avg_technique_rating,
        "lastSessionAt": getattr(sessions[0], "startedAt", None) if sessions else None,
        "lastCheckInAt": _get_created_at(mood_logs[0]) if mood_logs else None,
    }
    if most_used_technique_id:
        update_data["mostUsedTechniqueId"] = most_used_technique_id

    await prisma.userstatistics.upsert(
        where={"userId": user_id},
        data={
            "create": {"userId": user_id, **update_data},
            "update": update_data,
        },
    )

    return {
        "total_sessions": total_sessions,
        "total_messages": total_messages,
        "total_checkins": total_checkins,
        "average_mood_rating": average_mood_rating,
        "most_common_emotion": most_common_emotion,
        "current_streak": current_streak,
        "longest_streak": max(existing_longest, longest_streak),
        "avg_technique_rating": avg_technique_rating,
        "most_used_technique_id": most_used_technique_id,
        "mood_logs": mood_logs,
        "profile_records": profile_records,
        "ratings": ratings,
    }


async def _refresh_psych_profile(prisma: Any, user_id: str, state: MentalHealthState, stats: dict) -> dict:
    profile = await prisma.psychprofile.find_unique(where={"userId": user_id})
    mood_logs = stats.get("profile_records") or stats.get("mood_logs") or []
    ratings = stats.get("ratings") or []

    distress_logs = [
        log for log in mood_logs
        if str(getattr(log, "emotion", "") or "").upper() in _NEGATIVE_EMOTIONS
    ]
    anxiety_baseline = (
        round(sum(_to_float(getattr(log, "intensity", 0.0), 0.0) for log in distress_logs[:30]) / len(distress_logs[:30]), 3)
        if distress_logs[:30]
        else _to_float(getattr(profile, "anxietyBaseline", 0.5), 0.5)
    )

    # Group by calendar week for resilience tracking
    buckets = {}
    for log in mood_logs:
        created_at = _get_created_at(log)
        if not created_at:
            continue
        week_key = created_at.strftime("%Y-W%V")
        buckets.setdefault(week_key, []).append(_mood_score(log))

    sorted_weeks = sorted(buckets.keys(), reverse=True)
    recent_scores = []
    older_scores = []

    # Last 2 weeks
    for w in sorted_weeks[:2]:
        recent_scores.extend(buckets[w])
    # Prior 2 weeks
    for w in sorted_weeks[2:4]:
        older_scores.extend(buckets[w])

    old_resilience = _to_float(getattr(profile, "resilienceScore", 0.5), 0.5)
    resilience = old_resilience
    if recent_scores and older_scores:
        delta = (sum(recent_scores) / len(recent_scores)) - (sum(older_scores) / len(older_scores))
        resilience = _clamp(old_resilience + (delta / 10.0), 0.05, 0.95)
    elif recent_scores:
        resilience = _clamp((sum(recent_scores) / len(recent_scores)) / 10.0, 0.05, 0.95)

    completed = [rating for rating in ratings if bool(getattr(rating, "completed", False))]
    if ratings:
        technique_acc_rate = round(len(completed) / len(ratings), 3)
    else:
        technique_acc_rate = _to_float(getattr(profile, "techniqueAccRate", 0.5), 0.5)

    reflection_depth = round(
        (0.7 * _to_float(getattr(profile, "reflectionDepth", 0.5), 0.5)) + (0.3 * _message_depth_score(state)),
        3,
    )
    social_dependency = round(
        (0.7 * _to_float(getattr(profile, "socialDependency", 0.5), 0.5)) + (0.3 * _social_dependency_score(state)),
        3,
    )

    if technique_acc_rate >= 0.65 and stats.get("avg_technique_rating", 0) >= 3.5:
        coping_style = "proactive"
    elif technique_acc_rate <= 0.35:
        coping_style = "avoidant"
    else:
        coping_style = "mixed"

    distortions = state.get("all_distortions") or []
    new_distortions = [str(item).strip() for item in distortions if str(item).strip()]
    existing_distortions = getattr(profile, "topDistortions", []) if profile else []
    existing_triggers = getattr(profile, "emotionalTriggers", []) if profile else []
    existing_count = int(getattr(profile, "distortionCount", 0) or 0) if profile else 0

    update_data = {
        "copingStyle": coping_style,
        "techniqueAccRate": technique_acc_rate,
        "reflectionDepth": _clamp(reflection_depth),
        "anxietyBaseline": _clamp(anxiety_baseline),
        "resilienceScore": round(_clamp(resilience), 3),
        "dominantEmotion": str(stats.get("most_common_emotion", "NEUTRAL")).lower(),
        "emotionalTriggers": _merge_limited(existing_triggers, _extract_trigger_candidates(state)),
        "motivationType": getattr(profile, "motivationType", "mixed") if profile else "mixed",
        "socialDependency": _clamp(social_dependency),
        "topDistortions": _merge_limited(existing_distortions, new_distortions),
        "distortionCount": existing_count + len(new_distortions),
    }

    await prisma.psychprofile.upsert(
        where={"userId": user_id},
        data={
            "create": {"userId": user_id, **update_data},
            "update": update_data,
        },
    )
    return update_data


async def update_long_term_analytics(state: MentalHealthState) -> dict:
    """
    Persist and refresh analytics for the dashboard and personalization.

    This is intentionally non-LLM and exception-safe. It can run after the user
    has already received a response.
    """
    user_id = state.get("user_id")
    if not user_id:
        return {"analytics_updated": False, "analytics_error": "missing_user_id"}

    try:
        from ..db.client import get_prisma_client

        prisma = await get_prisma_client()
        emotion = _db_emotion(state.get("fused_emotion") or state.get("emotion"))
        intensity = _clamp(_to_float(state.get("fused_intensity", state.get("intensity", 0.5)), 0.5))
        sentiment = _db_sentiment(emotion, state.get("sentiment"))

        snapshot_saved = await _save_emotion_snapshot(prisma, state, emotion, sentiment, intensity)
        stats = await _refresh_user_statistics(prisma, user_id)
        profile = await _refresh_psych_profile(prisma, user_id, state, stats)

        print(
            "[NODE: LONG_TERM_ANALYTICS]  Updated | "
            f"emotion={emotion} | intensity={intensity:.0%} | "
            f"mood={stats.get('average_mood_rating')} | "
            f"streak={stats.get('current_streak')}"
        )
        try:
            from ..services.cache_state import invalidate_user_cache

            invalidate_user_cache(user_id, session_id=state.get("session_id"))
        except Exception as cache_err:
            print(f"[NODE: LONG_TERM_ANALYTICS] Cache invalidation skipped: {str(cache_err)[:100]}")

        return {
            "analytics_updated": True,
            "emotion_snapshot_saved": snapshot_saved,
            "dashboard_signals": {
                "average_mood_rating": stats.get("average_mood_rating"),
                "most_common_emotion": stats.get("most_common_emotion"),
                "current_checkin_streak": stats.get("current_streak"),
                "dominant_emotion": profile.get("dominantEmotion"),
                "coping_style": profile.get("copingStyle"),
                "resilience_score": profile.get("resilienceScore"),
                "technique_acceptance_rate": profile.get("techniqueAccRate"),
            },
        }
    except Exception as e:
        print(f"[NODE: LONG_TERM_ANALYTICS]  Skipped: {str(e)[:120]}")
        return {"analytics_updated": False, "analytics_error": str(e)[:200]}
