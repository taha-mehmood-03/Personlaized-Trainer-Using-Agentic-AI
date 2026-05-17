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
    Estimate a conservative minimum score from distinct longitudinal indicators.

    Each indicator in ClinicalAssessmentLog represents an item that scored >= 2
    on a previous turn, so counting distinct indicators gives a useful floor
    when symptoms were disclosed across multiple chats instead of one message.
    """
    if instrument == "phq":
        return min(27, len(indicators & _PHQ_INDICATORS) * 2)
    return min(21, len(indicators & _GAD_INDICATORS) * 2)


async def aggregate_clinical_assessment(
    *,
    user_id: str,
    current: dict,
    history_limit: int = 12,
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
    max_phq = current_phq
    max_gad = current_gad
    max_severity = _normalize_severity(current.get("severity", "minimal"))
    confidences = [current_conf] if current_conf else []

    for idx, row in enumerate(history):
        # Recent prior assessments matter, but should not permanently dominate.
        weight = 0.75 * (0.85 ** idx)
        phq = int(getattr(row, "phq9Score", 0) or 0)
        gad = int(getattr(row, "gad7Score", 0) or 0)
        sev = _normalize_severity(getattr(row, "severity", "minimal"))
        indicators = set(getattr(row, "indicators", []) or [])
        conf = float(getattr(row, "confidence", 0.0) or 0.0)

        weighted_phq += phq * weight
        weighted_gad += gad * weight
        total_weight += weight
        max_phq = max(max_phq, phq)
        max_gad = max(max_gad, gad)
        indicator_union.update(indicators)
        confidences.append(conf)

        if _SEVERITY_ORDER[sev] > _SEVERITY_ORDER[max_severity]:
            max_severity = sev

    avg_phq = round(weighted_phq / total_weight) if total_weight else current_phq
    avg_gad = round(weighted_gad / total_weight) if total_weight else current_gad

    phq_floor = _score_floor_from_indicators(indicator_union, "phq")
    gad_floor = _score_floor_from_indicators(indicator_union, "gad")

    aggregated_phq = min(27, max(current_phq, avg_phq, max_phq, phq_floor))
    aggregated_gad = min(21, max(current_gad, avg_gad, max_gad, gad_floor))

    score_severity = _severity_from_scores(aggregated_phq, aggregated_gad)
    final_severity = max(
        (score_severity, max_severity),
        key=lambda sev: _SEVERITY_ORDER[sev],
    )

    confidence = max(confidences) if confidences else 0.0
    if history and confidence:
        confidence = min(1.0, confidence + 0.05)

    return {
        **current,
        "severity": final_severity,
        "phq9_total": aggregated_phq,
        "gad7_total": aggregated_gad,
        "clinical_indicators": sorted(indicator_union),
        "confidence": confidence,
        "aggregation_source": "current_plus_history" if history else "current_only",
        "history_count": len(history),
        "current_phq9_total": current_phq,
        "current_gad7_total": current_gad,
        "current_severity": _normalize_severity(current.get("severity", "minimal")),
    }
