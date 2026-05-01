"""
Behavioral Activation Engine Node (Node 3b) - SentiMind v3.0

ARCHITECTURE NODE 3b:
Purpose: Recommend concrete, real-world micro-actions based on the user's emotional state,
         intensity level, time of day, and psychological profile.
         This implements evidence-based Behavioral Activation Therapy (BAT) principles.

Runs AFTER conversation_planner_node, BEFORE technique_selector_node.
No LLM call — deterministic decision matrix.

MICRO-ACTION CATEGORIES:
  - Physical movement    (walk, stretch, breathe)
  - Social connection    (message a friend, call someone)
  - Environmental       (tidy space, change location)
  - Nourishment         (water, food, rest)
  - Cognitive grounding  (write, name 5 things, reflect)

OUTPUT STATE FIELDS:
  - micro_action:           str | None
  - micro_action_rationale: str | None
  - micro_action_category:  str | None
"""

import datetime
from ..agent.state import MentalHealthState


# ============================================
# MICRO-ACTION DATABASE
# ============================================
# Structure: (emotion, intensity_band) → list[(action, rationale, category, time_filter)]
# time_filter: "any" | "daytime" | "night"

ACTIVATION_MATRIX: dict[tuple, list[dict]] = {
    ("sadness", "high"): [
        {"action": "Send a short message to one person you trust", "rationale": "Social connection is the fastest buffer against sadness.", "category": "social", "time": "any"},
        {"action": "Step outside for 10 minutes, even briefly", "rationale": "Daylight and movement reduce cortisol and boost serotonin.", "category": "physical", "time": "daytime"},
        {"action": "Write down 3 things that happened today — anything at all", "rationale": "Journaling externalizes emotion and provides perspective.", "category": "cognitive", "time": "any"},
        {"action": "Tidy one small area nearby (desk, pillow, sink)", "rationale": "Environmental control restores a sense of agency.", "category": "environmental", "time": "any"},
    ],
    ("sadness", "medium"): [
        {"action": "Make yourself a warm drink and sit quietly for 5 minutes", "rationale": "Physical warmth activates the parasympathetic nervous system.", "category": "nourishment", "time": "any"},
        {"action": "Write one thing you appreciated today, however small", "rationale": "Gratitude micro-journaling shifts cognitive framing.", "category": "cognitive", "time": "any"},
        {"action": "Put on one song that historically lifts your mood", "rationale": "Music directly activates dopamine reward pathways.", "category": "physical", "time": "any"},
    ],
    ("sadness", "low"): [
        {"action": "Notice one small beautiful or interesting thing around you", "rationale": "Mindful attention interrupts rumination cycles.", "category": "cognitive", "time": "any"},
    ],
    ("anxiety", "high"): [
        {"action": "Drink a glass of cold water slowly right now", "rationale": "Cold water triggers the dive reflex, rapidly slowing heart rate.", "category": "nourishment", "time": "any"},
        {"action": "Name 5 things you can see from where you are", "rationale": "5-4-3-2-1 grounding anchors attention to the present moment.", "category": "cognitive", "time": "any"},
        {"action": "Walk to another room and back slowly", "rationale": "Physical movement discharges adrenaline and cortisol.", "category": "physical", "time": "any"},
    ],
    ("anxiety", "medium"): [
        {"action": "Step away from your screen for 5 minutes", "rationale": "Screen breaks reduce sympathetic nervous system activation.", "category": "environmental", "time": "any"},
        {"action": "Write down what you can and cannot control in this situation", "rationale": "Separating locus of control reduces anxiety-driven rumination.", "category": "cognitive", "time": "any"},
        {"action": "Take 3 slow belly breaths before responding to anything", "rationale": "Diaphragmatic breathing directly activates the vagus nerve.", "category": "physical", "time": "any"},
    ],
    ("anxiety", "low"): [
        {"action": "Check in with your body: where do you feel it?", "rationale": "Somatic awareness reduces anticipatory anxiety.", "category": "cognitive", "time": "any"},
    ],
    ("anger", "high"): [
        {"action": "Walk briskly around the block or do 10 jumping jacks", "rationale": "High-intensity movement metabolizes excess adrenaline effectively.", "category": "physical", "time": "daytime"},
        {"action": "Splash cold water on your face or wrists", "rationale": "Cold water activates the mammalian dive reflex, calming the nervous system.", "category": "nourishment", "time": "any"},
        {"action": "Write what you are angry about — not who — for 5 minutes", "rationale": "Writing anger externalizes it safely without suppression.", "category": "cognitive", "time": "any"},
    ],
    ("anger", "medium"): [
        {"action": "Change your physical location for 10 minutes", "rationale": "Environmental change breaks the stimulus-anger association.", "category": "environmental", "time": "any"},
        {"action": "Take 5 full breath cycles before you respond to anyone", "rationale": "Breathing creates a pause between stimulus and response.", "category": "physical", "time": "any"},
    ],
    ("fear", "any"): [
        {"action": "Ground yourself: name 5 things you can see right now", "rationale": "Grounding breaks the fear-threat cycle by redirecting attention.", "category": "cognitive", "time": "any"},
        {"action": "Remind yourself: what is actually happening vs. what you imagine?", "rationale": "Reality-testing interrupts the fear escalation loop.", "category": "cognitive", "time": "any"},
    ],
    ("neutral", "any"): [
        {"action": "If you have a moment, write one intention for tomorrow", "rationale": "Proactive planning boosts sense of purpose and direction.", "category": "cognitive", "time": "any"},
    ],
    ("joy", "any"): [
        {"action": "Share what's going well with someone who matters to you", "rationale": "Sharing positive experiences amplifies and extends positive affect.", "category": "social", "time": "any"},
    ],
}

