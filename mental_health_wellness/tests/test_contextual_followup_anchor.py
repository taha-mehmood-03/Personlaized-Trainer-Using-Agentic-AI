from langchain_core.messages import AIMessage, HumanMessage
import pytest
from types import SimpleNamespace

from mental_health_wellness.agent.graph import (
    _protect_contextual_followup_gate,
    _remember_session_context,
    _session_context_store,
)
from mental_health_wellness.nodes.emotion_fusion_node import fuse_emotions
from mental_health_wellness.nodes.mood_analyzer_node import _anchor_low_signal_followup
from mental_health_wellness.nodes.parallel_intake import _gate_calibrated_mood
from mental_health_wellness.nodes.session_saver import _technique_delivery_snapshot
from mental_health_wellness.nodes import technique_selector_node
from mental_health_wellness.tools.technique_tools import _contextual_selection_adjustment


def test_pre_graph_gate_corrects_contextual_answer_before_mood_rerun():
    gate = {
        "route": "therapeutic",
        "confidence": 0.86,
        "reasoning": "misread as a fresh emotional disclosure",
        "context_flags": ["new_emotional_disclosure"],
        "intensity_hint": 0.24,
        "needs_full_pipeline": True,
        "run_full_pipeline": True,
        "should_skip_mood_analysis": False,
    }
    previous = [
        HumanMessage(content="im not feeling well"),
        AIMessage(content="Could you tell me more about what has been happening today?"),
    ]
    session_context = {
        "last_detected_emotion": "sadness",
        "last_detected_intensity": 0.87,
        "peak_distress_intensity": 0.87,
        "active_thread_summary": "not feeling well",
        "last_assistant_question": "Could you tell me more about what has been happening today?",
    }

    corrected = _protect_contextual_followup_gate(
        gate,
        "actually i want to enjoy a lil bit but im all alone",
        previous,
        session_context,
    )

    assert corrected["route"] == "contextual_followup"
    assert corrected["should_skip_mood_analysis"] is True
    assert "answering_previous_question" in corrected["context_flags"]
    assert "gate_corrected_contextual_followup" in corrected["context_flags"]
    assert corrected["intensity_hint"] <= 0.35


def test_gate_calibrated_mood_uses_peak_anchor_when_last_emotion_was_polluted():
    mood = _gate_calibrated_mood(
        {
            "gate_route": "contextual_followup",
            "gate_intensity_hint": 0.24,
            "last_detected_emotion": "joy",
            "last_detected_intensity": 0.24,
            "peak_distress_intensity": 0.87,
            "primary_sub_emotion": "desire",
            "active_thread_summary": "not feeling well; user feels all alone",
            "followup_turn_count": 0,
        },
        "actually i want to enjoy a lil bit but im all alone",
    )

    assert mood["emotion"] == "sadness"
    assert mood["sentiment"] == "negative"
    assert mood["primary_sub_emotion"] == "loneliness"
    assert "isolation" in mood["secondary_sub_emotions"]
    assert mood["followup_sub_emotion_enriched"] is True
    assert mood["intensity"] >= 0.73


def test_emotion_fusion_reanchors_low_signal_followup_to_distress_peak():
    fused = fuse_emotions(
        {
            "gate_route": "contextual_followup",
            "gate_intensity_hint": 0.24,
            "emotion": "joy",
            "intensity": 0.24,
            "confidence": 0.43,
            "last_detected_emotion": "joy",
            "last_detected_intensity": 0.24,
            "peak_distress_intensity": 0.87,
            "primary_sub_emotion": "desire",
            "active_thread_summary": "not feeling well; user feels all alone",
            "followup_turn_count": 0,
            "messages": [
                HumanMessage(content="actually i want to enjoy a lil bit but im all alone")
            ],
        }
    )

    assert fused["fused_emotion"] == "sadness"
    assert fused["fused_intensity"] >= 0.73


def test_mood_guard_reanchors_worst_at_night_followup_before_fusion():
    guarded = _anchor_low_signal_followup(
        {
            "gate_route": "contextual_followup",
            "last_detected_emotion": "anxiety",
            "last_detected_intensity": 0.64,
            "peak_distress_intensity": 0.64,
            "active_thread_summary": "loneliness, overthinking, and sleep difficulty",
        },
        "It's worst at night",
        {
            "emotion": "joy",
            "sentiment": "positive",
            "intensity": 0.2,
            "primary_sub_emotion": "joy",
            "secondary_sub_emotions": [],
        },
    )

    assert guarded["emotion"] == "anxiety"
    assert guarded["sentiment"] == "negative"
    assert guarded["primary_sub_emotion"] == "rumination"
    assert guarded["intensity"] >= 0.64


