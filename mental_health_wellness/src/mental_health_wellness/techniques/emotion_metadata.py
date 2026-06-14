"""
Technique emotion metadata v2 for SentiMind / Personalized Trainer.

Purpose:
- Provide safer, cleaner technique matching.
- Keep backward compatibility with older fields:
  target_sub_emotions, avoid_sub_emotions, min_intensity, max_intensity,
  pacing_tier, delivery_mode, best_for_contexts.
- Add cleaner internal fields:
  target_symptoms, target_behaviors, avoid_symptoms, avoid_behaviors.
- Add aliases for duplicate technique names.
- Add safety gates for advanced breathing techniques.

IMPORTANT:
This metadata is a recommendation/ranking aid, not a clinical decision system.
Crisis handling must remain outside this file.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Iterable, Any


# =============================================================================
# CORE ENUMS / NORMALIZATION
# =============================================================================

CORE_EMOTION_ENUMS = {
    "ANGER",
    "DISGUST",
    "FEAR",
    "JOY",
    "NEUTRAL",
    "SADNESS",
    "SURPRISE",
    "ANXIETY",
}


def _norm(value: Any) -> str:
    """Normalize labels to snake_case lowercase."""
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _unique(values: Iterable[str] | None) -> list[str]:
    """Normalize + deduplicate while preserving order."""
    cleaned: list[str] = []
    for value in values or []:
        item = _norm(value)
        if item and item not in cleaned:
            cleaned.append(item)
    return cleaned


def _clean_subs(values: Iterable[str] | None) -> list[str]:
    return _unique(values)


def _clean_contexts(values: Iterable[str] | None) -> list[str]:
    return _unique(values)


def _clean_core_emotions(values: Iterable[str] | None) -> list[str]:
    cleaned: list[str] = []
    for value in values or []:
        core = str(value or "").strip().upper()
        if core in CORE_EMOTION_ENUMS and core not in cleaned:
            cleaned.append(core)
    return cleaned


# =============================================================================
# TAXONOMY
# =============================================================================

# Emotional tone / sub-emotional states.
SUB_EMOTION_TO_CORE = {
    # anxiety / fear spectrum
    "anxiety": "ANXIETY",
    "worry": "ANXIETY",
    "nervousness": "ANXIETY",
    "performance_anxiety": "ANXIETY",
    "social_anxiety": "ANXIETY",
    "anticipatory_anxiety": "ANXIETY",
    "racing_thoughts": "ANXIETY",
    "obsessive_thoughts": "ANXIETY",
    "rumination": "ANXIETY",
    "catastrophising": "ANXIETY",
    "catastrophizing": "ANXIETY",
    "fear_of_failure": "ANXIETY",
    "academic_pressure": "ANXIETY",
    "bedtime_rumination": "ANXIETY",
    "future_threat": "ANXIETY",
    "fortune_telling": "ANXIETY",
    "indecision": "ANXIETY",
    "ambivalence": "ANXIETY",
    "confusion": "ANXIETY",
    "stress": "ANXIETY",
    "overwhelm": "ANXIETY",
    "restlessness": "ANXIETY",
    "tension": "ANXIETY",
    "panic": "FEAR",
    "panic_now": "FEAR",
    "fear": "FEAR",
    "distress": "FEAR",
    "high_anxiety": "ANXIETY",

    # sadness / low mood spectrum
    "sadness": "SADNESS",
    "low_mood": "SADNESS",
    "grief": "SADNESS",
    "loneliness": "SADNESS",
    "isolation": "SADNESS",
    "emptiness": "SADNESS",
    "hopelessness": "SADNESS",
    "disappointment": "SADNESS",
    "rejection": "SADNESS",
    "insecurity": "SADNESS",
    "inadequacy": "SADNESS",
    "anhedonia": "SADNESS",
    "fatigue": "SADNESS",
    "burnout": "SADNESS",
    "numbness": "SADNESS",
    "dissociation": "SADNESS",
    "depersonalization": "SADNESS",
    "unresolved_feelings": "SADNESS",
    "regret": "SADNESS",
    "remorse": "SADNESS",
    "meaninglessness": "SADNESS",
    "low_expectancy": "SADNESS",

    # anger spectrum
    "anger": "ANGER",
    "rage": "ANGER",
    "frustration": "ANGER",
    "irritability": "ANGER",
    "resentment": "ANGER",
    "bitterness": "ANGER",
    "feeling_disrespected": "ANGER",
    "betrayal": "ANGER",
    "anger_at_self": "ANGER",

    # shame/guilt spectrum
    "shame": "SADNESS",
    "guilt": "SADNESS",
    "self_blame": "SADNESS",
    "self_criticism": "SADNESS",
    "embarrassment": "SADNESS",
    "people_pleasing": "ANXIETY",

    # behavior/urge-adjacent emotional signals
    "impulsivity": "ANGER",
    "urge": "ANGER",
    "avoidance": "ANXIETY",
    "procrastination": "ANXIETY",
    "boredom": "NEUTRAL",
    "creative_block": "NEUTRAL",
    "mood_swings": "ANXIETY",
    "vulnerability": "ANXIETY",
    "awkwardness": "ANXIETY",
    "distraction": "NEUTRAL",
    "compassion_fatigue": "SADNESS",
    "depression": "SADNESS",
    "jealousy": "ANGER",

    # positive / neutral
    "joy": "JOY",
    "relief": "JOY",
    "calm": "NEUTRAL",
    "neutral": "NEUTRAL",
}

_CORE_TO_SUBS = {
    "ANXIETY": [
    "anxiety", "worry", "nervousness", "performance_anxiety",
        "social_anxiety", "racing_thoughts", "rumination", "bedtime_rumination",
        "stress", "overwhelm", "fear_of_failure", "academic_pressure",
        "future_threat", "catastrophizing", "fortune_telling",
        "tension", "restlessness", "indecision", "procrastination",
    ],
    "SADNESS": [
        "sadness", "low_mood", "grief", "loneliness", "hopelessness",
        "emptiness", "fatigue", "burnout", "self_criticism",
        "shame", "guilt", "rejection", "depression",
    ],
    "ANGER": [
        "anger", "frustration", "irritability", "resentment",
        "feeling_disrespected", "rage", "impulsivity", "jealousy",
    ],
    "FEAR": [
        "fear", "panic", "panic_now", "distress", "high_anxiety",
    ],
    "NEUTRAL": ["neutral", "boredom", "confusion"],
    "JOY": ["joy", "relief", "calm"],
}

CANONICAL_SUB_EMOTIONS = frozenset(SUB_EMOTION_TO_CORE.keys())

# States where the safest first response is human warmth, validation, and
# context-gathering. Techniques can still be offered later when the planner has
# a clear action signal or the user asks for one.
EMPATHY_FIRST_SUB_EMOTIONS = frozenset({
    "loneliness", "isolation", "grief", "shame", "guilt", "self_blame",
    "self_criticism", "rejection", "insecurity", "inadequacy",
    "embarrassment", "disappointment", "regret", "remorse",
    "unresolved_feelings", "emptiness", "hopelessness", "numbness",
    "meaninglessness",
})

# Low-signal or positive states should not cause an exercise just because the
# conversation has enough context. These require an explicit request/action cue.
NO_TECHNIQUE_BY_DEFAULT_SUB_EMOTIONS = frozenset({
    "neutral", "calm", "joy", "relief", "boredom", "curiosity",
    "confusion", "gratitude", "approval", "admiration", "amusement",
    "excitement", "pride", "optimism", "realization",
})

# Signals that are not pure emotions, but should still influence matching.
SYMPTOM_TAGS = {
    "sleep_issues", "hyperventilation", "shortness_of_breath", "chest_pain",
    "sleep_difficulty", "sleep_disruption", "bedtime_racing_thoughts",
    "racing_thoughts", "fatigue", "numbness",
    "dizziness", "respiratory_distress", "body_tension", "physical_fatigue",
    "attention_difficulty", "decision_fatigue", "mental_fog",
    "trauma_activation", "body_focused_anxiety", "health_anxiety",
    "seizure_history", "cardiac_condition", "respiratory_condition",
    "high_blood_pressure", "pregnancy",
}

BEHAVIOR_TAGS = {
    "avoidance", "procrastination", "isolation", "people_pleasing", "rumination",
    "emotional_eating", "stress_eating", "impulsivity", "resistance_to_change",
    "low_energy_activation", "task_initiation", "task_starting",
    "social_re_engagement", "connection_practice",
}

# Practical contexts used by your agent and FYP use cases.
PROJECT_STUDY_CONTEXTS = {
    "exam_preparation", "pre_exam_anxiety", "study_planning",
    "study_stress", "before_studying", "math_anxiety", "exam_week",
    "exam_pressure", "academic_anxiety", "academic_pressure", "academic_risk",
    "bedtime_rumination", "sleep_difficulty", "sleep_disruption",
    "nighttime_worry", "fear_of_failure", "future_threat",
    "catastrophic_exam_thought", "specific_exam_failure_belief",
    "sleep_environment", "phone_distraction", "study_space_distraction",
    "project_deadline", "final_year_project", "backend_architecture",
    "technical_complexity", "coding_task_start", "database_integration",
    "demo_anxiety", "presentation_anxiety", "pre_presentation",
    "supervisor_evaluation_fear", "family_conflict", "work_stress",
    "relationship_conflict", "social_isolation",
}


# =============================================================================
# DEFAULTS / ALIASES / SAFETY
# =============================================================================

_CATEGORY_DEFAULTS = {
    "Breathing": {
        "target_sub_emotions": ["stress", "nervousness", "tension", "worry"],
        "avoid_sub_emotions": ["boredom"],
        "target_symptoms": [],
        "target_behaviors": [],
        "avoid_symptoms": [],
        "avoid_behaviors": [],
        "min_intensity": 0.2,
        "max_intensity": 0.8,
        "pacing_tier": "normal",
        "delivery_mode": "breathing",
        "best_for_contexts": ["general_settling", "nervous_system_regulation"],
    },
    "Mindfulness": {
        "target_sub_emotions": ["stress", "overwhelm", "rumination", "worry"],
        "avoid_sub_emotions": ["panic_now"],
        "target_symptoms": [],
        "target_behaviors": [],
        "avoid_symptoms": [],
        "avoid_behaviors": [],
        "min_intensity": 0.15,
        "max_intensity": 0.8,
        "pacing_tier": "normal",
        "delivery_mode": "mindfulness",
        "best_for_contexts": ["present_moment_awareness", "attention_training"],
    },
    "CBT": {
        "target_sub_emotions": ["worry", "self_criticism", "rumination", "anxiety"],
        "avoid_sub_emotions": ["panic_now"],
        "target_symptoms": [],
        "target_behaviors": [],
        "avoid_symptoms": [],
        "avoid_behaviors": [],
        "min_intensity": 0.25,
        "max_intensity": 0.8,
        "pacing_tier": "normal",
        "delivery_mode": "cognitive_skill",
        "best_for_contexts": ["specific_negative_thought", "belief_challenge"],
    },
    "DBT": {
        "target_sub_emotions": ["overwhelm", "anger", "distress", "impulsivity"],
        "avoid_sub_emotions": [],
        "target_symptoms": [],
        "target_behaviors": [],
        "avoid_symptoms": [],
        "avoid_behaviors": [],
        "min_intensity": 0.3,
        "max_intensity": 1.0,
        "pacing_tier": "normal",
        "delivery_mode": "regulation_skill",
        "best_for_contexts": ["emotion_regulation", "distress_tolerance"],
    },
    "Journaling": {
        "target_sub_emotions": ["rumination", "sadness", "confusion", "self_criticism"],
        "avoid_sub_emotions": ["panic_now", "high_anxiety"],
        "target_symptoms": [],
        "target_behaviors": [],
        "avoid_symptoms": [],
        "avoid_behaviors": [],
        "min_intensity": 0.1,
        "max_intensity": 0.75,
        "pacing_tier": "slow",
        "delivery_mode": "reflection",
        "best_for_contexts": ["emotional_reflection", "thought_unloading"],
    },
    "Behavioral Activation": {
        "target_sub_emotions": ["low_mood", "avoidance", "procrastination", "fatigue"],
        "avoid_sub_emotions": ["panic_now"],
        "target_symptoms": [],
        "target_behaviors": ["avoidance", "procrastination"],
        "avoid_symptoms": [],
        "avoid_behaviors": [],
        "min_intensity": 0.15,
        "max_intensity": 0.8,
        "pacing_tier": "normal",
        "delivery_mode": "behavioral_action",
        "best_for_contexts": ["task_starting", "momentum_building"],
    },
    # fallback
    "": {
        "target_sub_emotions": ["stress", "worry", "overwhelm"],
        "avoid_sub_emotions": [],
        "target_symptoms": [],
        "target_behaviors": [],
        "avoid_symptoms": [],
        "avoid_behaviors": [],
        "min_intensity": 0.0,
        "max_intensity": 1.0,
        "pacing_tier": "normal",
        "delivery_mode": "exercise",
        "best_for_contexts": [],
    },
}

# Canonical aliases to reduce duplicates during lookup.
TECHNIQUE_ALIASES = {
    "STOP Practice": "STOP Skill",
    "Behavioral Experiments": "Behavioral Experiment",
    "Opposite Action Practice": "Opposite Action",
    "Pleasant Activity Scheduling": "Activity Scheduling",
}

ADVANCED_BREATHING_TECHNIQUES = {
    "Wim Hof Breathing",
    "Bellows Breath (Kapalabhati)",
    "Breath of Fire",
    "Retention Breathing (Kumbhaka)",
}

ADVANCED_BREATHING_AVOID_SUBS = {
    "panic", "panic_now", "fear", "high_anxiety", "anger", "rage",
    "hyperventilation", "tension", "overwhelm",
}

ADVANCED_BREATHING_AVOID_SYMPTOMS = {
    "shortness_of_breath", "chest_pain", "dizziness",
    "respiratory_condition", "cardiac_condition",
    "high_blood_pressure", "pregnancy", "seizure_history",
}

WEAK_CONTEXT_RENAMES = {
    "left_right_hemisphere_balance": "mental_balance",
    "military_calm": "performance_calm",
    "therapist_technique": "guided_reflection",
    "kundalini_practice": "advanced_energizing_practice",
}


# =============================================================================
# METADATA FACTORY
# =============================================================================

def _split_signals(values: Iterable[str] | None) -> tuple[list[str], list[str], list[str]]:
    """
    Split a mixed list into:
    - sub-emotions
    - symptoms
    - behaviors

    Backward compatibility:
    Unknown values remain in sub-emotions so older ranking does not break.
    """
    emotions: list[str] = []
    symptoms: list[str] = []
    behaviors: list[str] = []

    for raw in _unique(values):
        item = WEAK_CONTEXT_RENAMES.get(raw, raw)

        if item in SYMPTOM_TAGS:
            symptoms.append(item)
        elif item in BEHAVIOR_TAGS:
            behaviors.append(item)
        else:
            emotions.append(item)

    return _unique(emotions), _unique(symptoms), _unique(behaviors)


def _m(
    target_sub_emotions: Iterable[str] | None = None,
    *,
    avoid: Iterable[str] | None = None,
    avoid_sub_emotions: Iterable[str] | None = None,
    target_symptoms: Iterable[str] | None = None,
    target_behaviors: Iterable[str] | None = None,
    avoid_symptoms: Iterable[str] | None = None,
    avoid_behaviors: Iterable[str] | None = None,
    min_i: float = 0.0,
    max_i: float = 1.0,
    pacing: str = "normal",
    mode: str = "exercise",
    contexts: Iterable[str] | None = None,
    target_emotions: Iterable[str] | None = None,
) -> dict:
    """
    Metadata constructor.

    Supports your old call style:
        _m(["worry", "stress"], avoid=[...], min_i=..., max_i=..., contexts=[...])

    Also supports cleaner new fields:
        target_symptoms=[...], target_behaviors=[...], avoid_symptoms=[...]
    """
    sub_emotions, symptoms_from_targets, behaviors_from_targets = _split_signals(target_sub_emotions)

    avoid_combined = list(avoid or []) + list(avoid_sub_emotions or [])
    avoid_emotions, symptoms_from_avoid, behaviors_from_avoid = _split_signals(avoid_combined)

    context_values = [
        WEAK_CONTEXT_RENAMES.get(_norm(c), _norm(c))
        for c in (contexts or [])
    ]

    return {
        "target_sub_emotions": _unique(sub_emotions),
        "target_symptoms": _unique(list(target_symptoms or []) + symptoms_from_targets),
        "target_behaviors": _unique(list(target_behaviors or []) + behaviors_from_targets),
        "avoid_sub_emotions": _unique(avoid_emotions),
        "avoid_symptoms": _unique(list(avoid_symptoms or []) + symptoms_from_avoid),
        "avoid_behaviors": _unique(list(avoid_behaviors or []) + behaviors_from_avoid),
        "min_intensity": float(min_i),
        "max_intensity": float(max_i),
        "pacing_tier": str(pacing or "normal"),
        "delivery_mode": str(mode or "exercise"),
        "best_for_contexts": _unique(context_values),
        "target_emotions": _clean_core_emotions(target_emotions or []),
    }




TECHNIQUE_EMOTION_METADATA = {

    # ══════════════════════════════════════════════════════════════════════════
    # BASE BREATHING
    # ══════════════════════════════════════════════════════════════════════════

    "4-7-8 Breathing": _m(
        ["worry", "nervousness", "stress", "racing_thoughts", "tension",
         "sleep_issues", "restlessness", "overwhelm", "performance_anxiety"],
        avoid=["boredom", "high_anxiety", "hyperventilation"],
        min_i=0.3, max_i=0.9,
        contexts=["sleep_onset", "pre_exam_anxiety", "bedtime_wind_down",
                  "acute_worry", "nervous_system_settling"],
    ),

    "Box Breathing": _m(
        ["performance_anxiety", "panic", "nervousness", "stress", "overwhelm",
         "tension", "racing_thoughts", "irritability", "anger", "fear",
         "high_anxiety", "restlessness"],
        avoid=["boredom", "hyperventilation"],
        min_i=0.35, max_i=0.95,
        contexts=["acute_pressure", "presentation_anxiety", "pre_performance",
                  "military_calm", "emotion_regulation_reset"],
    ),

    "Belly Breathing": _m(
        ["tension", "stress", "overwhelm", "irritability", "nervousness",
         "anger", "fatigue", "sadness", "low_mood", "worry", "fear",
         "dissociation", "numbness"],
        avoid=["boredom"],
        min_i=0.2, max_i=0.85,
        contexts=["body_tension", "general_settling", "anger_cool_down",
                  "somatic_grounding", "beginner_breathing"],
    ),

    "Alternate Nostril Breathing": _m(
        ["racing_thoughts", "stress", "worry", "overwhelm", "low_mood",
         "mood_swings", "irritability", "indecision", "ambivalence",
         "restlessness", "tension", "burnout"],
        avoid=["panic", "hyperventilation", "high_anxiety"],
        min_i=0.2, max_i=0.75,
        contexts=["mental_balance", "pre_meditation", "left_right_hemisphere_balance",
                  "emotional_regulation", "sustained_stress"],
    ),

    "Resonance Breathing": _m(
        ["stress", "tension", "worry", "burnout", "anxiety", "low_mood",
         "irritability", "mood_swings", "fatigue", "restlessness",
         "performance_anxiety", "social_anxiety"],
        avoid=["panic", "hyperventilation"],
        min_i=0.25, max_i=0.8,
        contexts=["sustained_stress", "heart_rate_variability_training",
                  "chronic_anxiety", "burnout_recovery", "nervous_system_regulation"],
    ),

    "Pursed Lip Breathing": _m(
        ["panic", "fear", "tension", "nervousness", "hyperventilation",
         "high_anxiety", "overwhelm", "stress", "distress"],
        avoid=["boredom", "fatigue"],
        min_i=0.45, max_i=1.0,
        contexts=["shortness_of_breath", "panic_body_alarm", "hyperventilation_rescue",
                  "respiratory_distress", "acute_fear"],
    ),

    "Breath Counting": _m(
        ["rumination", "racing_thoughts", "worry", "sadness", "stress",
         "restlessness", "low_mood", "overwhelm", "indecision", "nervousness",
         "tension", "boredom"],
        avoid=["panic", "high_anxiety"],
        min_i=0.15, max_i=0.7,
        contexts=["mind_wandering", "attention_training", "meditation_entry",
                  "gentle_focus", "mild_anxiety_relief"],
    ),

    "3-Part Breath": _m(
        ["tension", "stress", "overwhelm", "nervousness", "fatigue",
         "numbness", "dissociation", "low_mood", "sadness", "anger",
         "irritability", "restlessness"],
        avoid=["panic", "hyperventilation"],
        min_i=0.2, max_i=0.8,
        contexts=["body_awareness", "somatic_grounding", "yoga_integration",
                  "breath_retraining", "tension_release"],
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # BASE MINDFULNESS
    # ══════════════════════════════════════════════════════════════════════════

    "5-4-3-2-1 Grounding": _m(
        ["panic", "fear", "overwhelm", "dissociation", "racing_thoughts",
         "stress", "high_anxiety", "distress", "numbness", "depersonalization",
         "panic_now", "tension", "anger", "impulsivity"],
        avoid=["boredom"],
        min_i=0.4, max_i=1.0,
        contexts=["present_moment_grounding", "dissociation_rescue",
                  "panic_interrupt", "trauma_flashback_grounding",
                  "acute_overwhelm"],
    ),

    "Body Scan Meditation": _m(
        ["tension", "stress", "burnout", "sadness", "fatigue", "numbness",
         "dissociation", "low_mood", "anxiety", "anger", "overwhelm",
         "restlessness", "worry", "grief", "emptiness", "anhedonia"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.8,
        contexts=["somatic_awareness", "sleep_preparation", "chronic_tension",
                  "body_reconnection", "burnout_recovery", "trauma_informed_grounding"],
    ),

    "Mindful Walking": _m(
        ["restlessness", "low_mood", "stress", "overwhelm", "fatigue",
         "anger", "irritability", "rumination", "avoidance", "procrastination",
         "tension", "anhedonia", "sadness", "loneliness", "anxiety"],
        avoid=["panic", "panic_now"],
        min_i=0.15, max_i=0.75,
        contexts=["movement_needed", "nature_therapy", "rumination_break",
                  "anger_discharge", "mood_lift", "low_energy_activation"],
    ),

    "RAIN Meditation": _m(
        ["shame", "sadness", "anger", "overwhelm", "self_criticism", "grief",
         "guilt", "loneliness", "fear", "rejection", "insecurity",
         "disappointment", "resentment", "regret", "emptiness", "self_blame",
         "embarrassment", "hopelessness", "remorse"],
        avoid=["panic", "panic_now", "high_anxiety"],
        min_i=0.25, max_i=0.85,
        pacing="slow",
        contexts=["difficult_emotion_processing", "self_compassion_deepening",
                  "shame_healing", "grief_processing", "inner_critic_work",
                  "self_blame_release"],
    ),

    "Mindful Eating": _m(
        ["stress", "overwhelm", "numbness", "emptiness", "low_mood",
         "anxiety", "tension", "loneliness", "sadness", "boredom"],
        avoid=["panic", "panic_now", "high_anxiety"],
        min_i=0.15, max_i=0.6,
        contexts=["sensory_slowing", "emotional_eating", "body_reconnection",
                  "stress_eating", "present_moment_pleasure"],
    ),

    "Loving-Kindness Meditation": _m(
        ["loneliness", "rejection", "shame", "insecurity", "anger", "resentment",
         "guilt", "self_blame", "isolation", "self_criticism", "inadequacy",
         "grief", "sadness", "fear", "hopelessness", "embarrassment",
         "disappointment", "people_pleasing", "low_mood"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.8,
        pacing="slow",
        contexts=["self_compassion", "connection", "anger_softening",
                  "shame_healing", "loneliness_relief", "relationship_repair",
                  "inner_critic_softening"],
    ),

    "STOP Practice": _m(
        ["impulsivity", "anger", "frustration", "panic", "overwhelm",
         "irritability", "stress", "feeling_disrespected", "resentment",
         "racing_thoughts", "tension", "high_anxiety"],
        avoid=[],
        min_i=0.4, max_i=1.0,
        contexts=["pause_before_reacting", "impulse_control", "anger_interrupt",
                  "conflict_de_escalation", "stress_pause"],
    ),

    "Mindfulness of Thoughts": _m(
        ["rumination", "racing_thoughts", "worry", "self_criticism",
         "anxiety", "obsessive_thoughts", "indecision", "confusion",
         "overwhelm", "stress", "low_mood", "fear", "bedtime_rumination",
         "academic_pressure", "future_threat"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.75,
        contexts=["defusion", "thought_observation", "cognitive_defusion",
                  "rumination_interrupt", "metacognitive_awareness",
                  "bedtime_rumination", "sleep_difficulty", "nighttime_worry",
                  "academic_anxiety", "exam_week"],
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # BASE CBT
    # ══════════════════════════════════════════════════════════════════════════

    "Thought Record": _m(
        ["worry", "rumination", "self_criticism", "performance_anxiety",
         "insecurity", "anxiety", "sadness", "low_mood", "anger",
         "frustration", "guilt", "shame", "hopelessness", "fear",
         "social_anxiety", "resentment", "rejection", "grief",
         "fear_of_failure", "catastrophizing", "fortune_telling",
         "future_threat", "academic_pressure"],
        avoid=["panic", "panic_now"],
        min_i=0.25, max_i=0.8,
        mode="cognitive_skill",
        contexts=["thought_challenge", "cognitive_restructuring_entry",
                  "mood_episode_analysis", "distortion_identification",
                  "grief_processing", "specific_negative_thought",
                  "specific_exam_failure_belief", "catastrophic_exam_thought",
                  "academic_anxiety", "exam_pressure", "academic_risk"],
    ),

    "Cognitive Restructuring": _m(
        ["worry", "self_criticism", "hopelessness", "insecurity",
         "performance_anxiety", "social_anxiety", "anxiety", "sadness",
         "anger", "guilt", "shame", "low_mood", "fear", "resentment",
         "disappointment", "grief", "rejection", "frustration",
         "fear_of_failure", "catastrophizing", "fortune_telling",
         "future_threat", "academic_pressure"],
        avoid=["panic", "panic_now"],
        min_i=0.25, max_i=0.8,
        mode="cognitive_skill",
        contexts=["belief_reframe", "negative_automatic_thought_work",
                  "catastrophising_correction", "grief_narrative_reframe",
                  "anger_reappraisal", "catastrophic_exam_thought",
                  "specific_exam_failure_belief", "academic_anxiety",
                  "exam_pressure", "academic_risk"],
    ),

    "Behavioral Experiment": _m(
        ["avoidance", "worry", "social_anxiety", "performance_anxiety",
         "insecurity", "fear", "hopelessness", "low_expectancy", "shame",
         "rejection", "low_mood", "procrastination"],
        avoid=["panic", "panic_now"],
        min_i=0.3, max_i=0.8,
        mode="behavioral_action",
        contexts=["testing_predictions", "exposure_entry", "fear_disconfirmation",
                  "avoidance_breaking", "social_fear_testing"],
    ),

    "Worry Time": _m(
        ["worry", "racing_thoughts", "rumination", "stress", "anxiety",
         "performance_anxiety", "social_anxiety", "overwhelm", "indecision",
         "procrastination", "tension", "bedtime_rumination",
         "academic_pressure", "future_threat"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.75,
        mode="cognitive_skill",
        contexts=["scheduled_worry", "worry_containment", "rumination_time_boxing",
                  "anxiety_management", "intrusive_thought_reduction",
                  "bedtime_rumination", "nighttime_worry", "sleep_difficulty",
                  "exam_week", "exam_pressure", "academic_anxiety"],
    ),

    "Pie Chart Technique": _m(
        ["guilt", "self_blame", "self_criticism", "shame", "resentment",
         "regret", "remorse", "disappointment", "inadequacy", "hopelessness"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.7,
        mode="cognitive_skill",
        contexts=["responsibility_rebalancing", "guilt_reduction",
                  "blame_attribution_correction", "shame_contextualising"],
    ),

    "Cost-Benefit Analysis": _m(
        ["ambivalence", "indecision", "avoidance", "procrastination",
         "fear", "worry", "resentment", "anger", "hopelessness",
         "overwhelm", "impulsivity"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.7,
        mode="cognitive_skill",
        contexts=["decision_clarity", "change_motivation", "ambivalence_resolution",
                  "avoidance_cost_mapping", "urge_evaluation"],
    ),

    "Activity Scheduling": _m(
        ["low_mood", "anhedonia", "avoidance", "fatigue", "hopelessness",
         "emptiness", "procrastination", "isolation", "loneliness",
         "burnout", "boredom", "sadness"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.75,
        mode="behavioral_action",
        pacing="slow",
        contexts=["behavioral_activation", "depression_management",
                  "pleasure_restoration", "routine_rebuilding",
                  "avoidance_reduction"],
    ),

    "The Triple Column Technique": _m(
        ["self_criticism", "worry", "rumination", "inadequacy", "shame",
         "guilt", "insecurity", "self_blame", "hopelessness", "anger",
         "frustration", "resentment"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.75,
        mode="cognitive_skill",
        contexts=["distortion_labeling", "automatic_thought_work",
                  "inner_critic_restructuring", "cognitive_diary"],
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # BASE DBT
    # ══════════════════════════════════════════════════════════════════════════

    "TIPP Skills": _m(
        ["panic", "anger", "impulsivity", "overwhelm", "fear", "distress",
         "rage", "high_anxiety", "panic_now", "tension", "shame",
         "feeling_disrespected", "dissociation"],
        avoid=[],
        min_i=0.6, max_i=1.0,
        contexts=["high_arousal_reset", "crisis_stabilisation",
                  "emotion_dysregulation_peak", "rage_interrupt",
                  "acute_distress"],
    ),

    "Check the Facts": _m(
        ["anger", "fear", "worry", "resentment", "feeling_disrespected",
         "jealousy", "shame", "guilt", "anxiety", "frustration",
         "sadness", "disappointment", "rejection"],
        avoid=["panic", "panic_now"],
        min_i=0.3, max_i=0.85,
        mode="regulation_skill",
        contexts=["emotion_fact_check", "anger_validation",
                  "emotion_accuracy_assessment", "threat_appraisal_check"],
    ),

    "Opposite Action": _m(
        ["avoidance", "anger", "shame", "sadness", "fear", "guilt",
         "loneliness", "rejection", "hopelessness", "anxiety", "isolation",
         "self_criticism", "embarrassment", "low_mood"],
        avoid=["panic", "panic_now"],
        min_i=0.3, max_i=0.85,
        mode="behavioral_action",
        contexts=["emotion_urge_reversal", "fear_exposure", "shame_action",
                  "loneliness_outreach", "guilt_repair", "avoidance_breaking"],
    ),

    "Radical Acceptance": _m(
        ["grief", "disappointment", "resentment", "unresolved_feelings",
         "hopelessness", "shame", "guilt", "loneliness", "anger", "regret",
         "remorse", "sadness", "frustration", "fear", "emptiness",
         "rejection", "betrayal", "bitterness"],
        avoid=["panic", "panic_now"],
        min_i=0.3, max_i=0.9,
        pacing="slow",
        mode="acceptance_skill",
        contexts=["unchangeable_situation", "grief_acceptance",
                  "resentment_release", "chronic_pain_acceptance",
                  "loss_integration", "trauma_processing"],
    ),

    "STOP Skill": _m(
        ["anger", "impulsivity", "panic", "overwhelm", "irritability",
         "rage", "frustration", "feeling_disrespected", "distress",
         "high_anxiety", "resentment"],
        avoid=[],
        min_i=0.4, max_i=1.0,
        mode="regulation_skill",
        contexts=["pause_before_action", "impulse_interrupt",
                  "anger_management", "crisis_deceleration"],
    ),

    "IMPROVE the Moment": _m(
        ["overwhelm", "hopelessness", "sadness", "stress", "distress",
         "loneliness", "emptiness", "grief", "anxiety", "low_mood",
         "boredom", "tension", "anger", "fear"],
        avoid=[],
        min_i=0.4, max_i=0.95,
        mode="regulation_skill",
        contexts=["distress_tolerance", "crisis_endurance",
                  "meaning_in_pain", "self_soothing", "acute_distress_management"],
    ),

    "Pros and Cons": _m(
        ["impulsivity", "ambivalence", "indecision", "avoidance",
         "anger", "resentment", "hopelessness", "worry", "fear", "shame"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.75,
        mode="regulation_skill",
        contexts=["urge_decision", "crisis_behaviour_evaluation",
                  "change_decision", "self_harm_urge_evaluation"],
    ),

    "Wise Mind": _m(
        ["confusion", "ambivalence", "anger", "worry", "overwhelm",
         "impulsivity", "indecision", "anxiety", "resentment",
         "shame", "guilt", "fear", "hopelessness"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.8,
        mode="regulation_skill",
        contexts=["balanced_decision", "emotion_reason_integration",
                  "values_clarification", "conflict_resolution",
                  "self_trust_building"],
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # BASE JOURNALING
    # ══════════════════════════════════════════════════════════════════════════

    "Gratitude Journaling": _m(
        ["low_mood", "disappointment", "stress", "emptiness", "loneliness",
         "sadness", "hopelessness", "burnout", "boredom", "anhedonia",
         "resentment", "frustration"],
        avoid=["panic", "panic_now", "grief", "shame", "high_anxiety"],
        min_i=0.15, max_i=0.55,
        pacing="slow",
        mode="reflection",
        contexts=["savoring_positive", "mood_lift", "negativity_bias_correction",
                  "resilience_building", "wellbeing_maintenance"],
    ),

    "Stream of Consciousness": _m(
        ["rumination", "confusion", "stress", "overwhelm", "anxiety",
         "anger", "frustration", "sadness", "grief", "emptiness",
         "racing_thoughts", "creative_block", "tension", "indecision",
         "loneliness", "resentment"],
        avoid=["panic", "panic_now"],
        min_i=0.15, max_i=0.7,
        pacing="slow",
        mode="reflection",
        contexts=["mental_unloading", "emotional_purge", "creative_unblocking",
                  "anger_discharge", "grief_expression"],
    ),

    "Cognitive Distortion Journal": _m(
        ["self_criticism", "worry", "rumination", "insecurity", "shame",
         "guilt", "hopelessness", "low_mood", "anxiety", "anger",
         "inadequacy", "rejection", "fear"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.75,
        mode="cognitive_skill",
        contexts=["thought_patterns", "distortion_awareness",
                  "cognitive_monitoring", "automatic_thought_tracking"],
    ),

    "Self-Compassion Letter": _m(
        ["shame", "guilt", "self_criticism", "inadequacy", "rejection",
         "self_blame", "embarrassment", "loneliness", "sadness", "grief",
         "regret", "remorse", "hopelessness", "low_mood", "isolation",
         "disappointment", "fear", "insecurity"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.8,
        pacing="slow",
        mode="reflection",
        contexts=["self_kindness", "shame_healing", "inner_critic_softening",
                  "grief_self_care", "failure_recovery"],
    ),

    "One-Sentence Journal": _m(
        ["low_mood", "fatigue", "emptiness", "anhedonia", "overwhelm",
         "burnout", "hopelessness", "numbness", "procrastination",
         "avoidance", "isolation"],
        avoid=["panic", "panic_now"],
        min_i=0.1, max_i=0.6,
        pacing="slow",
        mode="reflection",
        contexts=["low_energy_reflection", "depression_micro_engagement",
                  "journaling_entry_point", "energy_conserving_reflection"],
    ),

    "Emotion Tracking": _m(
        ["confusion", "mood_swings", "stress", "worry", "anxiety",
         "irritability", "sadness", "low_mood", "overwhelm", "burnout",
         "anger", "frustration", "tension", "numbness"],
        avoid=["panic", "panic_now"],
        min_i=0.1, max_i=0.65,
        mode="reflection",
        contexts=["pattern_tracking", "mood_pattern_data", "trigger_identification",
                  "emotional_self_awareness", "menstrual_cycle_tracking",
                  "therapy_preparation"],
    ),

    "Unsent Letter": _m(
        ["anger", "grief", "unresolved_feelings", "resentment", "rejection",
         "sadness", "shame", "guilt", "disappointment", "betrayal",
         "loneliness", "regret", "frustration", "hopelessness"],
        avoid=["panic", "panic_now"],
        min_i=0.25, max_i=0.85,
        pacing="slow",
        mode="reflection",
        contexts=["emotional_expression", "grief_processing", "anger_discharge",
                  "closure_seeking", "relationship_processing",
                  "unfinished_business"],
    ),

    "Morning Pages": _m(
        ["rumination", "creative_block", "worry", "stress", "anxiety",
         "low_mood", "confusion", "overwhelm", "sadness", "anger",
         "frustration", "procrastination", "indecision", "tension"],
        avoid=["panic", "panic_now"],
        min_i=0.1, max_i=0.65,
        pacing="slow",
        mode="reflection",
        contexts=["daily_unloading", "creative_unblocking", "morning_ritual",
                  "anxiety_clearing", "intention_setting"],
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # BASE BEHAVIORAL ACTIVATION
    # ══════════════════════════════════════════════════════════════════════════

    "Pleasant Activity Scheduling": _m(
        ["low_mood", "anhedonia", "fatigue", "hopelessness", "emptiness",
         "loneliness", "isolation", "boredom", "sadness", "burnout",
         "procrastination", "avoidance"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.75,
        pacing="slow",
        mode="behavioral_action",
        contexts=["increase_reward", "depression_activation", "pleasure_restoration",
                  "social_re_engagement", "routine_enrichment"],
    ),

    "Micro-Activities": _m(
        ["overwhelm", "avoidance", "fatigue", "procrastination", "low_mood",
         "hopelessness", "emptiness", "anhedonia", "burnout", "anxiety",
         "depression", "indecision", "self_criticism"],
        avoid=[],
        min_i=0.2, max_i=0.85,
        mode="behavioral_action",
        contexts=["tiny_action", "activation_entry_point",
                  "overwhelm_reduction", "task_initiation",
                  "momentum_building"],
    ),

    "Activity-Mood Monitoring": _m(
        ["low_mood", "anhedonia", "confusion", "stress", "burnout",
         "fatigue", "mood_swings", "anxiety", "frustration", "emptiness",
         "sadness", "boredom"],
        avoid=["panic", "panic_now"],
        min_i=0.1, max_i=0.65,
        mode="reflection",
        contexts=["mood_pattern_data", "activity_reward_tracking",
                  "behavioural_analysis", "therapy_monitoring"],
    ),

    "Values-Based Action": _m(
        ["emptiness", "hopelessness", "low_mood", "avoidance", "grief",
         "meaninglessness", "anhedonia", "burnout", "loneliness",
         "isolation", "regret", "shame", "guilt", "procrastination",
         "low_expectancy"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.9,
        pacing="slow",
        mode="behavioral_action",
        contexts=["meaning_and_values", "grief_meaning_making",
                  "identity_rebuilding", "post_loss_activation",
                  "ACT_committed_action"],
    ),

    "Behavioral Experiments": _m(
        ["avoidance", "worry", "social_anxiety", "low_expectancy", "fear",
         "insecurity", "shame", "hopelessness", "rejection", "performance_anxiety",
         "procrastination"],
        avoid=["panic", "panic_now"],
        min_i=0.25, max_i=0.8,
        mode="behavioral_action",
        contexts=["test_avoidance_belief", "exposure_entry",
                  "prediction_testing", "social_fear_disconfirmation"],
    ),

    "Energy Management": _m(
        ["burnout", "fatigue", "overwhelm", "low_mood", "stress",
         "anhedonia", "tension", "procrastination", "avoidance",
         "mood_swings", "irritability"],
        avoid=["panic", "panic_now"],
        min_i=0.15, max_i=0.75,
        mode="behavioral_action",
        contexts=["energy_matching", "burnout_recovery", "pacing",
                  "sustainable_productivity", "chronic_fatigue_management"],
    ),

    "Anti-Procrastination List": _m(
        ["procrastination", "avoidance", "overwhelm", "worry", "anxiety",
         "low_mood", "shame", "guilt", "self_criticism", "hopelessness",
         "indecision", "fatigue"],
        avoid=["panic", "panic_now"],
        min_i=0.15, max_i=0.75,
        mode="behavioral_action",
        contexts=["task_starting", "overwhelm_chunking",
                  "avoidance_interruption", "productivity_entry"],
    ),

    "Routine Building": _m(
        ["low_mood", "anhedonia", "fatigue", "stress", "anxiety",
         "hopelessness", "emptiness", "burnout", "procrastination",
         "confusion", "mood_swings", "isolation"],
        avoid=["panic", "panic_now"],
        min_i=0.15, max_i=0.7,
        pacing="slow",
        mode="behavioral_action",
        contexts=["daily_structure", "depression_management",
                  "recovery_structure", "stability_building",
                  "anxiety_reduction_through_predictability"],
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # ADVANCED BREATHING
    # ══════════════════════════════════════════════════════════════════════════

    "Wim Hof Breathing": _m(
        ["fatigue", "burnout", "low_mood", "numbness", "restlessness"],
        avoid=["panic", "panic_now", "fear", "high_anxiety", "anger",
               "hyperventilation", "tension"],
        min_i=0.1, max_i=0.55,
        pacing="advanced",
        contexts=["energizing_low_arousal", "cold_resilience_training",
                  "physical_energy_boost", "numbness_activation"],
    ),

    "Buteyko Breathing": _m(
        ["panic", "hyperventilation", "anxiety", "sleep_issues", "stress",
         "nervousness", "tension", "racing_thoughts", "fear", "overwhelm"],
        avoid=["boredom", "fatigue"],
        min_i=0.3, max_i=0.9,
        contexts=["overbreathing", "chronic_anxiety", "sleep_apnea_support",
                  "breath_volume_reduction", "panic_prevention"],
    ),

    "Sitali Breath (Cooling Breath)": _m(
        ["anger", "frustration", "irritability", "feeling_disrespected",
         "resentment", "tension", "overwhelm", "stress", "impulsivity",
         "high_anxiety"],
        avoid=["fatigue", "low_mood", "anhedonia"],
        min_i=0.3, max_i=0.9,
        contexts=["heated_emotion", "anger_cooling", "frustration_relief",
                  "hot_mood_regulation", "conflict_de_escalation"],
    ),

    "Ocean Breath (Ujjayi)": _m(
        ["stress", "nervousness", "racing_thoughts", "tension", "anxiety",
         "overwhelm", "restlessness", "low_mood", "sadness", "fatigue",
         "anger", "worry"],
        avoid=["panic", "hyperventilation"],
        min_i=0.2, max_i=0.75,
        contexts=["steady_focus", "yoga_integration", "sustained_calm",
                  "moving_meditation", "energy_channeling"],
    ),

    "Bellows Breath (Kapalabhati)": _m(
        ["fatigue", "low_mood", "anhedonia", "burnout", "numbness",
         "procrastination", "emptiness"],
        avoid=["panic", "panic_now", "high_anxiety", "anger", "hyperventilation",
               "fear", "tension"],
        min_i=0.05, max_i=0.5,
        pacing="advanced",
        contexts=["energizing", "morning_activation", "physical_fatigue_lift",
                  "low_arousal_reset"],
    ),

    "Breath of Fire": _m(
        ["fatigue", "anhedonia", "low_mood", "burnout", "numbness",
         "emptiness", "procrastination"],
        avoid=["panic", "panic_now", "high_anxiety", "anger", "hyperventilation",
               "fear", "tension"],
        min_i=0.05, max_i=0.5,
        pacing="advanced",
        contexts=["energizing", "kundalini_practice", "low_energy_activation",
                  "internal_heat_generation"],
    ),

    "Extended Exhale Breathing": _m(
        ["panic", "worry", "stress", "tension", "overwhelm", "anger",
         "irritability", "fear", "racing_thoughts", "high_anxiety",
         "nervousness", "restlessness"],
        avoid=["boredom", "fatigue", "low_mood"],
        min_i=0.3, max_i=0.95,
        contexts=["downregulation", "parasympathetic_activation",
                  "sleep_onset", "anger_de_escalation",
                  "panic_interrupt", "nervous_system_reset"],
    ),

    "Sama Vritti (Equal Breathing)": _m(
        ["stress", "worry", "nervousness", "restlessness", "anxiety",
         "tension", "racing_thoughts", "overwhelm", "mood_swings",
         "irritability", "indecision"],
        avoid=["panic", "hyperventilation"],
        min_i=0.2, max_i=0.7,
        contexts=["balance", "nervous_system_regulation",
                  "meditation_preparation", "emotional_steadiness"],
    ),

    "Left Nostril Breathing": _m(
        ["anger", "irritability", "frustration", "stress", "feeling_disrespected",
         "resentment", "tension", "overwhelm", "high_anxiety", "impulsivity"],
        avoid=["fatigue", "low_mood", "anhedonia"],
        min_i=0.25, max_i=0.85,
        contexts=["cooling", "anger_softening", "overstimulation_relief",
                  "right_hemisphere_activation"],
    ),

    "Retention Breathing (Kumbhaka)": _m(
        ["stress", "restlessness", "nervousness", "tension", "anxiety",
         "low_mood", "procrastination"],
        avoid=["panic", "panic_now", "fear", "hyperventilation", "high_anxiety"],
        min_i=0.15, max_i=0.65,
        pacing="advanced",
        contexts=["capacity_training", "breath_mastery",
                  "advanced_pranayama", "focus_building"],
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # ADVANCED MINDFULNESS
    # ══════════════════════════════════════════════════════════════════════════

    "Choiceless Awareness": _m(
        ["rumination", "worry", "restlessness", "anxiety", "confusion",
         "overwhelm", "sadness", "tension", "low_mood", "racing_thoughts",
         "indecision", "anger", "grief"],
        avoid=["panic", "panic_now"],
        min_i=0.15, max_i=0.7,
        pacing="advanced",
        contexts=["open_awareness", "advanced_meditation",
                  "non_striving_practice", "present_moment_receptivity"],
    ),

    "Tonglen Meditation": _m(
        ["grief", "loneliness", "sadness", "shame", "guilt", "rejection",
         "isolation", "emptiness", "compassion_fatigue", "hopelessness",
         "resentment", "anger"],
        avoid=["panic", "panic_now", "high_anxiety"],
        min_i=0.2, max_i=0.8,
        pacing="slow",
        contexts=["compassion_for_suffering", "grief_transformation",
                  "loneliness_relief", "compassion_fatigue_recovery",
                  "anger_into_compassion"],
    ),

    "Sound Meditation": _m(
        ["racing_thoughts", "stress", "restlessness", "overwhelm", "anxiety",
         "tension", "low_mood", "sadness", "loneliness", "anger",
         "frustration", "numbness"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.8,
        contexts=["auditory_anchor", "thought_interruption",
                  "sensory_grounding", "beginner_meditation",
                  "accessible_mindfulness"],
    ),

    "Heartfulness Meditation": _m(
        ["loneliness", "sadness", "grief", "emptiness", "rejection",
         "shame", "guilt", "isolation", "hopelessness", "low_mood",
         "fear", "insecurity", "self_criticism"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.75,
        pacing="slow",
        contexts=["heart_connection", "emotional_warmth",
                  "self_compassion", "loneliness_relief",
                  "grief_healing"],
    ),

    "Mantra Meditation": _m(
        ["racing_thoughts", "worry", "stress", "overwhelm", "anxiety",
         "rumination", "fear", "sadness", "anger", "low_mood",
         "restlessness", "tension", "grief"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.8,
        contexts=["attention_anchor", "thought_interruption",
                  "stress_relief", "spiritual_practice",
                  "repetitive_thought_reduction"],
    ),

    "Mountain Meditation": _m(
        ["fear", "worry", "anger", "overwhelm", "anxiety", "sadness",
         "grief", "hopelessness", "shame", "low_mood", "restlessness",
         "insecurity", "rejection"],
        avoid=["panic", "panic_now"],
        min_i=0.25, max_i=0.85,
        contexts=["stability", "groundedness", "resilience_building",
                  "emotional_solidity", "adversity_anchoring"],
    ),

    "Anchor and Release": _m(
        ["sadness", "grief", "rumination", "rejection", "resentment",
         "shame", "guilt", "loneliness", "regret", "anger", "disappointment",
         "unresolved_feelings", "emptiness"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.8,
        pacing="slow",
        contexts=["letting_go", "grief_release", "resentment_release",
                  "emotional_completion", "acceptance_support"],
    ),

    "Mindful Listening to Music": _m(
        ["sadness", "loneliness", "emptiness", "fatigue", "grief",
         "low_mood", "anhedonia", "numbness", "anger", "stress",
         "isolation", "hopelessness", "boredom"],
        avoid=["panic", "panic_now"],
        min_i=0.1, max_i=0.7,
        pacing="slow",
        contexts=["gentle_soothing", "emotional_processing_through_music",
                  "mood_lift", "grief_companionship",
                  "low_energy_engagement"],
    ),

    "Three-Minute Breathing Space": _m(
        ["stress", "overwhelm", "worry", "racing_thoughts", "anxiety",
         "tension", "anger", "frustration", "sadness", "low_mood",
         "rumination", "irritability"],
        avoid=[],
        min_i=0.2, max_i=0.85,
        contexts=["quick_reset", "work_break", "micro_mindfulness",
                  "transition_pause", "stress_interrupt"],
    ),

    "Metta Phrases for Self": _m(
        ["shame", "loneliness", "insecurity", "rejection", "self_criticism",
         "guilt", "self_blame", "sadness", "grief", "hopelessness",
         "embarrassment", "inadequacy", "isolation", "anger", "resentment",
         "fear", "low_mood"],
        avoid=["panic", "panic_now"],
        min_i=0.15, max_i=0.8,
        pacing="slow",
        contexts=["self_compassion", "shame_healing", "self_forgiveness",
                  "inner_critic_softening", "loneliness_self_care"],
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # ADVANCED CBT
    # ══════════════════════════════════════════════════════════════════════════

    "Socratic Questioning": _m(
        ["worry", "self_criticism", "insecurity", "rumination", "hopelessness",
         "anger", "resentment", "shame", "guilt", "low_mood", "anxiety",
         "confusion", "fear", "procrastination"],
        avoid=["panic", "panic_now"],
        min_i=0.25, max_i=0.8,
        mode="cognitive_skill",
        contexts=["guided_inquiry", "belief_examination",
                  "automatic_thought_challenge", "perspective_broadening",
                  "therapist_technique"],
    ),

    "Positive Data Log": _m(
        ["self_criticism", "inadequacy", "insecurity", "low_mood",
         "shame", "embarrassment", "rejection", "self_blame",
         "hopelessness", "anxiety", "fear"],
        avoid=["panic", "panic_now", "grief"],
        min_i=0.15, max_i=0.7,
        mode="cognitive_skill",
        contexts=["evidence_for_strength", "self_belief_building",
                  "counter_negative_schema", "confidence_building"],
    ),

    "Advantage-Disadvantage Analysis": _m(
        ["avoidance", "ambivalence", "worry", "indecision", "fear",
         "procrastination", "hopelessness", "anger", "resentment",
         "anxiety", "impulsivity"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.7,
        mode="cognitive_skill",
        contexts=["decision_patterns", "behaviour_change_motivation",
                  "avoidance_analysis", "pros_cons_deep_dive"],
    ),

    "Double Standard Technique": _m(
        ["shame", "guilt", "self_criticism", "inadequacy", "self_blame",
         "embarrassment", "rejection", "hopelessness", "regret", "remorse",
         "loneliness", "insecurity"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.75,
        mode="cognitive_skill",
        contexts=["compassionate_reframe", "self_compassion_entry",
                  "inner_critic_confrontation", "fairness_check"],
    ),

    "Problem-Solving Worksheet": _m(
        ["overwhelm", "stress", "worry", "indecision", "frustration",
         "resentment", "anger", "anxiety", "hopelessness", "avoidance",
         "procrastination", "low_mood"],
        avoid=["panic", "panic_now"],
        min_i=0.25, max_i=0.8,
        mode="cognitive_skill",
        contexts=["practical_problem_solving", "obstacle_mapping",
                  "solution_generation", "frustration_redirect",
                  "structured_decision_making"],
    ),

    "Advantages of the Symptom": _m(
        ["avoidance", "ambivalence", "procrastination", "self_criticism",
         "resistance_to_change", "anger", "fear", "indecision",
         "hopelessness", "shame"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.7,
        mode="cognitive_skill",
        contexts=["protective_function", "secondary_gain_exploration",
                  "ambivalence_clarification", "resistance_exploration"],
    ),

    "Rational Responding Cards": _m(
        ["worry", "panic", "racing_thoughts", "self_criticism", "anxiety",
         "fear", "hopelessness", "shame", "anger", "performance_anxiety",
         "social_anxiety", "low_mood"],
        avoid=[],
        min_i=0.3, max_i=0.9,
        mode="cognitive_skill",
        contexts=["portable_coping_statement", "on_the_go_reframe",
                  "in_vivo_support", "pre_exposure_preparation"],
    ),

    "Externalization of Voices": _m(
        ["self_criticism", "shame", "inadequacy", "hopelessness",
         "self_blame", "guilt", "insecurity", "low_mood", "rejection",
         "anger_at_self", "emptiness"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.8,
        mode="cognitive_skill",
        contexts=["separate_from_inner_critic", "self_compassion_entry",
                  "inner_critic_externalising", "shame_reduction"],
    ),

    "Best Friend Technique": _m(
        ["shame", "guilt", "self_criticism", "inadequacy", "sadness",
         "self_blame", "rejection", "hopelessness", "loneliness",
         "embarrassment", "low_mood", "insecurity", "regret"],
        avoid=["panic", "panic_now"],
        min_i=0.15, max_i=0.75,
        mode="cognitive_skill",
        contexts=["friendly_perspective", "self_compassion_entry",
                  "compassionate_self_talk", "inner_critic_softening"],
    ),

    "Probability Overestimation": _m(
        ["worry", "performance_anxiety", "social_anxiety", "panic", "fear",
         "anxiety", "stress", "hopelessness", "avoidance", "low_expectancy",
         "catastrophising"],
        avoid=[],
        min_i=0.25, max_i=0.85,
        mode="cognitive_skill",
        contexts=["catastrophe_probability", "threat_overestimation_correction",
                  "anxiety_reality_testing", "fear_prediction_check"],
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # ADVANCED DBT
    # ══════════════════════════════════════════════════════════════════════════

    "DEAR MAN": _m(
        ["social_anxiety", "anger", "feeling_disrespected", "insecurity",
         "fear", "shame", "guilt", "people_pleasing", "rejection",
         "resentment", "loneliness", "frustration"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.8,
        mode="communication_skill",
        contexts=["assertive_request", "boundary_setting",
                  "needs_expression", "conflict_navigation",
                  "interpersonal_effectiveness"],
    ),

    "FAST": _m(
        ["shame", "guilt", "insecurity", "people_pleasing",
         "feeling_disrespected", "resentment", "rejection", "anger",
         "self_criticism", "hopelessness", "inadequacy"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.8,
        mode="communication_skill",
        contexts=["self_respect", "values_in_relationships",
                  "boundary_holding", "people_pleasing_interruption",
                  "self_integrity_maintenance"],
    ),

    "GIVE": _m(
        ["loneliness", "rejection", "social_anxiety", "insecurity",
         "anger", "resentment", "isolation", "shame", "fear",
         "people_pleasing", "guilt", "frustration"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.75,
        mode="communication_skill",
        contexts=["relationship_effectiveness", "conflict_de_escalation",
                  "connection_deepening", "repair_attempt",
                  "validation_practice"],
    ),

    "ABC PLEASE": _m(
        ["stress", "burnout", "mood_swings", "low_mood", "anxiety",
         "irritability", "fatigue", "overwhelm", "anger", "tension",
         "anhedonia", "hopelessness", "vulnerability"],
        avoid=["panic", "panic_now"],
        min_i=0.15, max_i=0.7,
        mode="regulation_skill",
        contexts=["vulnerability_reduction", "emotion_regulation_foundation",
                  "physical_self_care", "mood_stability",
                  "burnout_prevention"],
    ),

    "Emotion Surfing": _m(
        ["anger", "frustration", "impulsivity", "overwhelm", "shame",
         "fear", "panic", "resentment", "grief", "sadness", "anxiety",
         "distress", "urge"],
        avoid=[],
        min_i=0.35, max_i=0.95,
        mode="regulation_skill",
        contexts=["urge_wave", "craving_surfing", "emotion_riding",
                  "impulse_tolerance", "distress_non_reactivity"],
    ),

    "Cope Ahead Plan": _m(
        ["performance_anxiety", "worry", "social_anxiety", "stress",
         "fear", "avoidance", "procrastination", "anxiety", "shame",
         "anticipatory_anxiety", "low_expectancy"],
        avoid=["panic", "panic_now", "high_anxiety"],
        min_i=0.2, max_i=0.8,
        mode="regulation_skill",
        contexts=["future_stressor", "anticipatory_anxiety",
                  "pre_event_preparation", "rehearsal_coping",
                  "exposure_preparation"],
    ),

    "Validation of Self": _m(
        ["shame", "sadness", "loneliness", "disappointment", "self_criticism",
         "guilt", "rejection", "insecurity", "self_blame", "grief",
         "emptiness", "fear", "hopelessness"],
        avoid=["panic", "panic_now"],
        min_i=0.15, max_i=0.75,
        mode="regulation_skill",
        pacing="slow",
        contexts=["self_validation", "inner_compassion",
                  "shame_reduction", "emotion_legitimisation",
                  "self_acceptance"],
    ),

    "Distress Tolerance Body Scan": _m(
        ["panic", "overwhelm", "anger", "tension", "dissociation", "fear",
         "high_anxiety", "distress", "panic_now", "rage", "numbness",
         "shame"],
        avoid=[],
        min_i=0.4, max_i=1.0,
        mode="regulation_skill",
        contexts=["body_based_distress", "dissociation_rescue",
                  "crisis_grounding", "somatic_regulation",
                  "acute_distress_body_work"],
    ),

    "Dialectical Thinking": _m(
        ["ambivalence", "anger", "confusion", "indecision", "resentment",
         "hopelessness", "shame", "guilt", "fear", "frustration",
         "sadness", "anxiety"],
        avoid=["panic", "panic_now"],
        min_i=0.15, max_i=0.7,
        mode="regulation_skill",
        contexts=["both_and_thinking", "polarised_thinking_correction",
                  "all_or_nothing_reframe", "dialectical_synthesis"],
    ),

    "Observe, Describe, Participate": _m(
        ["confusion", "overwhelm", "stress", "rumination", "anxiety",
         "anger", "sadness", "dissociation", "numbness", "avoidance",
         "low_mood", "fear", "tension"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.8,
        mode="regulation_skill",
        contexts=["mindfulness_skills", "non_judgemental_observation",
                  "present_focus", "emotion_labelling",
                  "mindful_engagement"],
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # ADVANCED JOURNALING
    # ══════════════════════════════════════════════════════════════════════════

    "Clustering/Mind Mapping": _m(
        ["confusion", "overwhelm", "creative_block", "rumination", "anxiety",
         "stress", "indecision", "procrastination", "anger", "sadness",
         "low_mood", "grief"],
        avoid=["panic", "panic_now"],
        min_i=0.15, max_i=0.65,
        mode="reflection",
        contexts=["organize_inner_material", "creative_brainstorming",
                  "problem_mapping", "confusion_untangling"],
    ),

    "Parts Work Journal": _m(
        ["ambivalence", "shame", "self_criticism", "confusion", "guilt",
         "fear", "anger", "sadness", "rejection", "indecision",
         "hopelessness", "loneliness"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.8,
        mode="reflection",
        pacing="slow",
        contexts=["inner_parts", "IFS_journaling", "internal_conflict_exploration",
                  "self_compassion_deepening", "inner_child_work"],
    ),

    "Alternate Perspective Journal": _m(
        ["anger", "resentment", "feeling_disrespected", "rejection",
         "shame", "guilt", "hopelessness", "frustration", "sadness",
         "loneliness", "disappointment", "grief"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.75,
        mode="reflection",
        contexts=["perspective_shift", "empathy_building",
                  "conflict_reappraisal", "resentment_softening",
                  "compassionate_reframe"],
    ),

    "Triggered Journal": _m(
        ["anger", "panic", "rejection", "shame", "overwhelm", "fear",
         "resentment", "anxiety", "dissociation", "frustration",
         "guilt", "sadness"],
        avoid=[],
        min_i=0.3, max_i=0.9,
        mode="reflection",
        contexts=["trigger_mapping", "pattern_identification",
                  "trauma_trigger_work", "reactive_emotion_analysis"],
    ),

    "Timeline Journal": _m(
        ["grief", "sadness", "unresolved_feelings", "regret", "shame",
         "guilt", "loneliness", "rejection", "hopelessness",
         "disappointment", "anger", "resentment", "fear"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.8,
        mode="reflection",
        pacing="slow",
        contexts=["life_story_processing", "grief_narrative",
                  "identity_reconstruction", "trauma_narrative",
                  "meaning_making_over_time"],
    ),

    "Future Projection Journal": _m(
        ["worry", "hopelessness", "low_mood", "avoidance", "anxiety",
         "fear", "procrastination", "sadness", "emptiness", "indecision",
         "shame", "low_expectancy"],
        avoid=["panic", "panic_now"],
        min_i=0.15, max_i=0.7,
        mode="reflection",
        contexts=["future_self", "hope_building", "goal_visualisation",
                  "hopelessness_interruption", "values_projection"],
    ),

    "Habit Tracker Journal": _m(
        ["procrastination", "fatigue", "low_mood", "avoidance", "burnout",
         "anhedonia", "anxiety", "stress", "indecision"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.6,
        mode="reflection",
        contexts=["behavior_pattern", "routine_monitoring",
                  "habit_formation", "self_accountability",
                  "incremental_progress_tracking"],
    ),

    "Rewrite Your Story Journal": _m(
        ["shame", "regret", "hopelessness", "inadequacy", "grief",
         "rejection", "self_blame", "guilt", "sadness", "loneliness",
         "emptiness", "anger", "resentment"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.8,
        mode="reflection",
        pacing="slow",
        contexts=["narrative_reframe", "trauma_narrative_reshaping",
                  "identity_shift", "victim_to_survivor_reframe",
                  "meaning_making"],
    ),

    "Sentence Stems Journal": _m(
        ["confusion", "worry", "insecurity", "ambivalence", "indecision",
         "fear", "shame", "sadness", "hopelessness", "low_mood",
         "grief", "anger", "procrastination"],
        avoid=["panic", "panic_now"],
        min_i=0.15, max_i=0.7,
        mode="reflection",
        contexts=["prompted_insight", "emotion_exploration",
                  "value_uncovering", "blocked_expression",
                  "therapeutic_writing"],
    ),

    "Metaphor Exploration Journal": _m(
        ["sadness", "grief", "emptiness", "confusion", "anger", "shame",
         "hopelessness", "loneliness", "fear", "low_mood", "numbness",
         "rejection", "overwhelm"],
        avoid=["panic", "panic_now"],
        min_i=0.15, max_i=0.75,
        mode="reflection",
        contexts=["symbolic_expression", "right_brain_processing",
                  "artistic_therapy_entry", "emotion_externalisation",
                  "grief_symbolism"],
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # ADVANCED BEHAVIORAL ACTIVATION
    # ══════════════════════════════════════════════════════════════════════════

    "Reverse Scheduling": _m(
        ["burnout", "resentment", "overwhelm", "guilt", "stress",
         "fatigue", "anger", "procrastination", "anxiety", "low_mood",
         "anhedonia"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.75,
        mode="behavioral_action",
        contexts=["rest_first_planning", "burnout_recovery",
                  "overcommitment_reduction", "energy_pacing",
                  "sustainable_scheduling"],
    ),

    "Behavioral Chain Analysis": _m(
        ["impulsivity", "avoidance", "shame", "anger", "resentment",
         "frustration", "guilt", "self_criticism", "fear", "anxiety",
         "rejection", "hopelessness"],
        avoid=["panic", "panic_now"],
        min_i=0.3, max_i=0.85,
        mode="behavioral_action",
        contexts=["chain_mapping", "behaviour_antecedent_analysis",
                  "relapse_analysis", "self_harm_chain",
                  "emotion_behaviour_link"],
    ),

    "Opposite Action Practice": _m(
        ["avoidance", "shame", "sadness", "anger", "fear", "guilt",
         "loneliness", "anxiety", "hopelessness", "isolation",
         "low_mood", "rejection", "embarrassment"],
        avoid=["panic", "panic_now"],
        min_i=0.3, max_i=0.85,
        mode="behavioral_action",
        contexts=["urge_opposite", "exposure_based_action",
                  "shame_opposite", "loneliness_outreach",
                  "fear_approach"],
    ),

    "Graded Task Assignment": _m(
        ["overwhelm", "avoidance", "procrastination", "performance_anxiety",
         "fear", "hopelessness", "low_mood", "fatigue", "shame",
         "anxiety", "low_expectancy", "indecision"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.8,
        mode="behavioral_action",
        contexts=["graded_exposure_to_tasks", "task_hierarchy",
                  "avoidance_ladder", "confidence_building",
                  "stepped_exposure"],
    ),

    "Activity Experiment": _m(
        ["anhedonia", "low_mood", "avoidance", "hopelessness", "emptiness",
         "fatigue", "shame", "low_expectancy", "anxiety", "procrastination",
         "burnout", "isolation"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.75,
        mode="behavioral_action",
        contexts=["activity_prediction_test", "pleasure_prediction",
                  "anhedonia_interruption", "mastery_experience",
                  "mood_activity_testing"],
    ),

    "Social Skills Practice": _m(
        ["social_anxiety", "loneliness", "insecurity", "isolation",
         "shame", "rejection", "fear", "awkwardness", "anger",
         "low_mood", "people_pleasing", "frustration"],
        avoid=["panic", "panic_now"],
        min_i=0.2, max_i=0.75,
        mode="behavioral_action",
        pacing="slow",
        contexts=["connection_practice", "social_confidence_building",
                  "communication_skills", "intimacy_building",
                  "social_re_engagement"],
    ),

    "Reward Scheduling": _m(
        ["low_mood", "procrastination", "fatigue", "anhedonia", "burnout",
         "hopelessness", "emptiness", "avoidance", "shame", "anxiety",
         "self_criticism"],
        avoid=["panic", "panic_now"],
        min_i=0.1, max_i=0.65,
        mode="behavioral_action",
        contexts=["positive_reinforcement", "motivation_building",
                  "self_reward", "task_completion_incentive",
                  "depression_activation"],
    ),

    "Role Modeling": _m(
        ["insecurity", "inadequacy", "low_mood", "hopelessness",
         "shame", "fear", "social_anxiety", "rejection", "low_expectancy",
         "loneliness", "emptiness"],
        avoid=["panic", "panic_now"],
        min_i=0.15, max_i=0.65,
        mode="behavioral_action",
        contexts=["identity_practice", "aspirational_modelling",
                  "confidence_building", "social_learning",
                  "identity_expansion"],
    ),

    "Environmental Design": _m(
        ["procrastination", "avoidance", "stress", "overwhelm", "anxiety",
         "fatigue", "low_mood", "anger", "frustration", "indecision",
         "burnout", "distraction"],
        avoid=["panic", "panic_now"],
        min_i=0.1, max_i=0.7,
        mode="behavioral_action",
        contexts=["reduce_friction", "habit_cue_design",
                  "nudge_architecture", "default_option_optimisation",
                  "environment_for_goals"],
    ),

    "Commitment Devices": _m(
        ["procrastination", "avoidance", "ambivalence", "worry",
         "impulsivity", "indecision", "shame", "anxiety", "hopelessness",
         "self_criticism", "low_mood"],
        avoid=["panic", "panic_now"],
        min_i=0.15, max_i=0.7,
        mode="behavioral_action",
        contexts=["accountability", "pre_commitment",
                  "goal_locking", "impulse_control_design",
                  "self_contract"],
    ),
}



# =============================================================================
# POST-PROCESSING OVERRIDES / SAFETY FIXES
# =============================================================================

TECHNIQUE_METADATA_OVERRIDES = {
    # Safer breath-holding range.
    "4-7-8 Breathing": {
        "max_intensity": 0.75,
        "avoid_sub_emotions": ["boredom", "high_anxiety", "hyperventilation", "panic_now"],
        "avoid_symptoms": ["shortness_of_breath", "dizziness"],
    },

    # Better for performance anxiety than active panic.
    "Box Breathing": {
        "max_intensity": 0.80,
        "avoid_sub_emotions": ["boredom", "hyperventilation", "panic_now"],
        "avoid_symptoms": ["shortness_of_breath"],
        "best_for_contexts": [
            "acute_pressure", "presentation_anxiety", "pre_performance",
            "pre_exam_anxiety", "performance_calm", "emotion_regulation_reset",
        ],
    },

    # Body scans can be uncomfortable for body-focused anxiety.
    "Body Scan Meditation": {
        "avoid_sub_emotions": ["panic", "panic_now"],
        "avoid_symptoms": ["health_anxiety", "body_focused_anxiety"],
    },

    # Your FYP/project use case.
    "Problem-Solving Worksheet": {
        "best_for_contexts": [
            "practical_problem_solving", "obstacle_mapping",
            "solution_generation", "frustration_redirect",
            "structured_decision_making", "project_deadline",
            "technical_complexity", "final_year_project",
            "backend_architecture", "database_integration",
            "exam_pressure", "academic_anxiety", "academic_risk",
        ],
    },

    "Anti-Procrastination List": {
        "best_for_contexts": [
            "task_starting", "overwhelm_chunking",
            "avoidance_interruption", "productivity_entry",
            "study_planning", "project_deadline",
            "coding_task_start", "exam_preparation",
        ],
    },

    "Graded Task Assignment": {
        "best_for_contexts": [
            "graded_exposure_to_tasks", "task_hierarchy",
            "avoidance_ladder", "confidence_building",
            "stepped_exposure", "large_project",
            "backend_architecture", "final_year_project",
            "deadline_pressure",
        ],
    },

    # CBT worksheets should require a concrete thought/belief.
    "Thought Record": {
        "best_for_contexts": [
            "specific_negative_thought", "thought_challenge",
            "cognitive_restructuring_entry", "mood_episode_analysis",
            "distortion_identification", "grief_processing",
            "specific_exam_failure_belief", "catastrophic_exam_thought",
            "academic_anxiety", "exam_pressure", "academic_risk",
        ],
    },

    "Cognitive Restructuring": {
        "best_for_contexts": [
            "belief_reframe", "negative_automatic_thought_work",
            "catastrophising_correction", "catastrophic_exam_thought",
            "specific_exam_failure_belief", "academic_anxiety",
            "exam_pressure", "academic_risk",
        ],
    },

    "Worry Time": {
        "best_for_contexts": [
            "scheduled_worry", "worry_containment", "rumination_time_boxing",
            "anxiety_management", "intrusive_thought_reduction",
            "bedtime_rumination", "nighttime_worry", "sleep_difficulty",
            "exam_week", "exam_pressure", "academic_anxiety",
        ],
    },

    "Mindfulness of Thoughts": {
        "best_for_contexts": [
            "defusion", "thought_observation", "cognitive_defusion",
            "rumination_interrupt", "metacognitive_awareness",
            "bedtime_rumination", "sleep_difficulty", "nighttime_worry",
            "academic_anxiety", "exam_week",
        ],
    },

    "Brain Dump Before Sleep": {
        "target_sub_emotions": [
            "bedtime_rumination", "racing_thoughts", "worry",
            "academic_pressure", "fear_of_failure",
        ],
        "target_symptoms": ["sleep_difficulty", "bedtime_racing_thoughts"],
        "target_behaviors": ["rumination"],
        "best_for_contexts": [
            "thought_unloading", "bedtime_rumination", "sleep_difficulty",
            "nighttime_worry", "exam_week", "exam_pressure",
            "academic_anxiety",
        ],
        "min_intensity": 0.1,
        "max_intensity": 0.65,
        "delivery_mode": "reflection",
    },

    "Thought Defusion": {
        "target_sub_emotions": [
            "rumination", "racing_thoughts", "worry", "catastrophizing",
            "fortune_telling", "fear_of_failure", "future_threat",
            "bedtime_rumination",
        ],
        "target_behaviors": ["rumination"],
        "best_for_contexts": [
            "defusion", "cognitive_defusion", "thought_observation",
            "rumination_interrupt", "metacognitive_awareness",
            "bedtime_rumination", "catastrophic_exam_thought",
        ],
        "min_intensity": 0.15,
        "max_intensity": 0.75,
        "delivery_mode": "exercise",
    },

    "Leaves on a Stream": {
        "target_sub_emotions": [
            "rumination", "racing_thoughts", "worry", "bedtime_rumination",
            "catastrophizing", "future_threat",
        ],
        "target_symptoms": ["sleep_difficulty", "bedtime_racing_thoughts"],
        "target_behaviors": ["rumination"],
        "best_for_contexts": [
            "cognitive_defusion", "thought_observation", "rumination_interrupt",
            "bedtime_rumination", "sleep_difficulty", "nighttime_worry",
        ],
        "min_intensity": 0.1,
        "max_intensity": 0.7,
        "delivery_mode": "exercise",
    },

    "Stimulus Control for Sleep": {
        "target_sub_emotions": [
            "bedtime_rumination", "restlessness", "worry", "stress",
        ],
        "target_symptoms": ["sleep_difficulty", "sleep_disruption"],
        "target_behaviors": ["avoidance"],
        "best_for_contexts": [
            "sleep_onset", "sleep_environment", "bedtime_wind_down",
            "bedtime_rumination", "sleep_difficulty", "nighttime_worry",
        ],
        "min_intensity": 0.1,
        "max_intensity": 0.65,
        "delivery_mode": "plan",
    },

    "Sleep Wind-Down Routine": {
        "target_sub_emotions": [
            "bedtime_rumination", "stress", "worry", "restlessness",
            "academic_pressure",
        ],
        "target_symptoms": ["sleep_difficulty", "sleep_disruption"],
        "best_for_contexts": [
            "sleep_onset", "bedtime_wind_down", "sleep_difficulty",
            "nighttime_worry", "exam_week", "academic_anxiety",
        ],
        "min_intensity": 0.1,
        "max_intensity": 0.6,
        "delivery_mode": "plan",
    },

    "Constructive Worry Worksheet": {
        "target_sub_emotions": [
            "worry", "rumination", "bedtime_rumination", "academic_pressure",
            "future_threat", "fear_of_failure",
        ],
        "target_symptoms": ["sleep_difficulty", "bedtime_racing_thoughts"],
        "target_behaviors": ["rumination", "procrastination"],
        "best_for_contexts": [
            "scheduled_worry", "worry_containment", "practical_problem_solving",
            "bedtime_rumination", "exam_week", "exam_pressure",
            "academic_anxiety",
        ],
        "min_intensity": 0.15,
        "max_intensity": 0.7,
        "delivery_mode": "worksheet",
    },

    "Decatastrophizing Questions": {
        "target_sub_emotions": [
            "catastrophizing", "fortune_telling", "fear_of_failure",
            "future_threat", "academic_pressure",
        ],
        "target_behaviors": ["rumination"],
        "best_for_contexts": [
            "catastrophising_correction", "belief_challenge",
            "catastrophic_exam_thought", "specific_exam_failure_belief",
            "academic_risk", "exam_pressure",
        ],
        "min_intensity": 0.2,
        "max_intensity": 0.75,
        "delivery_mode": "worksheet",
    },

    "Coping Card for Catastrophic Thoughts": {
        "target_sub_emotions": [
            "catastrophizing", "fortune_telling", "fear_of_failure",
            "future_threat", "panic", "worry",
        ],
        "best_for_contexts": [
            "belief_challenge", "catastrophic_exam_thought",
            "specific_exam_failure_belief", "academic_risk",
            "panic_coping", "exam_pressure",
        ],
        "min_intensity": 0.2,
        "max_intensity": 0.8,
        "delivery_mode": "plan",
    },

    "Self-Soothing with Five Senses": {
        "target_sub_emotions": [
            "distress", "panic", "overwhelm", "shame", "grief",
            "anger", "fear",
        ],
        "target_symptoms": ["tension", "restlessness"],
        "best_for_contexts": [
            "nervous_system_regulation", "distress_tolerance",
            "grounding", "emotion_regulation",
        ],
        "min_intensity": 0.25,
        "max_intensity": 0.85,
        "delivery_mode": "exercise",
    },

    "Exam Coping Plan": {
        "target_sub_emotions": [
            "academic_pressure", "fear_of_failure", "future_threat",
            "worry", "overwhelm", "procrastination",
        ],
        "target_behaviors": ["procrastination", "avoidance", "task_starting"],
        "best_for_contexts": [
            "exam_week", "exam_pressure", "academic_anxiety",
            "academic_risk", "practical_problem_solving",
            "pre_performance",
        ],
        "min_intensity": 0.2,
        "max_intensity": 0.75,
        "delivery_mode": "plan",
    },

    "Environmental Design": {
        "avoid_sub_emotions": [
            "panic", "panic_now", "fear_of_failure", "catastrophizing",
            "fortune_telling", "bedtime_rumination", "future_threat",
        ],
        "best_for_contexts": [
            "reduce_friction", "habit_cue_design", "nudge_architecture",
            "default_option_optimisation", "environment_for_goals",
            "sleep_environment", "phone_distraction", "study_space_distraction",
        ],
    },

    "Gratitude Journaling": {
        "avoid_sub_emotions": [
            "panic", "panic_now", "grief", "shame", "high_anxiety",
            "fear_of_failure", "catastrophizing", "fortune_telling",
            "bedtime_rumination", "academic_pressure", "future_threat",
        ],
        "best_for_contexts": [
            "savoring_positive", "mood_lift", "negativity_bias_correction",
            "resilience_building", "wellbeing_maintenance",
        ],
    },
}


def _canonical_name(name: str) -> str:
    return TECHNIQUE_ALIASES.get(str(name or ""), str(name or ""))


def _derive_core_emotions(
    sub_emotions: Iterable[str] | None,
    fallback_targets: Iterable[str] | None = None,
) -> list[str]:
    derived: list[str] = []
    for sub in _clean_subs(sub_emotions):
        core = SUB_EMOTION_TO_CORE.get(sub)
        if core and core not in derived:
            derived.append(core)

    if derived:
        return derived

    return _clean_core_emotions(fallback_targets or [])


def _default_metadata(category: str = "", target_emotions: Iterable[str] | None = None) -> dict:
    base = deepcopy(_CATEGORY_DEFAULTS.get(category, _CATEGORY_DEFAULTS.get(str(category or ""), _CATEGORY_DEFAULTS[""])))

    # Expand broad technique.targetEmotions into sub-emotions.
    expanded_subs = list(base.get("target_sub_emotions", []))
    for emotion in target_emotions or []:
        expanded_subs.extend(_CORE_TO_SUBS.get(str(emotion or "").upper(), []))

    base["target_sub_emotions"] = _clean_subs(expanded_subs)
    base["avoid_sub_emotions"] = _clean_subs(base.get("avoid_sub_emotions", []))
    base["target_symptoms"] = _clean_subs(base.get("target_symptoms", []))
    base["target_behaviors"] = _clean_subs(base.get("target_behaviors", []))
    base["avoid_symptoms"] = _clean_subs(base.get("avoid_symptoms", []))
    base["avoid_behaviors"] = _clean_subs(base.get("avoid_behaviors", []))
    base["best_for_contexts"] = _clean_contexts(base.get("best_for_contexts", []))
    return base


def _merge_metadata(base: dict, override: dict | None) -> dict:
    """Merge metadata safely, replacing explicit override lists where supplied."""
    if not override:
        return base

    merged = deepcopy(base)

    for key, value in deepcopy(override).items():
        if key in {
            "target_sub_emotions", "target_symptoms", "target_behaviors",
            "avoid_sub_emotions", "avoid_symptoms", "avoid_behaviors",
            "best_for_contexts", "target_emotions",
        }:
            merged[key] = _unique(value)
        else:
            merged[key] = value

    return merged


def _apply_advanced_breathing_safety(name: str, metadata: dict) -> dict:
    if name not in ADVANCED_BREATHING_TECHNIQUES:
        return metadata

    metadata["pacing_tier"] = "advanced"
    metadata["delivery_mode"] = "advanced_energizing"

    metadata["avoid_sub_emotions"] = _unique(
        list(metadata.get("avoid_sub_emotions", [])) + list(ADVANCED_BREATHING_AVOID_SUBS)
    )
    metadata["avoid_symptoms"] = _unique(
        list(metadata.get("avoid_symptoms", [])) + list(ADVANCED_BREATHING_AVOID_SYMPTOMS)
    )
    metadata["max_intensity"] = min(float(metadata.get("max_intensity", 1.0)), 0.50)
    return metadata


def _finalize_metadata(name: str, metadata: dict, fallback_targets: Iterable[str] | None = None) -> dict:
    # Clean lists.
    for key in [
        "target_sub_emotions", "target_symptoms", "target_behaviors",
        "avoid_sub_emotions", "avoid_symptoms", "avoid_behaviors",
        "best_for_contexts",
    ]:
        metadata[key] = _unique(metadata.get(key, []))

    # Fix weak context labels.
    metadata["best_for_contexts"] = _unique(
        WEAK_CONTEXT_RENAMES.get(ctx, ctx) for ctx in metadata.get("best_for_contexts", [])
    )

    # Derive core emotions from sub-emotions.
    explicit_core = _clean_core_emotions(metadata.get("target_emotions", []))
    metadata["target_emotions"] = explicit_core or _derive_core_emotions(
        metadata.get("target_sub_emotions", []),
        fallback_targets,
    )

    # Clamp intensities.
    metadata["min_intensity"] = max(0.0, min(1.0, float(metadata.get("min_intensity", 0.0))))
    metadata["max_intensity"] = max(
        metadata["min_intensity"],
        min(1.0, float(metadata.get("max_intensity", 1.0))),
    )

    metadata["pacing_tier"] = str(metadata.get("pacing_tier") or "normal")
    metadata["delivery_mode"] = str(metadata.get("delivery_mode") or "exercise")

    # Apply special safety rules last.
    metadata = _apply_advanced_breathing_safety(name, metadata)

    return metadata


# =============================================================================
# PUBLIC API
# =============================================================================

def technique_emotion_metadata(
    name: str,
    category: str = "",
    target_emotions: Iterable[str] | None = None,
) -> dict:
    """
    Return fully normalized metadata for a technique.

    Backward compatible fields:
      - target_emotions
      - target_sub_emotions
      - avoid_sub_emotions
      - min_intensity
      - max_intensity
      - pacing_tier
      - delivery_mode
      - best_for_contexts

    New richer fields:
      - target_symptoms
      - target_behaviors
      - avoid_symptoms
      - avoid_behaviors
    """
    canonical = _canonical_name(name)
    metadata = _default_metadata(category, target_emotions)

    override = TECHNIQUE_EMOTION_METADATA.get(canonical)
    metadata = _merge_metadata(metadata, override)

    safety_override = TECHNIQUE_METADATA_OVERRIDES.get(canonical)
    metadata = _merge_metadata(metadata, safety_override)

    return _finalize_metadata(canonical, metadata, target_emotions)


def annotate_technique_dict(technique: dict, category: str = "") -> dict:
    """Attach normalized metadata to one technique dict."""
    metadata = technique_emotion_metadata(
        str(technique.get("name") or ""),
        category or str(technique.get("category") or ""),
        technique.get("target_emotions") or technique.get("targetEmotions") or [],
    )

    # Always update metadata fields so stale DB seed values do not dominate.
    technique["target_emotions"] = metadata["target_emotions"]
    technique["target_sub_emotions"] = metadata["target_sub_emotions"]
    technique["target_symptoms"] = metadata["target_symptoms"]
    technique["target_behaviors"] = metadata["target_behaviors"]
    technique["avoid_sub_emotions"] = metadata["avoid_sub_emotions"]
    technique["avoid_symptoms"] = metadata["avoid_symptoms"]
    technique["avoid_behaviors"] = metadata["avoid_behaviors"]
    technique["min_intensity"] = metadata["min_intensity"]
    technique["max_intensity"] = metadata["max_intensity"]
    technique["pacing_tier"] = metadata["pacing_tier"]
    technique["delivery_mode"] = metadata["delivery_mode"]
    technique["best_for_contexts"] = metadata["best_for_contexts"]
    return technique


def annotate_technique_list(techniques: list[dict], category: str = "") -> list[dict]:
    for technique in techniques:
        annotate_technique_dict(technique, category)
    return techniques


def prisma_metadata_fields(technique: dict, category: str = "") -> dict:
    """
    Convert metadata into Prisma/DB seed field names.

    Keep your existing Prisma fields:
      targetSubEmotions, avoidSubEmotions, minIntensity, maxIntensity,
      pacingTier, deliveryMode, bestForContexts

    Add these fields to Prisma if you want richer matching:
      targetSymptoms, targetBehaviors, avoidSymptoms, avoidBehaviors
    """
    metadata = technique_emotion_metadata(
        str(technique.get("name") or ""),
        category or str(technique.get("category") or ""),
        technique.get("target_emotions") or technique.get("targetEmotions") or [],
    )

    return {
        "targetSubEmotions": metadata["target_sub_emotions"],
        "targetSymptoms": metadata["target_symptoms"],
        "targetBehaviors": metadata["target_behaviors"],
        "avoidSubEmotions": metadata["avoid_sub_emotions"],
        "avoidSymptoms": metadata["avoid_symptoms"],
        "avoidBehaviors": metadata["avoid_behaviors"],
        "minIntensity": metadata["min_intensity"],
        "maxIntensity": metadata["max_intensity"],
        "pacingTier": metadata["pacing_tier"],
        "deliveryMode": metadata["delivery_mode"],
        "bestForContexts": metadata["best_for_contexts"],
    }


def target_emotions_for_technique(technique: dict, category: str = "") -> list[str]:
    metadata = technique_emotion_metadata(
        str(technique.get("name") or ""),
        category or str(technique.get("category") or ""),
        technique.get("target_emotions") or technique.get("targetEmotions") or [],
    )
    return metadata["target_emotions"]


def is_technique_safe_for_state(
    technique_name: str,
    *,
    sub_emotions: Iterable[str] | None = None,
    symptoms: Iterable[str] | None = None,
    behaviors: Iterable[str] | None = None,
    intensity: float | None = None,
    category: str = "",
) -> tuple[bool, list[str]]:
    """
    Safety/ranking helper.

    Returns:
        (is_safe, reasons)

    This does not replace clinical safety checks. It only prevents obvious
    recommendation mismatches.
    """
    metadata = technique_emotion_metadata(technique_name, category)
    reasons: list[str] = []

    user_subs = set(_unique(sub_emotions))
    user_symptoms = set(_unique(symptoms))
    user_behaviors = set(_unique(behaviors))

    blocked_subs = user_subs.intersection(metadata.get("avoid_sub_emotions", []))
    blocked_symptoms = user_symptoms.intersection(metadata.get("avoid_symptoms", []))
    blocked_behaviors = user_behaviors.intersection(metadata.get("avoid_behaviors", []))

    if blocked_subs:
        reasons.append(f"blocked_sub_emotions={sorted(blocked_subs)}")
    if blocked_symptoms:
        reasons.append(f"blocked_symptoms={sorted(blocked_symptoms)}")
    if blocked_behaviors:
        reasons.append(f"blocked_behaviors={sorted(blocked_behaviors)}")

    if intensity is not None:
        i = max(0.0, min(1.0, float(intensity)))
        if i < metadata["min_intensity"]:
            reasons.append(f"intensity_too_low={i:.2f}<min={metadata['min_intensity']:.2f}")
        if i > metadata["max_intensity"]:
            reasons.append(f"intensity_too_high={i:.2f}>max={metadata['max_intensity']:.2f}")

    return (len(reasons) == 0), reasons


def score_technique_match(
    technique_name: str,
    *,
    sub_emotions: Iterable[str] | None = None,
    symptoms: Iterable[str] | None = None,
    behaviors: Iterable[str] | None = None,
    contexts: Iterable[str] | None = None,
    intensity: float | None = None,
    category: str = "",
) -> float:
    """
    Lightweight deterministic score for technique ranking.

    Suggested usage:
    - Use this as one component in your recommender.
    - Combine with user rating, recent-use penalty, and technique effectiveness.
    - Context and intensity are accepted for API compatibility, but do not
      influence the ranking score.

    Returns 0.0–1.0.
    """
    metadata = technique_emotion_metadata(technique_name, category)
    safe, _reasons = is_technique_safe_for_state(
        technique_name,
        sub_emotions=sub_emotions,
        symptoms=symptoms,
        behaviors=behaviors,
        category=category,
    )
    if not safe:
        return 0.0

    score = 0.0

    user_subs = set(_unique(sub_emotions))
    user_symptoms = set(_unique(symptoms))
    user_behaviors = set(_unique(behaviors))
    score += 0.45 * bool(user_subs.intersection(metadata["target_sub_emotions"]))
    score += 0.30 * bool(user_symptoms.intersection(metadata["target_symptoms"]))
    score += 0.25 * bool(user_behaviors.intersection(metadata["target_behaviors"]))

    return max(0.0, min(1.0, score))


__all__ = [
    "TECHNIQUE_EMOTION_METADATA",
    "TECHNIQUE_ALIASES",
    "CANONICAL_SUB_EMOTIONS",
    "EMPATHY_FIRST_SUB_EMOTIONS",
    "NO_TECHNIQUE_BY_DEFAULT_SUB_EMOTIONS",
    "SYMPTOM_TAGS",
    "BEHAVIOR_TAGS",
    "PROJECT_STUDY_CONTEXTS",
    "technique_emotion_metadata",
    "annotate_technique_dict",
    "annotate_technique_list",
    "prisma_metadata_fields",
    "target_emotions_for_technique",
    "is_technique_safe_for_state",
    "score_technique_match",
]