# Fallback for unmatched states
FALLBACK_ACTIONS = [
    {"action": "Take 3 slow, deep breaths right now", "rationale": "Controlled breathing is universally calming regardless of emotional state.", "category": "physical", "time": "any"},
    {"action": "Drink a glass of water", "rationale": "Hydration supports cognitive clarity and emotional regulation.", "category": "nourishment", "time": "any"},
]


# ============================================
# MAIN NODE FUNCTION
# ============================================

def activate_behavioral_intervention(state: MentalHealthState) -> dict:
    """
    BEHAVIORAL ACTIVATION ENGINE — Deterministic real-world micro-action recommender.

    Process:
    1. Extract emotion, intensity, conversation strategy, and time context
    2. Apply profile-based filters (avoidant copring → simplest action first)
    3. Lookup from activation matrix
    4. Filter by time of day
    5. Return best micro-action

    No LLM involved. ~<10ms.
    """
    emotion = state.get("fused_emotion", state.get("emotion", "neutral")).lower()
    intensity = state.get("fused_intensity", state.get("intensity", 0.5))
    strategy = state.get("conversation_strategy", "validate_only")
    psych_profile = state.get("psych_profile", {})

    print(f"\n[NODE: ACTIVATION] 💡 Selecting micro-action | Emotion: {emotion} | Intensity: {intensity:.0%}")

    # FIX 4: Skip entirely on no_action strategy (chitchat/neutral gate)
    # No micro-actions should fire on grocery lists or casual conversation.
    if strategy == "no_action":
        print(f"[NODE: ACTIVATION] ⏭️  Skipping (strategy: no_action — casual conversation, no intervention)")
        return _empty_activation()

    # Only recommend actions when strategy warrants it
    if strategy == "ask_question":
        print(f"[NODE: ACTIVATION] ⏭️  Skipping (strategy: ask_question — user still opening up)")
        return _empty_activation()

    # Determine time of day
    current_hour = datetime.datetime.now().hour
    is_daytime = 7 <= current_hour <= 21
    time_context = "daytime" if is_daytime else "night"

    # Determine intensity band
    if intensity >= 0.65:
        intensity_band = "high"
    elif intensity >= 0.35:
        intensity_band = "medium"
    else:
        intensity_band = "low"

    # Try exact emotion + intensity lookup
    candidates = _get_candidates(emotion, intensity_band)

    # Filter by time of day
    time_filtered = [c for c in candidates if c["time"] == "any" or c["time"] == time_context]
    if not time_filtered:
        time_filtered = candidates  # fallback: remove filter if nothing matches

    if not time_filtered:
        time_filtered = FALLBACK_ACTIONS

    # Profile-based ordering: avoidant coping → prefer lowest-effort action
    coping_style = psych_profile.get("coping_style", "mixed")
    if coping_style == "avoidant":
        # Sort by action length as a simple proxy for effort (shorter = simpler)
        time_filtered = sorted(time_filtered, key=lambda c: len(c["action"]))
    elif coping_style == "proactive":
        # Proactive users get slightly more challenging, impactful actions (longer = richer)
        time_filtered = sorted(time_filtered, key=lambda c: len(c["action"]), reverse=True)

    best = time_filtered[0]

    print(f"[NODE: ACTIVATION] ✅ Action: '{best['action'][:60]}...' (category: {best['category']})")

    return {
        "micro_action":           best["action"],
        "micro_action_rationale": best["rationale"],
        "micro_action_category":  best["category"],
    }


def _get_candidates(emotion: str, intensity_band: str) -> list[dict]:
    """Look up activation matrix with fallback to 'any' intensity."""
    # Exact match
    key = (emotion, intensity_band)
    if key in ACTIVATION_MATRIX:
        return ACTIVATION_MATRIX[key]

    # Fall back to 'any' intensity for this emotion
    any_key = (emotion, "any")
    if any_key in ACTIVATION_MATRIX:
        return ACTIVATION_MATRIX[any_key]

    # Fall back to medium for this emotion
    medium_key = (emotion, "medium")
    if medium_key in ACTIVATION_MATRIX:
        return ACTIVATION_MATRIX[medium_key]

    return FALLBACK_ACTIONS


def _empty_activation() -> dict:
    return {
        "micro_action":           None,
        "micro_action_rationale": None,
        "micro_action_category":  None,
    }
