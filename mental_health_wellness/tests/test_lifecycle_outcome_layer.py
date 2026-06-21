from types import SimpleNamespace

from langchain_core.messages import HumanMessage

from mental_health_wellness.pipeline.emotion_fusion_node import _fusion_metadata
from mental_health_wellness.nodes.optimized_response_generator import (
    _build_optimized_system_prompt,
    _response_includes_technique,
)
from mental_health_wellness.services.dashboard_analytics import _filter_turn_types
from mental_health_wellness.utils.turn_lifecycle import initial_turn_type_guess, refine_turn_type


def test_turn_lifecycle_classifies_initial_reaction_and_followup_disclosure():
    assert initial_turn_type_guess(
        current_message="I feel anxious and I cannot sleep.",
        session_message_count=1,
        gate_route="therapeutic",
    ) == "INITIAL_DISCLOSURE"

    assert initial_turn_type_guess(
        current_message="yes thanks",
        session_message_count=3,
        gate_route="technique_follow_up",
        prior_technique_offered=True,
    ) == "POST_RECOMMENDATION_REACTION"

    refined = refine_turn_type(
        state={
            "turn_type_guess": "CONTEXT_GATHERING",
            "message": "my chest gets tight and I keep thinking I'll fail",
            "fused_emotion": "anxiety",
            "fused_intensity": 0.74,
            "detected_symptoms": ["chest_tightness"],
        },
        previous_context={},
    )
    assert refined == "FOLLOW_UP_DISCLOSURE"


def test_response_marks_only_actual_technique_offers():
    technique = {
        "id": "worry-time",
        "name": "Worry Time",
        "category": "CBT",
    }

    assert _response_includes_technique(
        "Worry Time could help here. Would you like to give it a try?",
        technique,
    )
    assert not _response_includes_technique(
        "I hear how heavy this has been. What part feels hardest tonight?",
        technique,
    )


def test_masking_prompt_guidance_is_uncertain_not_assertive():
    prompt = _build_optimized_system_prompt(
        agent_role="coach",
        emotion="anxiety",
        intensity=0.72,
        technique={},
        crisis_detected=False,
        mismatch=True,
        possible_masking=True,
        fusion_confidence=0.68,
    )

    assert "POSSIBLE EMOTION MISMATCH" in prompt
    assert "Do not assert that the user feels differently" in prompt
    assert "Fusion confidence: 68%" in prompt


def test_dashboard_filters_only_qualifying_turn_types_and_moodlogs():
    records = [
        SimpleNamespace(turnType="INITIAL_DISCLOSURE"),
        SimpleNamespace(turnType="FOLLOW_UP_DISCLOSURE"),
        SimpleNamespace(turnType="POST_RECOMMENDATION"),
        SimpleNamespace(turnType="POST_RECOMMENDATION_REACTION"),
        SimpleNamespace(turnType="CRISIS_DISCLOSURE"),
        SimpleNamespace(turnType="CONTEXT_GATHERING"),
        SimpleNamespace(),  # MoodLog-like records have no turnType and remain eligible.
    ]

    filtered = _filter_turn_types(records)

    assert records[0] in filtered
    assert records[1] in filtered
    assert records[2] in filtered
    assert records[3] in filtered
    assert records[4] in filtered
    assert records[5] not in filtered
    assert records[6] in filtered


def test_fusion_metadata_flags_possible_masking_and_caps_confidence():
    metadata = _fusion_metadata(
        state={
            "messages": [HumanMessage(content="I'm fine")],
            "transcription": "I'm fine",
            "transcription_confidence": 0.61,
            "confidence": 0.9,
            "voice_features": {"emotion": "anxiety", "confidence": 0.82},
        },
        text_emotion="neutral",
        voice_emotion="anxiety",
        fused_emotion="anxiety",
        fused_intensity=0.76,
        voice_confidence=0.82,
        distress_index=0.8,
    )

    assert metadata["mismatch"] is True
    assert metadata["possible_masking"] is True
    assert metadata["fusion_confidence"] == 0.61
    assert metadata["voice_feature_snapshot"]["emotion"] == "anxiety"
