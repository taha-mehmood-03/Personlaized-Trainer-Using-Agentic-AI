from types import SimpleNamespace

from langchain_core.messages import HumanMessage

from mental_health_wellness.nodes.analysis_and_planning import _derive_exam_sleep_cognitive_context
from mental_health_wellness.tools.technique_tools import _contextual_selection_adjustment


def _technique(name: str):
    return SimpleNamespace(name=name)


def test_catastrophic_exam_thought_enriches_distortion_and_prefers_cbt_tools():
    state = {
        "messages": [
            HumanMessage(content="I might fail and drop out"),
            HumanMessage(content="it usually shows up when I try to sleep"),
            HumanMessage(content="yes plz go for it"),
        ],
        "active_thread_summary": "The user fears failing exams and dropping out, especially when trying to sleep.",
        "primary_sub_emotion": "anxiety",
        "detected_contexts": ["exam_pressure"],
        "emotion": "neutral",
        "fused_emotion": "neutral",
    }

    updates = _derive_exam_sleep_cognitive_context(state)

    assert updates["distortion_type"] in {"catastrophizing", "fortune_telling"}
    assert "fear_of_failure" in updates["secondary_sub_emotions"]
    assert "sleep_difficulty" in updates["detected_contexts"]

    kwargs = {
        "primary_sub_emotion": "fear_of_failure",
        "secondary_sub_emotions": updates["secondary_sub_emotions"],
        "detected_symptoms": updates["detected_symptoms"],
        "detected_behaviors": updates["detected_behaviors"],
        "detected_contexts": updates["detected_contexts"],
        "distortion_type": updates["distortion_type"],
        "query": state["active_thread_summary"],
    }

    thought_record = _contextual_selection_adjustment(_technique("Thought Record"), **kwargs)
    restructuring = _contextual_selection_adjustment(_technique("Cognitive Restructuring"), **kwargs)
    gratitude = _contextual_selection_adjustment(_technique("Gratitude Journaling"), **kwargs)
    environmental = _contextual_selection_adjustment(_technique("Environmental Design"), **kwargs)

    assert max(thought_record, restructuring) > 0
    assert gratitude < 0
    assert environmental < 0