def test_emotion_fusion_reanchors_low_signal_followup_with_thread_floor():
    fused = fuse_emotions(
        {
            "gate_route": "contextual_followup",
            "gate_intensity_hint": 0.18,
            "emotion": "joy",
            "intensity": 0.18,
            "confidence": 0.49,
            "last_detected_emotion": None,
            "last_detected_intensity": 0.0,
            "peak_distress_intensity": 0.0,
            "active_thread_summary": "nighttime overthinking and loneliness",
            "primary_concern": "overthinking at night",
            "followup_turn_count": 1,
            "messages": [
                HumanMessage(content="It's worst at night")
            ],
        }
    )

    assert fused["fused_emotion"] == "anxiety"
    assert fused["fused_intensity"] >= 0.35


def test_gate_calibrated_mood_enriches_social_humiliation_followup():
    mood = _gate_calibrated_mood(
        {
            "gate_route": "contextual_followup",
            "gate_intensity_hint": 0.30,
            "last_detected_emotion": "sadness",
            "last_detected_intensity": 0.70,
            "peak_distress_intensity": 0.70,
            "primary_sub_emotion": "sadness",
            "secondary_sub_emotions": [],
            "active_thread_summary": "not feeling well",
            "followup_turn_count": 0,
        },
        "I was insulted by my principal in front of everyone",
    )

    assert mood["emotion"] == "sadness"
    assert mood["primary_sub_emotion"] == "shame"
    assert "embarrassment" in mood["secondary_sub_emotions"]
    assert "rejection" in mood["secondary_sub_emotions"]
    assert "school_conflict" in mood["detected_contexts"]
    assert mood["followup_sub_emotion_enriched"] is True


def test_session_memory_preserves_disclosure_anchor_on_followup_turn():
    session_id = "anchor_regression_session"
    _session_context_store[session_id] = {
        "last_detected_emotion": "sadness",
        "last_detected_intensity": 0.87,
        "peak_distress_intensity": 0.87,
        "primary_sub_emotion": "sadness",
        "active_thread_summary": "not feeling well",
    }

    _remember_session_context(
        session_id,
        {
            "gate_route": "contextual_followup",
            "fused_emotion": "joy",
            "fused_intensity": 0.24,
            "primary_sub_emotion": "desire",
            "secondary_sub_emotions": ["optimism"],
            "detected_symptoms": [],
            "detected_behaviors": [],
            "detected_contexts": [],
            "emotion_scores": {"joy": 0.43},
            "intent": "contextual_followup",
            "response_task": "ask_next_context_question",
            "final_response": "That loneliness matters. What feels most in the way?",
        },
    )

    stored = _session_context_store[session_id]
    assert stored["last_detected_emotion"] == "sadness"
    assert stored["last_detected_intensity"] == 0.87
    assert stored["peak_distress_intensity"] == 0.87
    assert stored["primary_sub_emotion"] == "sadness"


def test_session_memory_allows_enriched_followup_subemotion_without_overwriting_anchor():
    session_id = "anchor_enriched_followup_session"
    _session_context_store[session_id] = {
        "last_detected_emotion": "sadness",
        "last_detected_intensity": 0.87,
        "peak_distress_intensity": 0.87,
        "primary_sub_emotion": "sadness",
        "secondary_sub_emotions": [],
        "active_thread_summary": "not feeling well",
    }

    _remember_session_context(
        session_id,
        {
            "gate_route": "contextual_followup",
            "fused_emotion": "sadness",
            "fused_intensity": 0.74,
            "primary_sub_emotion": "loneliness",
            "secondary_sub_emotions": ["sadness", "isolation"],
            "detected_symptoms": [],
            "detected_behaviors": ["isolation"],
            "detected_contexts": [],
            "emotion_scores": {"sadness": 0.8},
            "followup_sub_emotion_enriched": True,
            "intent": "contextual_followup",
            "response_task": "ask_next_context_question",
            "final_response": "That loneliness sounds heavy. When does it hit hardest?",
        },
    )

    stored = _session_context_store[session_id]
    assert stored["last_detected_emotion"] == "sadness"
    assert stored["last_detected_intensity"] == 0.87
    assert stored["peak_distress_intensity"] == 0.87
    assert stored["primary_sub_emotion"] == "loneliness"
    assert "isolation" in stored["secondary_sub_emotions"]
    assert "isolation" in stored["detected_behaviors"]


def test_hedge_does_not_halve_gate_confirmed_disclosure():
    fused = fuse_emotions(
        {
            "gate_route": "therapeutic",
            "gate_context_flags": ["emotional_disclosure"],
            "emotion": "sadness",
            "intensity": 0.75,
            "confidence": 0.72,
            "primary_sub_emotion": "sadness",
            "messages": [HumanMessage(content="my day was not that much good")],
        }
    )

    assert fused["fused_emotion"] == "sadness"
    assert fused["fused_intensity"] == 0.75


