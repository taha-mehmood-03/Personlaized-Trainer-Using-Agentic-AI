from types import SimpleNamespace

from langchain_core.messages import HumanMessage

from mental_health_wellness.nodes.analysis_and_planning import _derive_exam_sleep_cognitive_context
from mental_health_wellness.tools.technique_tools import _contextual_selection_adjustment


def _technique(name: str):
    return SimpleNamespace(name=name)


def test_exam_sleep_context_enrichment_and_rerank_prefers_rumination_tools():
    state = {
        "messages": [
            HumanMessage(
                content="whenever i want to sleep something related to exam goes in my mind because im having exam in the coming week"
            )
        ],
        "emotion": "neutral",
        "fused_emotion": "neutral",
    }

    updates = _derive_exam_sleep_cognitive_context(state)

    assert updates["fused_emotion"] == "anxiety"
    assert "sleep_difficulty" in updates["detected_contexts"]
    assert "exam_week" in updates["detected_contexts"]
    assert "bedtime_rumination" in updates["secondary_sub_emotions"]

    kwargs = {
        "primary_sub_emotion": updates["primary_sub_emotion"],
        "secondary_sub_emotions": updates["secondary_sub_emotions"],
        "detected_symptoms": updates["detected_symptoms"],
        "detected_behaviors": updates["detected_behaviors"],
        "detected_contexts": updates["detected_contexts"],
        "distortion_type": updates.get("distortion_type") or "",
        "query": state["messages"][0].content,
    }

    worry = _contextual_selection_adjustment(_technique("Worry Time"), **kwargs)
    mindfulness = _contextual_selection_adjustment(_technique("Mindfulness of Thoughts"), **kwargs)
    environmental = _contextual_selection_adjustment(_technique("Environmental Design"), **kwargs)
    gratitude = _contextual_selection_adjustment(_technique("Gratitude Journaling"), **kwargs)

    assert max(worry, mindfulness) > 0
    assert environmental < 0
    assert gratitude < 0
