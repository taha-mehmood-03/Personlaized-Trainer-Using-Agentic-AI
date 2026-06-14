import sys
from pathlib import Path
from types import SimpleNamespace

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from mental_health_wellness.techniques.emotion_metadata import (
    EMPATHY_FIRST_SUB_EMOTIONS,
    NO_TECHNIQUE_BY_DEFAULT_SUB_EMOTIONS,
    prisma_metadata_fields,
    target_emotions_for_technique,
    technique_emotion_metadata,
)
from mental_health_wellness.tools.technique_tools import (
    _emotion_fit_bonus,
    _is_subemotion_compatible,
)


def _fake_technique(**kwargs):
    defaults = {
        "targetSubEmotions": [],
        "targetSymptoms": [],
        "targetBehaviors": [],
        "avoidSubEmotions": [],
        "avoidSymptoms": [],
        "avoidBehaviors": [],
        "minIntensity": 0.0,
        "maxIntensity": 1.0,
        "bestForContexts": [],
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_panic_maps_to_grounding_not_activating_breathing():
    grounding = technique_emotion_metadata("5-4-3-2-1 Grounding", "Mindfulness", ["ANXIETY"])
    wim_hof = technique_emotion_metadata("Wim Hof Breathing", "Breathing", ["SADNESS", "ANXIETY"])

    assert "panic" in grounding["target_sub_emotions"]
    assert grounding["max_intensity"] >= 0.95
    assert "panic" in wim_hof["avoid_sub_emotions"]
    assert wim_hof["max_intensity"] <= 0.5


def test_target_emotions_are_derived_from_subemotion_profile():
    pursed_lip_targets = target_emotions_for_technique(
        {"name": "Pursed Lip Breathing", "target_emotions": ["anxiety"]},
        "Breathing",
    )
    compassion_targets = target_emotions_for_technique(
        {"name": "Self-Compassion Letter", "target_emotions": ["sadness"]},
        "Journaling",
    )
    sitali_targets = target_emotions_for_technique(
        {"name": "Sitali Breath (Cooling Breath)", "target_emotions": ["ANGER"]},
        "Breathing",
    )

    assert "FEAR" in pursed_lip_targets
    assert "SADNESS" in compassion_targets
    assert "ANGER" in sitali_targets


def test_loneliness_is_empathy_first_but_has_later_social_options():
    social = technique_emotion_metadata("Social Skills Practice", "Behavioral Activation", ["ANXIETY", "SADNESS"])
    metta = technique_emotion_metadata("Metta Phrases for Self", "Mindfulness", ["SADNESS"])

    assert "loneliness" in EMPATHY_FIRST_SUB_EMOTIONS
    assert "loneliness" in social["target_sub_emotions"]
    assert social["pacing_tier"] == "slow"
    assert "loneliness" in metta["target_sub_emotions"]


def test_boredom_and_positive_states_are_conversation_first():
    assert "boredom" in NO_TECHNIQUE_BY_DEFAULT_SUB_EMOTIONS
    assert "gratitude" in NO_TECHNIQUE_BY_DEFAULT_SUB_EMOTIONS
    assert "relief" in NO_TECHNIQUE_BY_DEFAULT_SUB_EMOTIONS


def test_metadata_fields_are_prisma_ready():
    fields = prisma_metadata_fields(
        {
            "name": "Self-Compassion Letter",
            "target_emotions": ["sadness"],
        },
        "Journaling",
    )

    assert fields["targetSubEmotions"]
    assert "targetSymptoms" in fields
    assert "targetBehaviors" in fields
    assert "avoidSymptoms" in fields
    assert "avoidBehaviors" in fields
    assert "shame" in fields["targetSubEmotions"]
    assert 0.0 <= fields["minIntensity"] <= fields["maxIntensity"] <= 1.0
    assert fields["deliveryMode"] == "reflection"


def test_subemotion_scoring_prefers_exact_match_and_rejects_avoidance():
    exact = _fake_technique(
        targetSubEmotions=["panic", "fear"],
        avoidSubEmotions=[],
        minIntensity=0.45,
        maxIntensity=1.0,
    )
    wrong = _fake_technique(
        targetSubEmotions=["low_mood"],
        avoidSubEmotions=["panic"],
        minIntensity=0.0,
        maxIntensity=0.5,
    )

    assert _is_subemotion_compatible(exact, "panic", [], 0.8)
    assert not _is_subemotion_compatible(wrong, "panic", [], 0.8)
    assert _emotion_fit_bonus(exact, "panic", [], 0.8) > _emotion_fit_bonus(wrong, "panic", [], 0.8)


def test_symptom_and_behavior_matching_affects_compatibility_and_score():
    safe_task = _fake_technique(
        targetSubEmotions=["overwhelm"],
        targetBehaviors=["procrastination"],
        targetSymptoms=[],
        avoidSubEmotions=[],
        avoidSymptoms=[],
        avoidBehaviors=[],
        minIntensity=0.1,
        maxIntensity=0.8,
        bestForContexts=["project_deadline"],
    )
    unsafe_breath = _fake_technique(
        targetSubEmotions=["stress"],
        targetSymptoms=[],
        targetBehaviors=[],
        avoidSubEmotions=[],
        avoidSymptoms=["shortness_of_breath"],
        avoidBehaviors=[],
        minIntensity=0.1,
        maxIntensity=0.8,
    )

    assert _is_subemotion_compatible(
        safe_task,
        "overwhelm",
        [],
        detected_behaviors=["procrastination"],
        intensity=0.5,
    )
    assert not _is_subemotion_compatible(
        unsafe_breath,
        "stress",
        [],
        detected_symptoms=["shortness_of_breath"],
        intensity=0.5,
    )
    assert _emotion_fit_bonus(
        safe_task,
        "overwhelm",
        [],
        detected_behaviors=["procrastination"],
        detected_contexts=["project_deadline"],
        intensity=0.5,
    ) > 3.0