def test_low_confidence_ambiguous_turn_does_not_create_anchor():
    session_id = "anchor_low_conf_ambiguous_session"
    _session_context_store[session_id] = {}

    _remember_session_context(
        session_id,
        {
            "gate_route": "technique_request",
            "gate_context_flags": [],
            "confidence": 0.32,
            "fused_emotion": "neutral",
            "fused_intensity": 0.30,
            "messages": [HumanMessage(content="hi not great")],
        },
    )

    stored = _session_context_store[session_id]
    assert "last_detected_intensity" not in stored
    assert "peak_distress_intensity" not in stored


def test_low_confidence_new_disclosure_without_anchor_gets_conservative_floor():
    session_id = "anchor_low_conf_new_disclosure_session"
    _session_context_store[session_id] = {}

    _remember_session_context(
        session_id,
        {
            "gate_route": "therapeutic",
            "gate_context_flags": ["new_emotional_disclosure"],
            "confidence": 0.34,
            "fused_emotion": "sadness",
            "fused_intensity": 0.41,
            "messages": [HumanMessage(content="i was insulted by my principal")],
        },
    )

    stored = _session_context_store[session_id]
    assert stored["last_detected_emotion"] == "sadness"
    assert stored["last_detected_intensity"] == 0.50
    assert stored["peak_distress_intensity"] == 0.50


def test_low_confidence_read_with_existing_anchor_holds_anchor():
    session_id = "anchor_low_conf_existing_session"
    _session_context_store[session_id] = {
        "last_detected_emotion": "sadness",
        "last_detected_intensity": 0.75,
        "peak_distress_intensity": 0.75,
    }

    _remember_session_context(
        session_id,
        {
            "gate_route": "therapeutic",
            "gate_context_flags": ["new_emotional_disclosure"],
            "confidence": 0.34,
            "fused_emotion": "sadness",
            "fused_intensity": 0.41,
            "messages": [HumanMessage(content="yes actually i was insulted by my principal")],
        },
    )

    stored = _session_context_store[session_id]
    assert stored["last_detected_emotion"] == "sadness"
    assert stored["last_detected_intensity"] == 0.75
    assert stored["peak_distress_intensity"] == 0.75


@pytest.mark.asyncio
async def test_short_consent_technique_selection_uses_anchor_floor_and_emotion(monkeypatch, capsys):
    captured = {}

    async def fake_recommend(payload):
        captured.update(payload)
        return [
            {
                "id": "self_compassion_letter",
                "name": "Self-Compassion Letter",
                "category": "CBT",
            }
        ]

    monkeypatch.setattr(
        technique_selector_node,
        "recommend_technique",
        SimpleNamespace(ainvoke=fake_recommend),
    )

    result = await technique_selector_node.select_technique(
        {
            "conversation_strategy": "suggest_technique",
            "technique_readiness": 1.0,
            "conversation_stage": "INTERVENTION",
            "needs_technique": True,
            "intent": "accept_technique",
            "gate_route": "technique_request",
            "gate_context_flags": ["accept_technique"],
            "response_task": "offer_one_technique",
            "fused_emotion": "neutral",
            "fused_intensity": 0.20,
            "primary_sub_emotion": "neutral",
            "last_detected_emotion": "sadness",
            "last_detected_intensity": 0.75,
            "peak_distress_intensity": 0.75,
            "active_thread_summary": "user was insulted by the principal",
            "messages": [HumanMessage(content="yes share it with me")],
            "user_id": "anchor_selection_test",
        }
    )

    out = capsys.readouterr().out
    assert "intensity=20% elevated_to_anchor=75% for tier selection" in out
    assert captured["emotion"] == "sadness"
    assert captured["intensity"] == 0.75
    assert result["technique_selection_emotion"] == "sadness"
    assert result["technique_selection_intensity"] == 0.75


def test_technique_delivery_snapshot_uses_selection_baseline_not_consent_turn():
    snapshot = _technique_delivery_snapshot(
        {
            "conversation_strategy": "suggest_technique",
            "fused_emotion": "neutral",
            "fused_intensity": 0.20,
            "technique_selection_emotion": "sadness",
            "technique_selection_intensity": 0.75,
        }
    )

    assert snapshot["technique_delivery_emotion"] == "sadness"
    assert snapshot["technique_delivery_intensity"] == 0.75


class _Technique:
    def __init__(self, name: str):
        self.name = name


def test_social_humiliation_context_boosts_self_compassion_over_environmental_design():
    kwargs = {
        "primary_sub_emotion": "shame",
        "secondary_sub_emotions": ["embarrassment", "rejection"],
        "detected_contexts": ["school_conflict"],
        "query": "user was insulted by the principal during game period",
    }

    self_compassion = _contextual_selection_adjustment(_Technique("Self-Compassion Letter"), **kwargs)
    thought_record = _contextual_selection_adjustment(_Technique("Thought Record"), **kwargs)
    environmental = _contextual_selection_adjustment(_Technique("Environmental Design"), **kwargs)

    assert self_compassion > thought_record > 0
    assert environmental < 0
    assert self_compassion > environmental + 4.0
