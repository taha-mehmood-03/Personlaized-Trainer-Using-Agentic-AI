import pytest
from langchain_core.messages import HumanMessage

from mental_health_wellness.nodes.analysis_and_planning import _derive_exam_sleep_cognitive_context
from mental_health_wellness.nodes.parallel_intake import _gate_calibrated_mood
from mental_health_wellness.nodes.technique_selector_node import select_technique


def test_acceptance_message_preserves_prior_exam_sleep_context():
    state = {
        "messages": [HumanMessage(content="yes plz go for it")],
        "gate_route": "accept_technique",
        "gate_context_flags": ["accept_technique", "technique_acceptance_answer"],
        "last_detected_emotion": "anxiety",
        "last_detected_intensity": 0.42,
        "primary_sub_emotion": "bedtime_rumination",
        "secondary_sub_emotions": ["academic_pressure", "worry"],
        "detected_symptoms": ["sleep_difficulty"],
        "detected_behaviors": ["rumination"],
        "detected_contexts": ["exam_week", "sleep_difficulty", "academic_anxiety"],
    }

    mood = _gate_calibrated_mood(state, "yes plz go for it")

    assert mood["emotion"] == "anxiety"
    assert mood["primary_sub_emotion"] == "bedtime_rumination"
    assert "exam_week" in mood["detected_contexts"]
    assert "sleep_difficulty" in mood["detected_contexts"]


def test_acceptance_context_enrichment_uses_active_thread_not_yes_only():
    updates = _derive_exam_sleep_cognitive_context(
        {
            "messages": [
                HumanMessage(content="I might fail and drop out"),
                HumanMessage(content="it usually shows up when I try to sleep"),
                HumanMessage(content="yes plz go for it"),
            ],
            "active_thread_summary": "Exam failure fear and bedtime rumination.",
            "emotion": "neutral",
            "fused_emotion": "neutral",
        }
    )

    assert updates["fused_emotion"] == "anxiety"
    assert updates["distortion_type"] == "catastrophizing"
    assert "bedtime_rumination" in updates["secondary_sub_emotions"]


@pytest.mark.asyncio
async def test_acceptance_reuses_pending_recommended_technique():
    latest = {"id": "tech-worry", "name": "Worry Time", "category": "CBT"}
    result = await select_technique(
        {
            "messages": [HumanMessage(content="yes plz go for it")],
            "conversation_strategy": "suggest_technique",
            "conversation_stage": "INTERVENTION",
            "needs_technique": True,
            "intent": "accept_technique",
            "gate_route": "accept_technique",
            "gate_context_flags": ["accept_technique", "technique_acceptance_answer"],
            "fused_emotion": "anxiety",
            "fused_intensity": 0.35,
            "exercise_consent": "allowed",
            "solution_preference": "exercise_requested",
            "latest_recommended_technique": latest,
        }
    )

    assert result["recommended_technique"]["name"] == "Worry Time"
    assert result["latest_recommended_technique"]["name"] == "Worry Time"
