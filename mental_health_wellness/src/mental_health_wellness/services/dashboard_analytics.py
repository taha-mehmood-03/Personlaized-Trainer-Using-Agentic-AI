"""
Dashboard analytics service.

Builds one data-backed payload for advanced user dashboards. The service uses
only persisted records and deterministic scoring, so the frontend can render
long-term outcomes without inventing metrics.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime, timezone, timedelta
from statistics import mean
from typing import Any, Awaitable

from .cache_state import user_cache_version

_POSITIVE = {"JOY", "SURPRISE", "POSITIVE"}
_NEGATIVE = {"ANGER", "DISGUST", "FEAR", "SADNESS", "ANXIETY", "NEGATIVE"}
_QUALIFYING_TURN_TYPES = {
    "INITIAL_DISCLOSURE",
    "FOLLOW_UP_DISCLOSURE",
    "POST_RECOMMENDATION_REACTION",
    "CRISIS_DISCLOSURE",
}
_DASHBOARD_CACHE: dict[tuple[str, int], tuple[int, dict[str, Any]]] = {}


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return None
    return str(value)


def _enum(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value)
    return text.split(".")[-1]


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _score_from_mood(record: Any) -> float:
    emotion = _enum(getattr(record, "emotion", None), "NEUTRAL").upper()
    sentiment = _enum(getattr(record, "sentiment", None), "").upper()
    intensity = max(0.0, min(1.0, _float(getattr(record, "intensity", 0.5), 0.5)))
    if sentiment in _POSITIVE or emotion in _POSITIVE:
        return round(5.0 + intensity * 5.0, 2)
    if sentiment in _NEGATIVE or emotion in _NEGATIVE:
        return round(5.0 - intensity * 4.0, 2)
    return 5.0


def _trend(values: list[float]) -> dict:
    if len(values) < 4:
        return {"label": "insufficient_data", "delta": 0.0}
    midpoint = max(1, len(values) // 2)
    earlier = values[:midpoint]
    recent = values[midpoint:]
    delta = round(mean(recent) - mean(earlier), 2)
    if delta >= 0.5:
        label = "improving"
    elif delta <= -0.5:
        label = "declining"
    else:
        label = "stable"
    return {"label": label, "delta": delta}


def _volatility(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    diffs = [abs(values[idx] - values[idx - 1]) for idx in range(1, len(values))]
    return round(mean(diffs), 2)


def _record_date(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _filter_window(records: list[Any], days: int, attr: str = "createdAt") -> list[Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    filtered = []
    for record in records:
        created = _record_date(getattr(record, attr, None))
        if created is None or created.tzinfo is None:
            if created is None:
                filtered.append(record)
            elif created.replace(tzinfo=timezone.utc) >= cutoff:
                filtered.append(record)
        elif created >= cutoff:
            filtered.append(record)
    return filtered


def _safe_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _clean_signal(value: Any) -> str:
    return str(value or "").strip().lower()


def _add_list_signals(counter: Counter, values: Any) -> None:
    for item in _safe_list(values):
        signal = _clean_signal(item)
        if signal:
            counter[signal] += 1


def _single_attr_counter(records: list[Any], attr: str) -> Counter:
    counter: Counter = Counter()
    for record in records:
        signal = _clean_signal(getattr(record, attr, None))
        if signal:
            counter[signal] += 1
    return counter


def _list_attr_counter(records: list[Any], attr: str) -> Counter:
    counter: Counter = Counter()
    for record in records:
        _add_list_signals(counter, getattr(record, attr, []))
    return counter


def _counter_items(counter: Counter, key: str, limit: int = 10) -> list[dict]:
    total = sum(counter.values())
    return [
        {
            key: name,
            "count": count,
            "percentage": round((count / total) * 100) if total else 0,
        }
        for name, count in counter.most_common(limit)
    ]


def _average_intensity(records: list[Any]) -> float:
    values = [
        _float(getattr(record, "intensity", None), 0.0)
        for record in records
        if getattr(record, "intensity", None) is not None
    ]
    return round(mean(values), 3) if values else 0.0


def _emotion_baselines(records: list[Any]) -> dict[str, float]:
    grouped: dict[str, list[float]] = {}
    for record in records:
        emotion = _enum(getattr(record, "emotion", None), "NEUTRAL").lower()
        grouped.setdefault(emotion, []).append(_float(getattr(record, "intensity", 0.0), 0.0))
    return {
        emotion: round(mean(values), 3)
        for emotion, values in sorted(grouped.items())
        if values
    }


def _counter_delta(before: Counter, after: Counter, *, direction: str, limit: int = 6) -> list[dict]:
    rows = []
    names = set(before) | set(after)
    for name in names:
        delta = after.get(name, 0) - before.get(name, 0)
        if direction == "down" and delta < 0:
            rows.append({"name": name, "delta": abs(delta), "before": before.get(name, 0), "after": after.get(name, 0)})
        elif direction == "up" and delta > 0:
            rows.append({"name": name, "delta": delta, "before": before.get(name, 0), "after": after.get(name, 0)})
    return sorted(rows, key=lambda row: row["delta"], reverse=True)[:limit]


def _merge_signal_records(mood_logs: list[Any], snapshots: list[Any]) -> list[Any]:
    """
    Merge MoodLog and EmotionSnapshot records into a single chronological list.

    Previously the dashboard chose one source or the other. Now we use both
    so that all available data informs the trend. Duplicate createdAt values
    (same second) favour the MoodLog record since it is the authoritative
    per-session summary.
    """
    # Deduplicate by session_id: prefer MoodLog when both cover the same session
    mood_session_ids: set[str] = set()
    for record in mood_logs:
        sid = getattr(record, "sessionId", None)
        if sid:
            mood_session_ids.add(sid)

    extra_snapshots = [
        snap for snap in snapshots
        if getattr(snap, "sessionId", None) not in mood_session_ids
    ]

    merged = list(mood_logs) + extra_snapshots
    # Sort ascending (oldest first) by createdAt
    merged.sort(key=lambda r: _record_date(getattr(r, "createdAt", None)) or datetime.min.replace(tzinfo=timezone.utc))
    return merged


def _filter_turn_types(records: list[Any]) -> list[Any]:
    filtered = []
    for r in records:
        if hasattr(r, "turnType"):
            tt_val = getattr(r, "turnType")
            if tt_val is None:
                filtered.append(r)
            else:
                tt_str = str(tt_val).upper().split(".")[-1]
                if tt_str == "POST_RECOMMENDATION":
                    tt_str = "POST_RECOMMENDATION_REACTION"
                if tt_str in _QUALIFYING_TURN_TYPES:
                    filtered.append(r)
        else:
            filtered.append(r)
    return filtered


def _bucket_scores_and_intensities(records: list[Any]) -> dict[str, dict[str, list[float]]]:
    buckets = {}
    for r in records:
        created = _record_date(getattr(r, "createdAt", None))
        if not created:
            continue
        week_key = created.strftime("%Y-W%V")
        score = _score_from_mood(r)
        intensity = _float(getattr(r, "intensity", None), None) # type: ignore[arg-type]
        
        week_data = buckets.setdefault(week_key, {"scores": [], "intensities": []})
        week_data["scores"].append(score)
        if intensity is not None:
            week_data["intensities"].append(intensity)
    return buckets


def _build_within_session_improvement(
    sessions: list[Any],
    snapshots: list[Any],
    outcomes: list[Any],
) -> dict:
    """
    Computes within-session distress relief from Session.peakIntensity to the
    final qualifying disclosure/reaction snapshot in that session.

    TechniqueOutcome remains as a fallback for older sessions that predate peak
    session fields.
    """
    valid_deltas = []
    snapshots_by_session: dict[str, list[Any]] = {}
    for snapshot in snapshots:
        sid = getattr(snapshot, "sessionId", None)
        if sid:
            snapshots_by_session.setdefault(sid, []).append(snapshot)

    for session in sessions:
        sid = getattr(session, "id", None)
        peak = getattr(session, "peakIntensity", None)
        if not sid or peak is None:
            continue
        session_snapshots = sorted(
            snapshots_by_session.get(sid, []),
            key=lambda snap: _record_date(getattr(snap, "createdAt", None)) or datetime.min.replace(tzinfo=timezone.utc),
        )
        qualifying = _filter_turn_types(session_snapshots)
        if not qualifying:
            continue
        final_intensity = getattr(qualifying[-1], "intensity", None)
        if final_intensity is not None:
            valid_deltas.append(_float(peak) - _float(final_intensity))

    source = "session_peak_to_final"
    if not valid_deltas:
        source = "technique_outcomes"
        for outcome in outcomes:
            ib = getattr(outcome, "intensityBefore", None)
            ia = getattr(outcome, "intensityAfter", None)
            if ib is not None and ia is not None:
                valid_deltas.append(_float(ib) - _float(ia))

    if not valid_deltas:
        return {
            "avg_intensity_delta": 0.0,
            "sessions_measured": 0,
            "label": "insufficient_data",
            "summary": "No completed session peak-to-final records to measure immediate within-session relief.",
            "source": source,
        }

    avg_delta = round(mean(valid_deltas), 3)
    count = len(valid_deltas)

    if avg_delta >= 0.15:
        label = "relieving"
        summary = f"Techniques are delivering immediate relief, reducing distress by {round(avg_delta * 100)}% on average."
    elif avg_delta <= -0.05:
        label = "worsening"
        summary = "Techniques are associated with increased distress. Adjusting matching profile."
    else:
        label = "neutral"
        summary = "Techniques show minor or no immediate impact on distress levels."

    return {
        "avg_intensity_delta": avg_delta,
        "sessions_measured": count,
        "label": label,
        "summary": summary,
        "source": source,
    }


def _build_session_outcome_stats(summaries: list[Any]) -> dict:
    """
    Count positive / neutral / negative session outcomes from SessionSummary records.

    The `outcome` field stores free-text that the agent generates (e.g. "positive",
    "improved", "negative", "difficult", "neutral"). We bucket loosely.
    """
    positive_terms = {"positive", "improved", "resolved", "better", "good", "great", "progress"}
    negative_terms = {"negative", "difficult", "worse", "hard", "struggle", "crisis", "declined"}

    counts = {"positive": 0, "neutral": 0, "negative": 0, "total": len(summaries)}
    for summary in summaries:
        outcome = str(getattr(summary, "outcome", "") or "").lower().strip()
        if any(term in outcome for term in positive_terms):
            counts["positive"] += 1
        elif any(term in outcome for term in negative_terms):
            counts["negative"] += 1
        else:
            counts["neutral"] += 1
    return counts


def _build_session_score_trajectory(recent_session_details: list[Any]) -> list[dict]:
    """
    Build a per-session average score series (oldest→newest) for charting.

    Each entry has: session_id, title, started_at, average_score (0-100), dominant_emotion.
    Scores are returned in the 0-100 percent scale so the frontend can plot them
    directly alongside MoodChart data points.
    """
    trajectory = []
    for session in reversed(recent_session_details):  # reversed → chronological
        messages = list(getattr(session, "messages", []) or [])
        user_messages = [
            msg for msg in messages
            if str(getattr(msg, "role", "")).split(".")[-1].upper() == "USER"
        ]
        scores = [_score_from_mood(msg) for msg in user_messages if getattr(msg, "emotion", None)]
        if not scores:
            continue
        avg = round(mean(scores), 2)
        summaries = list(getattr(session, "summaries", []) or [])
        summary = summaries[-1] if summaries else None
        trajectory.append({
            "session_id": getattr(session, "id", None),
            "title": getattr(session, "title", None) or (getattr(summary, "title", None) if summary else None) or "Session",
            "started_at": _iso(getattr(session, "startedAt", None)),
            "average_score": round(avg * 10),  # scale to 0-100
            "dominant_emotion": (
                _enum(getattr(user_messages[0], "emotion", None), "neutral").lower()
                if user_messages else "neutral"
            ),
            "outcome": getattr(summary, "outcome", None) if summary else None,
        })
    return trajectory[-15:]  # keep last 15 sessions


def _build_ranked_techniques(
    ratings: list[Any],
    outcomes: list[Any],
    technique_lookup: dict,
) -> list[dict]:
    """
    Rank techniques by a composite score: usage × effectiveness.

    composite = usage_count * max(0, mean_effectiveness)
    Falls back to usage_count when no outcomes exist.
    Returns up to 5 entries, each with name, category, usageCount, effectiveness (0-100%).
    """
    from collections import defaultdict
    usage: dict[str, int] = Counter()
    effectiveness_sums: dict[str, list[float]] = defaultdict(list)

    for rating in ratings:
        tid = getattr(rating, "techniqueId", None)
        if tid:
            usage[tid] += 1

    for outcome in outcomes:
        tid = getattr(outcome, "techniqueId", None)
        eff = _float(getattr(outcome, "effectiveness", None), None)  # type: ignore[arg-type]
        if tid and eff is not None:
            effectiveness_sums[tid].append(eff)

    entries = []
    for tid in set(list(usage.keys()) + list(effectiveness_sums.keys())):
        info = technique_lookup.get(tid, {})
        name = info.get("name") or tid
        category = info.get("category") or "general"
        use_count = usage.get(tid, 0)
        eff_values = effectiveness_sums.get(tid, [])
        mean_eff = round(mean(eff_values), 3) if eff_values else None
        # Composite: more usage AND higher effectiveness → ranks higher
        if mean_eff is not None:
            composite = use_count * max(0.0, mean_eff)
        else:
            composite = use_count * 0.5  # neutral weight when no outcomes
        entries.append({
            "name": name,
            "category": category,
            "usageCount": use_count,
            "meanEffectiveness": round(mean_eff * 100) if mean_eff is not None else None,
            "compositeScore": round(composite, 3),
        })

    entries.sort(key=lambda e: e["compositeScore"], reverse=True)
    return entries[:5]


def _build_improvement_analysis(
    scores: list[float],
    records: list[Any],
    outcomes: list[Any],
    profile: dict,
    session_outcome_stats: dict | None = None,
    crisis_count: int = 0,
    high_risk_crisis_count: int = 0,
    is_new_account: bool = False,
) -> dict:
    """
    Multi-signal improvement analysis.

    Status is determined by a weighted composite of:
      - Mood score delta          (35%) — primary long-term signal
      - Distress intensity delta  (15%) — secondary signal
      - Technique outcome ratio   (15%) — exercise effectiveness
      - Session outcome ratio     (15%) — per-session positive/negative ratio
      - Crisis frequency          (10%) — recent crisis events as negative modifier
      - Resilience bonus          (10%) — recovery capacity signal

    The status thresholds use the composite score so that a strong score
    improvement overrides a minor intensity fluctuation (the old AND bug).
    """
    if is_new_account or len(scores) < 4 or len(records) < 4:
        return {
            "status": "insufficient_data",
            "summary": "More mood records are needed before the dashboard can explain a reliable improvement trend.",
            "score_delta": 0.0,
            "intensity_delta": 0.0,
            "contributing_factors": [],
            "blockers": [],
            "symptoms_reduced": [],
            "symptoms_increased": [],
            "evidence": [],
            "composite_score": 0.5,
        }

    # Group by calendar week for stable comparison
    buckets = _bucket_scores_and_intensities(records)
    sorted_weeks = sorted(buckets.keys(), reverse=True)

    if len(sorted_weeks) < 2:
        return {
            "status": "insufficient_data",
            "summary": "More mood records are needed before the dashboard can explain a reliable improvement trend.",
            "score_delta": 0.0,
            "intensity_delta": 0.0,
            "contributing_factors": [],
            "blockers": [],
            "symptoms_reduced": [],
            "symptoms_increased": [],
            "evidence": [],
            "composite_score": 0.5,
        }

    recent_scores = []
    recent_intensities = []
    recent_records = []
    for w in sorted_weeks[:2]:
        recent_scores.extend(buckets[w]["scores"])
        recent_intensities.extend(buckets[w]["intensities"])
        for r in records:
            created = _record_date(getattr(r, "createdAt", None))
            if created and created.strftime("%Y-W%V") == w:
                recent_records.append(r)

    prior_scores = []
    prior_intensities = []
    early_records = []
    for w in sorted_weeks[2:4]:
        prior_scores.extend(buckets[w]["scores"])
        prior_intensities.extend(buckets[w]["intensities"])
        for r in records:
            created = _record_date(getattr(r, "createdAt", None))
            if created and created.strftime("%Y-W%V") == w:
                early_records.append(r)

    if not recent_scores or not prior_scores:
        return {
            "status": "insufficient_data",
            "summary": "More mood records are needed before the dashboard can explain a reliable improvement trend.",
            "score_delta": 0.0,
            "intensity_delta": 0.0,
            "contributing_factors": [],
            "blockers": [],
            "symptoms_reduced": [],
            "symptoms_increased": [],
            "evidence": [],
            "composite_score": 0.5,
        }

    score_delta = round(mean(recent_scores) - mean(prior_scores), 2)
    early_intensity = mean(prior_intensities) if prior_intensities else 0.0
    recent_intensity = mean(recent_intensities) if recent_intensities else 0.0
    intensity_delta = round(recent_intensity - early_intensity, 3)

    before_symptoms = _list_attr_counter(early_records, "detectedSymptoms")
    after_symptoms = _list_attr_counter(recent_records, "detectedSymptoms")
    symptoms_reduced = _counter_delta(before_symptoms, after_symptoms, direction="down")
    symptoms_increased = _counter_delta(before_symptoms, after_symptoms, direction="up")

    positive_outcomes = [
        outcome for outcome in outcomes
        if _float(getattr(outcome, "effectiveness", 0.0), 0.0) > 0.05
    ]
    negative_outcomes = [
        outcome for outcome in outcomes
        if _float(getattr(outcome, "effectiveness", 0.0), 0.0) < -0.05
    ]

    contributing_factors: list[str] = []
    blockers: list[str] = []
    evidence: list[str] = []

    # ── Signal 1: Mood score delta (40%) ────────────────────────────────────
    # Normalize score_delta from roughly -4..+4 to 0..1 (clamp)
    # score_delta of +2 → 0.75, 0 → 0.5, -2 → 0.25
    score_signal = max(0.0, min(1.0, 0.5 + score_delta / 8.0))
    if score_delta >= 0.5:
        contributing_factors.append(
            f"Mood score improved by {score_delta:.1f} points across the selected window."
        )
        evidence.append("Recent records show higher mood scores than earlier records.")
    elif score_delta <= -0.5:
        blockers.append(f"Mood score dropped by {abs(score_delta):.1f} points across the selected window.")
        evidence.append("Recent records show lower mood scores than earlier records.")
    else:
        evidence.append("Mood score is mostly stable across the selected window.")

    # ── Signal 2: Distress intensity delta (20%) ─────────────────────────────
    # intensity_delta < 0 is good (less distress). Normalize -0.3..+0.3 → 1..0
    intensity_signal = max(0.0, min(1.0, 0.5 - intensity_delta / 0.6))
    if intensity_delta <= -0.05:
        contributing_factors.append(
            f"Average distress intensity decreased from "
            f"{round(early_intensity * 100)}% to {round(recent_intensity * 100)}%."
        )
    elif intensity_delta >= 0.05:
        blockers.append(
            f"Average distress intensity increased from "
            f"{round(early_intensity * 100)}% to {round(recent_intensity * 100)}%."
        )

    # ── Signal 3: Symptom changes ─────────────────────────────────────────────
    if symptoms_reduced:
        names = ", ".join(item["name"].replace("_", " ") for item in symptoms_reduced[:3])
        contributing_factors.append(f"Reported symptoms eased: {names}.")
    if symptoms_increased:
        names = ", ".join(item["name"].replace("_", " ") for item in symptoms_increased[:3])
        blockers.append(f"Symptoms needing attention: {names}.")

    # ── Signal 4: Technique outcome ratio (20%) ───────────────────────────────
    total_outcomes = len(positive_outcomes) + len(negative_outcomes)
    if total_outcomes > 0:
        outcome_ratio = len(positive_outcomes) / total_outcomes
        technique_signal = outcome_ratio
        if len(positive_outcomes) > 0:
            contributing_factors.append(
                f"{len(positive_outcomes)} of {total_outcomes} technique outcome record(s) show "
                f"reduced distress after support ({round(outcome_ratio * 100)}% success rate)."
            )
        if len(negative_outcomes) > 0:
            blockers.append(
                f"{len(negative_outcomes)} technique record(s) show distress did not improve after support."
            )
    else:
        technique_signal = 0.5  # neutral if no outcomes yet

    # ── Signal 5: Session outcome ratio (20%) ─────────────────────────────────
    session_signal = 0.5  # neutral default
    if session_outcome_stats:
        positive_sessions = session_outcome_stats.get("positive", 0)
        negative_sessions = session_outcome_stats.get("negative", 0)
        total_sessions = session_outcome_stats.get("total", 0)
        if total_sessions >= 2:
            session_positive_ratio = positive_sessions / total_sessions
            session_signal = session_positive_ratio
            if session_positive_ratio >= 0.6:
                contributing_factors.append(
                    f"{positive_sessions} of {total_sessions} recent sessions ended positively "
                    f"({round(session_positive_ratio * 100)}%)."
                )
                evidence.append("Session outcomes are trending positive.")
            elif session_positive_ratio <= 0.3 and negative_sessions > 0:
                blockers.append(
                    f"{negative_sessions} of {total_sessions} recent sessions ended with difficult outcomes."
                )

    # ── Resilience signal (10%) ───────────────────────────────────────────────
    resilience = _float(profile.get("resilience_score"), 0.5)
    resilience_signal = resilience  # already 0..1
    if resilience >= 0.65:
        contributing_factors.append(
            "Resilience score is trending high, suggesting the user is recovering between hard moments."
        )
    elif resilience <= 0.35:
        blockers.append("Resilience score is still low, so progress may be fragile.")

    # ── Signal 6: Crisis frequency penalty (10%) ──────────────────────────────
    # No crises → neutral 0.5; many high-risk crises → pulls toward 0.0
    if crisis_count == 0:
        crisis_signal = 0.5  # no data yet: neutral
    elif high_risk_crisis_count >= 3:
        crisis_signal = 0.1
        blockers.append(
            f"{high_risk_crisis_count} high-risk crisis events recorded in this window. "
            f"Consistent safety monitoring is strongly recommended."
        )
    elif high_risk_crisis_count >= 1:
        crisis_signal = 0.3
        blockers.append(
            f"{high_risk_crisis_count} high-risk crisis event(s) recorded in this window."
        )
    elif crisis_count >= 3:
        crisis_signal = 0.35
        blockers.append(
            f"{crisis_count} crisis event(s) detected in this window. "
            f"Continued check-ins are important."
        )
    else:
        # Low-level crisis events, small penalty
        crisis_signal = max(0.0, 0.5 - crisis_count * 0.05)

    # ── Composite score (weighted, sums to 1.0) ───────────────────────────────
    composite = (
        0.35 * score_signal
        + 0.15 * intensity_signal
        + 0.15 * technique_signal
        + 0.15 * session_signal
        + 0.10 * crisis_signal
        + 0.10 * resilience_signal
    )
    composite = round(composite, 3)

    # ── Status from composite ──────────────────────────────────────────────────
    if composite >= 0.62:
        status = "improving"
    elif composite <= 0.40:
        status = "declining"
    else:
        status = "stable"

    # Override: a very strong score delta alone is enough to call "improving"
    if score_delta >= 1.5 and status != "declining":
        status = "improving"
    # Override: a strong score drop alone is enough to call "declining"
    if score_delta <= -1.5:
        status = "declining"

    if status == "improving":
        summary = (
            f"Mood is improving: recent scores are {abs(score_delta):.1f} pts {'higher' if score_delta >= 0 else 'lower'} "
            f"and the composite wellness score is {round(composite * 100)}%."
        )
    elif status == "declining":
        summary = (
            "Mood is getting harder. Recent scores and distress signals both point downward. "
            "Reviewing triggers and technique fit would help."
        )
    else:
        summary = (
            f"Mood is mostly stable (composite {round(composite * 100)}%). "
            "The dashboard is watching symptom and intensity changes for clearer movement."
        )

    return {
        "status": status,
        "summary": summary,
        "score_delta": score_delta,
        "intensity_delta": intensity_delta,
        "early_average_score": round(mean(prior_scores), 2),
        "recent_average_score": round(mean(recent_scores), 2),
        "early_average_intensity": early_intensity,
        "recent_average_intensity": recent_intensity,
        "contributing_factors": contributing_factors[:7],
        "blockers": blockers[:7],
        "symptoms_reduced": symptoms_reduced,
        "symptoms_increased": symptoms_increased,
        "evidence": evidence[:5],
        "composite_score": composite,
        "session_outcome_stats": session_outcome_stats or {},
    }


def _session_duration_minutes(messages: list[Any], started_at: Any = None, ended_at: Any = None) -> int:
    if started_at and ended_at:
        try:
            return max(1, round((ended_at - started_at).total_seconds() / 60))
        except Exception:
            pass
    if len(messages) >= 2:
        ordered = sorted(messages, key=lambda msg: getattr(msg, "createdAt", datetime.now(timezone.utc)))
        first = getattr(ordered[0], "createdAt", None)
        last = getattr(ordered[-1], "createdAt", None)
        if isinstance(first, datetime) and isinstance(last, datetime):
            return max(1, round((last - first).total_seconds() / 60))
    return 0


def _build_session_detail(session: Any) -> dict:
    messages = list(getattr(session, "messages", []) or [])
    user_messages = [
        msg for msg in messages
        if str(getattr(msg, "role", "")).split(".")[-1].upper() == "USER"
    ]
    scores = [_score_from_mood(msg) for msg in user_messages if getattr(msg, "emotion", None)]
    trend = _trend(scores) if scores else {"label": "insufficient_data", "delta": 0.0}
    emotion_counter = Counter(
        _enum(getattr(msg, "emotion", None), "NEUTRAL").lower()
        for msg in user_messages
        if getattr(msg, "emotion", None)
    )
    primary_counter = _single_attr_counter(user_messages, "primarySubEmotion")
    secondary_counter = _list_attr_counter(user_messages, "secondarySubEmotions")
    symptom_counter = _list_attr_counter(user_messages, "detectedSymptoms")
    behavior_counter = _list_attr_counter(user_messages, "detectedBehaviors")
    context_counter = _list_attr_counter(user_messages, "detectedContexts")

    summaries = list(getattr(session, "summaries", []) or [])
    summary = summaries[-1] if summaries else None
    techniques = _safe_list(getattr(summary, "techniques", [])) if summary else []
    if not techniques:
        for msg in messages:
            technique = getattr(msg, "technique", None)
            name = getattr(technique, "name", None) if technique else None
            if name:
                techniques.append(name)

    dominant_sub = primary_counter.most_common(1)[0][0] if primary_counter else None
    return {
        "id": getattr(session, "id", None),
        "title": getattr(session, "title", None) or getattr(summary, "title", None) or "Therapeutic session",
        "started_at": _iso(getattr(session, "startedAt", None)),
        "ended_at": _iso(getattr(session, "endedAt", None)),
        "duration_minutes": _session_duration_minutes(
            messages,
            getattr(session, "startedAt", None),
            getattr(session, "endedAt", None),
        ),
        "message_count": len(messages),
        "dominant_emotion": emotion_counter.most_common(1)[0][0] if emotion_counter else "neutral",
        "dominant_sub_emotion": dominant_sub,
        "secondary_sub_emotions": [name for name, _ in secondary_counter.most_common(6)],
        "detected_symptoms": [name for name, _ in symptom_counter.most_common(6)],
        "detected_behaviors": [name for name, _ in behavior_counter.most_common(6)],
        "detected_contexts": [name for name, _ in context_counter.most_common(6)],
        "average_score": round(mean(scores), 2) if scores else 5.0,
        "trend": trend,
        "summary": getattr(summary, "summary", None) if summary else None,
        "techniques": techniques[:4],
        "outcome": getattr(summary, "outcome", None) if summary else None,
    }


def _profile_dict(profile: Any) -> dict:
    if not profile:
        return {
            "coping_style": "unknown",
            "technique_acceptance_rate": 0.5,
            "reflection_depth": 0.5,
            "anxiety_baseline": 0.5,
            "resilience_score": 0.5,
            "dominant_emotion": "neutral",
            "emotional_triggers": [],
            "motivation_type": "mixed",
            "social_dependency": 0.5,
            "top_distortions": [],
            "distortion_count": 0,
        }
    return {
        "coping_style": getattr(profile, "copingStyle", "unknown"),
        "technique_acceptance_rate": _float(getattr(profile, "techniqueAccRate", 0.5), 0.5),
        "reflection_depth": _float(getattr(profile, "reflectionDepth", 0.5), 0.5),
        "anxiety_baseline": _float(getattr(profile, "anxietyBaseline", 0.5), 0.5),
        "resilience_score": _float(getattr(profile, "resilienceScore", 0.5), 0.5),
        "dominant_emotion": getattr(profile, "dominantEmotion", "neutral"),
        "emotional_triggers": _safe_list(getattr(profile, "emotionalTriggers", [])),
        "motivation_type": getattr(profile, "motivationType", "mixed"),
        "social_dependency": _float(getattr(profile, "socialDependency", 0.5), 0.5),
        "top_distortions": _safe_list(getattr(profile, "topDistortions", [])),
        "distortion_count": int(getattr(profile, "distortionCount", 0) or 0),
    }


def _build_suggestions(
    stats: Any,
    mood_trend: dict,
    average_score: float,
    volatility: float,
    profile: dict,
    preferred_categories: list[str],
) -> list[dict]:
    suggestions: list[dict] = []

    if mood_trend["label"] == "declining" or average_score < 4.0:
        suggestions.append({
            "priority": "high",
            "area": "mood",
            "title": "Mood decline needs attention",
            "action": "Show a check-in card, review recent triggers, and suggest a low-effort support plan.",
        })
    if volatility >= 1.5:
        suggestions.append({
            "priority": "medium",
            "area": "stability",
            "title": "Emotional volatility is elevated",
            "action": "Add a weekly pattern view and ask what changed on high-swing days.",
        })
    if profile["anxiety_baseline"] >= 0.65:
        suggestions.append({
            "priority": "medium",
            "area": "anxiety",
            "title": "Anxiety baseline is high",
            "action": "Prefer grounding, breathing, and preparation techniques before deeper reframes.",
        })
    if profile["technique_acceptance_rate"] >= 0.65 and preferred_categories:
        suggestions.append({
            "priority": "low",
            "area": "personalization",
            "title": "Personalized technique preference is emerging",
            "action": f"Prioritize {', '.join(preferred_categories[:2])} when the user asks for exercises.",
        })
    if int(getattr(stats, "currentCheckInStreak", 0) or 0) == 0:
        suggestions.append({
            "priority": "low",
            "area": "engagement",
            "title": "Check-in streak is inactive",
            "action": "Offer a simple daily mood check-in instead of a long form.",
        })
    return suggestions


async def _empty_on_error(awaitable: Awaitable[list[Any]]) -> list[Any]:
    try:
        return await awaitable
    except Exception:
        return []


async def build_user_dashboard(user_id: str, days: int = 30) -> dict:
    """
    Build a complete dashboard payload for one user.

    Args:
        user_id: User id from the application.
        days: Rolling window for trend views.
    """
    days = max(1, min(int(days or 30), 365))
    cache_key = (user_id, days)
    cache_version = user_cache_version(user_id)
    cached = _DASHBOARD_CACHE.get(cache_key)
    if cached and cached[0] == cache_version:
        return cached[1]

    from ..db.client import get_prisma_client

    prisma = await get_prisma_client()

    user = await prisma.user.find_unique(
        where={"id": user_id},
        include={"statistics": True, "preference": True, "psychProfile": True},
    )
    if not user:
        raise ValueError(f"User not found: {user_id}")

    (
        sessions,
        recent_session_details,
        mood_logs,
        snapshots,
        facts,
        summaries,
        ratings,
        crisis_logs,
    ) = await asyncio.gather(
        prisma.session.find_many(
            where={"userId": user_id},
            order={"startedAt": "desc"},
            take=60,
        ),
        _empty_on_error(prisma.session.find_many(
            where={"userId": user_id},
            order={"startedAt": "desc"},
            take=10,
            include={"messages": True, "summaries": True},
        )),
        prisma.moodlog.find_many(
            where={"userId": user_id},
            order={"createdAt": "desc"},
            take=240,
        ),
        prisma.emotionsnapshot.find_many(
            where={"userId": user_id},
            order={"createdAt": "desc"},
            take=300,
        ),
        prisma.userfact.find_many(
            where={"userId": user_id},
            order={"createdAt": "desc"},
            take=30,
        ),
        prisma.sessionsummary.find_many(
            where={"userId": user_id},
            order={"createdAt": "desc"},
            take=15,
        ),
        prisma.usertechniquerating.find_many(
            where={"userId": user_id},
            order={"usedAt": "desc"},
            take=100,
        ),
        _empty_on_error(prisma.crisislog.find_many(
            where={"userId": user_id},
            order={"createdAt": "desc"},
            take=30,
        )),
    )

    session_ids = [session.id for session in sessions]
    outcomes: list[Any] = []
    if session_ids:
        outcomes = await _empty_on_error(
            prisma.techniqueoutcome.find_many(
                where={"sessionId": {"in": session_ids}},
                order={"createdAt": "desc"},
                take=80,
            )
        )

    technique_ids = sorted({
        getattr(rating, "techniqueId", None) for rating in ratings
        if getattr(rating, "techniqueId", None)
    } | {
        getattr(outcome, "techniqueId", None) for outcome in outcomes
        if getattr(outcome, "techniqueId", None)
    })
    technique_lookup = {}
    if technique_ids:
        techniques = await _empty_on_error(
            prisma.technique.find_many(
                where={"id": {"in": technique_ids}},
                include={"category": True},
                take=len(technique_ids),
            )
        )
        for technique in techniques:
            category = getattr(technique, "category", None)
            technique_lookup[technique.id] = {
                "id": technique.id,
                "name": technique.name,
                "category": getattr(category, "name", None) if category else None,
                "avg_rating": _float(getattr(technique, "avgRating", 0.0), 0.0),
                "effectiveness": _float(getattr(technique, "effectiveness", 0.5), 0.5),
            }

    window_moods = list(reversed(_filter_window(mood_logs, days)))
    window_snapshots = list(reversed(_filter_window(snapshots, days)))
    # Merge both sources: MoodLog is the primary record; extra snapshots from
    # sessions without a MoodLog fill in the gaps for a richer signal set.
    signal_records = _merge_signal_records(window_moods, window_snapshots)
    # Timeline uses MoodLogs as the canonical series (or snapshots as fallback)
    # to keep the chart consistent and avoid duplicates.
    timeline_records = window_moods if window_moods else window_snapshots

    # Filter signal records by turn type to isolate disclosures from noise
    filtered_signals = _filter_turn_types(signal_records)
    mood_scores = [_score_from_mood(record) for record in filtered_signals]
    average_score = round(mean(mood_scores), 2) if mood_scores else 5.0
    mood_volatility = _volatility(mood_scores)

    # User-age gate for trend 'insufficient_data' state. Only qualifying
    # disclosure/reaction signals count as enough longitudinal data.
    qualifying_dates = []
    for record in filtered_signals:
        created = _record_date(getattr(record, "createdAt", None))
        if created:
            qualifying_dates.append(created.replace(tzinfo=timezone.utc) if created.tzinfo is None else created)
    has_any = bool(qualifying_dates)
    oldest_date = min(qualifying_dates) if qualifying_dates else datetime.now(timezone.utc)
    account_age_days = (datetime.now(timezone.utc) - oldest_date).days
    is_new_account = not has_any or account_age_days < 21
    distribution = Counter(_enum(getattr(record, "emotion", None), "NEUTRAL").upper() for record in filtered_signals)
    sub_distribution = _single_attr_counter(filtered_signals, "primarySubEmotion")
    secondary_distribution = _list_attr_counter(filtered_signals, "secondarySubEmotions")
    all_sub_distribution = Counter(sub_distribution)
    all_sub_distribution.update(secondary_distribution)
    symptom_distribution = _list_attr_counter(filtered_signals, "detectedSymptoms")
    behavior_distribution = _list_attr_counter(filtered_signals, "detectedBehaviors")
    context_distribution = _list_attr_counter(filtered_signals, "detectedContexts")
    emotion_baselines = _emotion_baselines(filtered_signals)
    distress_records = [
        record for record in filtered_signals
        if _enum(getattr(record, "emotion", None), "NEUTRAL").upper() in _NEGATIVE
    ]

    stats = getattr(user, "statistics", None)
    preferences = getattr(user, "preference", None)
    profile = _profile_dict(getattr(user, "psychProfile", None))
    profile["distress_baseline"] = (
        round(mean(_float(getattr(record, "intensity", 0.0), 0.0) for record in distress_records), 3)
        if distress_records
        else profile["anxiety_baseline"]
    )
    profile["emotion_baselines"] = emotion_baselines
    profile["top_primary_sub_emotions"] = [name for name, _ in sub_distribution.most_common(8)]
    profile["top_secondary_emotions"] = [name for name, _ in secondary_distribution.most_common(8)]
    profile["top_symptoms"] = [name for name, _ in symptom_distribution.most_common(8)]
    profile["top_behaviors"] = [name for name, _ in behavior_distribution.most_common(8)]
    profile["top_contexts"] = [name for name, _ in context_distribution.most_common(8)]
    preferred_categories = _safe_list(getattr(preferences, "preferredCategories", [])) if preferences else []

    outcome_values = [_float(getattr(outcome, "effectiveness", None), 0.0) for outcome in outcomes if getattr(outcome, "effectiveness", None) is not None]
    technique_effectiveness = round(mean(outcome_values), 3) if outcome_values else 0.0
    completed_ratings = [rating for rating in ratings if bool(getattr(rating, "completed", False))]
    adherence_rate = round(len(completed_ratings) / len(ratings), 3) if ratings else 0.0

    # Session-level outcome statistics (positive/neutral/negative ratio)
    session_outcome_stats = _build_session_outcome_stats(summaries)

    # Per-session score trajectory for the session progress chart
    session_score_trajectory = _build_session_score_trajectory(recent_session_details)

    # Composite-ranked techniques (usage × effectiveness)
    ranked_techniques = _build_ranked_techniques(ratings, outcomes, technique_lookup)

    # ── Crisis data ─────────────────────────────────────────────────────────
    crisis_count = len(crisis_logs)
    crisis_window = _filter_window(crisis_logs, days)
    recent_crisis_count = len(crisis_window)
    high_risk_crisis_count = sum(
        1 for c in crisis_window
        if _enum(getattr(c, "riskLevel", None), "").upper() in {"HIGH", "CRITICAL"}
    )

    # Improvement analysis (long-term trend)
    improvement_analysis = _build_improvement_analysis(
        scores=mood_scores,
        records=filtered_signals,
        outcomes=outcomes,
        profile=profile,
        session_outcome_stats=session_outcome_stats,
        crisis_count=recent_crisis_count,
        high_risk_crisis_count=high_risk_crisis_count,
        is_new_account=is_new_account,
    )
    mood_trend = {
        "label": improvement_analysis["status"],
        "delta": improvement_analysis.get("score_delta", 0.0),
    }
    suggestions = _build_suggestions(
        stats=stats,
        mood_trend=mood_trend,
        average_score=average_score,
        volatility=mood_volatility,
        profile=profile,
        preferred_categories=preferred_categories,
    )

    # Within-session improvement delta from peak distress to final qualifying turn
    within_session_improvement = _build_within_session_improvement(sessions, snapshots, outcomes)

    dashboard = {
        "success": True,
        "user_id": user_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_days": days,
        "overview": {
            "total_sessions": int(getattr(stats, "totalSessions", len(sessions)) or 0) if stats else len(sessions),
            "total_messages": int(getattr(stats, "totalMessages", 0) or 0) if stats else 0,
            "total_checkins": int(getattr(stats, "totalCheckIns", len(mood_logs)) or 0) if stats else len(mood_logs),
            "current_checkin_streak": int(getattr(stats, "currentCheckInStreak", 0) or 0) if stats else 0,
            "longest_checkin_streak": int(getattr(stats, "longestCheckInStreak", 0) or 0) if stats else 0,
            "average_mood_rating": _float(getattr(stats, "averageMoodRating", average_score), average_score) if stats else average_score,
            "most_common_emotion": _enum(getattr(stats, "mostCommonEmotion", None), distribution.most_common(1)[0][0] if distribution else "NEUTRAL"),
            "most_common_sub_emotion": sub_distribution.most_common(1)[0][0] if sub_distribution else None,
            "last_session_at": _iso(getattr(stats, "lastSessionAt", None)) if stats else None,
            "last_checkin_at": _iso(getattr(stats, "lastCheckInAt", None)) if stats else None,
        },
        "mood": {
            "average_score": average_score,
            "trend": mood_trend,
            "volatility": mood_volatility,
            "distribution": dict(distribution),
            "sub_emotion_distribution": dict(sub_distribution),
            "secondary_emotion_distribution": dict(secondary_distribution),
            "all_sub_emotion_distribution": dict(all_sub_distribution),
            "symptom_distribution": dict(symptom_distribution),
            "behavior_distribution": dict(behavior_distribution),
            "context_distribution": dict(context_distribution),
            "emotion_baselines": emotion_baselines,
            "top_sub_emotions": [
                {"sub_emotion": name, "count": count}
                for name, count in sub_distribution.most_common(8)
            ],
            "top_secondary_emotions": _counter_items(secondary_distribution, "emotion", 8),
            "top_symptoms": _counter_items(symptom_distribution, "symptom", 10),
            "top_behaviors": _counter_items(behavior_distribution, "behavior", 10),
            "top_contexts": _counter_items(context_distribution, "context", 10),
            "timeline": [
                {
                    "created_at": _iso(getattr(record, "createdAt", None)),
                    "emotion": _enum(getattr(record, "emotion", None), "NEUTRAL"),
                    "primary_sub_emotion": getattr(record, "primarySubEmotion", None),
                    "secondary_sub_emotions": _safe_list(getattr(record, "secondarySubEmotions", [])),
                    "detected_symptoms": _safe_list(getattr(record, "detectedSymptoms", [])),
                    "detected_behaviors": _safe_list(getattr(record, "detectedBehaviors", [])),
                    "detected_contexts": _safe_list(getattr(record, "detectedContexts", [])),
                    "sentiment": _enum(getattr(record, "sentiment", None), "NEUTRAL"),
                    "intensity": _float(getattr(record, "intensity", 0.0), 0.0),
                    "score": _score_from_mood(record),
                    "context": getattr(record, "context", None),
                }
                for record in timeline_records
            ],
            "snapshots": [
                {
                    "created_at": _iso(getattr(snapshot, "createdAt", None)),
                    "session_id": getattr(snapshot, "sessionId", None),
                    "turn": getattr(snapshot, "turn", None),
                    "emotion": _enum(getattr(snapshot, "emotion", None), "NEUTRAL"),
                    "primary_sub_emotion": getattr(snapshot, "primarySubEmotion", None),
                    "secondary_sub_emotions": _safe_list(getattr(snapshot, "secondarySubEmotions", [])),
                    "detected_symptoms": _safe_list(getattr(snapshot, "detectedSymptoms", [])),
                    "detected_behaviors": _safe_list(getattr(snapshot, "detectedBehaviors", [])),
                    "detected_contexts": _safe_list(getattr(snapshot, "detectedContexts", [])),
                    "intensity": _float(getattr(snapshot, "intensity", 0.0), 0.0),
                    "sentiment": _enum(getattr(snapshot, "sentiment", None), "NEUTRAL"),
                    "phase": _enum(getattr(snapshot, "phase", None), ""),
                    "distortion_type": getattr(snapshot, "distortionType", None),
                }
                for snapshot in window_snapshots
            ],
        },
        "sessions": {
            "recent": [_build_session_detail(session) for session in recent_session_details],
            "score_trajectory": session_score_trajectory,
        },
        "techniques": {
            "total_used": int(getattr(stats, "totalTechniquesUsed", len(ratings)) or 0) if stats else len(ratings),
            "average_rating": _float(getattr(stats, "avgTechniqueRating", 0.0), 0.0) if stats else 0.0,
            "most_used_technique_id": getattr(stats, "mostUsedTechniqueId", None) if stats else None,
            "preferred_categories": preferred_categories,
            "adherence_rate": adherence_rate,
            "mean_effectiveness": technique_effectiveness,
            "ranked": ranked_techniques,
            "ratings": [
                {
                    "used_at": _iso(getattr(rating, "usedAt", None)),
                    "technique_id": getattr(rating, "techniqueId", None),
                    "technique": technique_lookup.get(getattr(rating, "techniqueId", None), {}),
                    "rating": getattr(rating, "rating", None),
                    "completed": getattr(rating, "completed", False),
                    "feedback": getattr(rating, "feedback", None),
                }
                for rating in ratings
            ],
            "outcomes": [
                {
                    "created_at": _iso(getattr(outcome, "createdAt", None)),
                    "session_id": getattr(outcome, "sessionId", None),
                    "technique_id": getattr(outcome, "techniqueId", None),
                    "technique": technique_lookup.get(getattr(outcome, "techniqueId", None), {}),
                    "emotion_before": _enum(getattr(outcome, "emotionBefore", None), "NEUTRAL"),
                    "emotion_after": _enum(getattr(outcome, "emotionAfter", None), ""),
                    "sub_emotion_before": getattr(outcome, "subEmotionBefore", None),
                    "sub_emotion_after": getattr(outcome, "subEmotionAfter", None),
                    "symptoms_before": _safe_list(getattr(outcome, "symptomsBefore", [])),
                    "symptoms_after": _safe_list(getattr(outcome, "symptomsAfter", [])),
                    "behaviors_before": _safe_list(getattr(outcome, "behaviorsBefore", [])),
                    "behaviors_after": _safe_list(getattr(outcome, "behaviorsAfter", [])),
                    "intensity_before": _float(getattr(outcome, "intensityBefore", 0.0), 0.0),
                    "intensity_after": _float(getattr(outcome, "intensityAfter", 0.0), 0.0),
                    "effectiveness": _float(getattr(outcome, "effectiveness", 0.0), 0.0),
                }
                for outcome in outcomes
            ],
        },
        "personalization": {
            "profile": profile,
            "facts": [
                {
                    "category": getattr(fact, "category", None),
                    "fact": getattr(fact, "fact", None),
                    "created_at": _iso(getattr(fact, "createdAt", None)),
                }
                for fact in facts
            ],
            "session_summaries": [
                {
                    "created_at": _iso(getattr(summary, "createdAt", None)),
                    "session_id": getattr(summary, "sessionId", None),
                    "title": getattr(summary, "title", None),
                    "summary": getattr(summary, "summary", None),
                    "emotion": getattr(summary, "emotion", None),
                    "techniques": _safe_list(getattr(summary, "techniques", [])),
                    "outcome": getattr(summary, "outcome", None),
                }
                for summary in summaries
            ],
        },
        "long_term_outcomes": {
            "mood_trend": mood_trend,
            "average_mood_score": average_score,
            "emotional_volatility": mood_volatility,
            "technique_effectiveness": technique_effectiveness,
            "technique_adherence_rate": adherence_rate,
            "resilience_score": profile["resilience_score"],
            "distress_baseline": profile["distress_baseline"],
            "intervention_readiness": round(
                (profile["reflection_depth"] + profile["technique_acceptance_rate"] + max(0.0, 1.0 - profile["distress_baseline"])) / 3,
                3,
            ),
            "session_outcome_stats": session_outcome_stats,
            "improvement_analysis": improvement_analysis,
            "within_session_improvement": within_session_improvement,
            "composite_score": improvement_analysis.get("composite_score", 0.5),
            "crisis_count": crisis_count,
            "recent_crisis_count": recent_crisis_count,
            "high_risk_crisis_count": high_risk_crisis_count,
        },
        "suggestions": suggestions,
        "data_quality": {
            "mood_logs": len(mood_logs),
            "emotion_snapshots": len(snapshots),
            "sessions": len(sessions),
            "ratings": len(ratings),
            "crisis_logs": crisis_count,
            "warnings": [
                warning for warning in [
                    "No mood logs yet" if not mood_logs else None,
                    "No emotion snapshots yet" if not snapshots else None,
                    "Technique personalization needs more feedback" if len(ratings) < 3 else None,
                    f"Elevated safety risk: {high_risk_crisis_count} high-risk crisis events in current window." if high_risk_crisis_count > 0 else None,
                ]
                if warning
            ],
        },
    }
    if user_cache_version(user_id) == cache_version:
        for stale_key in [key for key in _DASHBOARD_CACHE if key[0] == user_id and key != cache_key]:
            _DASHBOARD_CACHE.pop(stale_key, None)
        _DASHBOARD_CACHE[cache_key] = (cache_version, dashboard)
    return dashboard
