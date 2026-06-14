from types import SimpleNamespace

from mental_health_wellness.tools.technique_tools import _contextual_selection_adjustment


def _technique(name: str):
    return SimpleNamespace(name=name)


def test_gratitude_journaling_is_downranked_for_failure_catastrophe():
    kwargs = {
        "primary_sub_emotion": "fear_of_failure",
        "secondary_sub_emotions": ["catastrophizing", "future_threat", "academic_pressure"],
        "detected_symptoms": [],
        "detected_behaviors": ["rumination"],
        "detected_contexts": ["exam_pressure", "academic_risk", "catastrophic_exam_thought"],
        "distortion_type": "catastrophizing",
        "query": "I might fail and drop out",
    }

    gratitude = _contextual_selection_adjustment(_technique("Gratitude Journaling"), **kwargs)
    thought_record = _contextual_selection_adjustment(_technique("Thought Record"), **kwargs)

    assert gratitude < 0
    assert thought_record > gratitude
    assert thought_record > 0
