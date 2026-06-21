"""
Clinical Aggregator - rolling PHQ-9/GAD-7 estimate across sessions.

The LLM clinical check evaluates the current turn. This module combines that
current evidence with prior ClinicalAssessmentLog rows so downstream nodes use a
longitudinal screening estimate instead of treating one message as a complete
questionnaire.
"""

from __future__ import annotations

from typing import Any


_SEVERITY_ORDER = {
    "minimal": 0,
    "mild": 1,
    "moderate": 2,
    "moderately_severe": 3,
    "severe": 4,
}

_PHQ_INDICATORS = {
    "anhedonia",
    "depressed_mood",
    "sleep_disturbance",
    "fatigue",
    "appetite_change",
    "worthlessness",
    "concentration",
    "psychomotor",
    "suicidal_ideation",
}

_GAD_INDICATORS = {
    "nervousness",
    "uncontrollable_worry",
    "excessive_worry",
    "restlessness",
    "motor_restlessness",
    "irritability",
    "dread",
}


def _normalize_severity(value: Any) -> str:
    raw = str(value or "minimal").lower()
    raw = raw.split(".")[-1]
    raw = raw.replace("moderately severe", "moderately_severe")
    raw = raw.replace("-", "_")
    return raw if raw in _SEVERITY_ORDER else "minimal"


def _severity_from_scores(phq9: int, gad7: int) -> str:
    phq_sev = (
        "severe" if phq9 >= 20 else
        "moderately_severe" if phq9 >= 15 else
        "moderate" if phq9 >= 10 else
        "mild" if phq9 >= 5 else
        "minimal"
    )
    gad_sev = (
        "severe" if gad7 >= 15 else
        "moderate" if gad7 >= 10 else
        "mild" if gad7 >= 5 else
        "minimal"
    )
    return max((phq_sev, gad_sev), key=lambda sev: _SEVERITY_ORDER[sev])


def _score_floor_from_indicators(indicators: set[str], instrument: str) -> int:
    """
    Conservative minimum score from distinct longitudinal indicators.

    Each known indicator scores 1 ("several days") — the lowest non-zero
    frequency on the PHQ/GAD scale. Using 2 per indicator caused severe
    inflation when many symptoms accumulated across sessions even when the
    user's current message showed little distress.
    """
    if instrument == "phq":
        return min(27, len(indicators & _PHQ_INDICATORS))
    return min(21, len(indicators & _GAD_INDICATORS))


async def aggregate_clinical_assessment(
    *,
    user_id: str,
    current: dict,
    history_limit: int = 12,
    session_start_score: float | None = None,
) -> dict:
    """
    Combine current-turn clinical evidence with recent logs across sessions.

    Returns the same public fields consumed by planner/technique/response nodes:
    severity, phq9_total, gad7_total, clinical_indicators, confidence.
    Extra metadata fields are included for logs/debugging.
    """
    current = current or {}
    current_phq = int(current.get("phq9_total", 0) or 0)
    current_gad = int(current.get("gad7_total", 0) or 0)
    current_conf = float(current.get("confidence", 0.0) or 0.0)
    indicator_union = set(current.get("clinical_indicators", []) or [])

    history = []
    if user_id:
        try:
            from ..db.client import get_prisma_client

            prisma = await get_prisma_client()
            history = await prisma.clinicalassessmentlog.find_many(
                where={"userId": user_id},
                order={"assessedAt": "desc"},
                take=history_limit,
            )
        except Exception as e:
            print(f"[CLINICAL_AGG] History load failed (non-fatal): {str(e)[:100]}")
            history = []

    weighted_phq = current_phq * 1.0
    weighted_gad = current_gad * 1.0
    total_weight = 1.0
    max_severity = _normalize_severity(current.get("severity", "minimal"))
    confidences = [current_conf] if current_conf else []

    for idx, row in enumerate(history):
        # Recent prior assessments matter, but decay quickly so they cannot
        # permanently dominate the current-turn LLM reading.
        weight = 0.75 * (0.85 ** idx)
        phq = int(getattr(row, "phq9Score", 0) or 0)
        gad = int(getattr(row, "gad7Score", 0) or 0)
        sev = _normalize_severity(getattr(row, "severity", "minimal"))
        indicators = set(getattr(row, "indicators", []) or [])
        conf = float(getattr(row, "confidence", 0.0) or 0.0)

        weighted_phq += phq * weight
        weighted_gad += gad * weight
        total_weight += weight
        # Only include indicators from recent history (last 4 logs ≈ 2 sessions)
        # for the floor so the union doesn't grow unboundedly across many months.
        if idx < 4:
            indicator_union.update(indicators)
        confidences.append(conf)

        if _SEVERITY_ORDER[sev] > _SEVERITY_ORDER[max_severity]:
            max_severity = sev

    avg_phq = round(weighted_phq / total_weight) if total_weight else current_phq
    avg_gad = round(weighted_gad / total_weight) if total_weight else current_gad

    # Floor uses only the limited indicator window (not unbounded history).
    phq_floor = _score_floor_from_indicators(indicator_union, "phq")
    gad_floor = _score_floor_from_indicators(indicator_union, "gad")

    # Use the weighted average blended with the floor.
    # Do NOT take max(…, max_phq) — that permanently locked scores at the
    # historical worst-case and prevented any improvement from showing on
    # the dashboard even when the user was genuinely getting better.
    aggregated_phq = min(27, max(avg_phq, phq_floor))
    aggregated_gad = min(21, max(avg_gad, gad_floor))

    score_severity = _severity_from_scores(aggregated_phq, aggregated_gad)
    # Severity uses the higher of score-derived or weighted-history max, but
    # not a permanent lock — max_severity already decays via the weighted avg.
    final_severity = max(
        (score_severity, max_severity),
        key=lambda sev: _SEVERITY_ORDER[sev],
    )

    confidence = max(confidences) if confidences else 0.0
    if history and confidence:
        confidence = min(1.0, confidence + 0.05)

    # Signed delta from session-start so dashboard can show "↓ improving".
    # Negative = improving, positive = worsening, None = first assessment.
    if session_start_score is not None:
        clinical_delta = round(aggregated_phq - session_start_score, 1)
    else:
        clinical_delta = None

    return {
        **current,
        "severity": final_severity,
        "phq9_total": aggregated_phq,
        "gad7_total": aggregated_gad,
        # Expose only current-turn indicators to state/technique nodes;
        # the full union is only used internally for the floor calculation.
        "clinical_indicators": sorted(current.get("clinical_indicators", []) or []),
        "confidence": confidence,
        "clinical_delta": clinical_delta,
        "aggregation_source": "current_plus_history" if history else "current_only",
        "history_count": len(history),
        "current_phq9_total": current_phq,
        "current_gad7_total": current_gad,
        "current_severity": _normalize_severity(current.get("severity", "minimal")),
    }
