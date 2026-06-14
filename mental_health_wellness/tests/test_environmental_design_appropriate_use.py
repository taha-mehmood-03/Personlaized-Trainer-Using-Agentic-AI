from types import SimpleNamespace

from mental_health_wellness.tools.technique_tools import _contextual_selection_adjustment


def _technique(name: str):
    return SimpleNamespace(name=name)


def test_environmental_design_allowed_for_phone_and_sleep_environment():
    adjustment = _contextual_selection_adjustment(
        _technique("Environmental Design"),
        primary_sub_emotion="stress",
        secondary_sub_emotions=[],
        detected_symptoms=["sleep_difficulty"],
        detected_behaviors=[],
        detected_contexts=["sleep_environment", "phone_distraction", "study_space_distraction"],
        distortion_type="",
        query="I study on my bed and my phone keeps distracting me when I try to sleep.",
    )

    assert adjustment > 0


def test_environmental_design_downranked_for_exam_rumination_without_environment_trigger():
    adjustment = _contextual_selection_adjustment(
        _technique("Environmental Design"),
        primary_sub_emotion="bedtime_rumination",
        secondary_sub_emotions=["academic_pressure", "worry"],
        detected_symptoms=["sleep_difficulty"],
        detected_behaviors=["rumination"],
        detected_contexts=["exam_week", "sleep_difficulty", "academic_anxiety"],
        distortion_type="",
        query="Exam thoughts keep coming when I try to sleep.",
    )

    assert adjustment < 0
