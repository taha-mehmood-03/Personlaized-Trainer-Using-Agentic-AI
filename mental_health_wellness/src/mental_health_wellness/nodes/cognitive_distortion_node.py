"""
Cognitive Distortion Detector Node (Node 2b) - SentiMind v3.0

ARCHITECTURE NODE 2b:
Purpose: Detect cognitive distortions (maladaptive thinking patterns) from user language.
         This enables the conversation planner to choose a 'reframe' strategy and the
         LLM to be explicitly instructed to address the specific distortion type.

Runs AFTER emotion_fusion_node, BEFORE conversation_planner_node.
No LLM call — pure deterministic keyword/pattern analysis.

DISTORTION TYPES DETECTED:
  - catastrophizing:     "always", "never", "everything is ruined", "hopeless"
  - black_white:         "total failure", "completely useless", "perfect", "100% bad"
  - overgeneralization:  "always happens to me", "nobody", "everyone hates me"
  - mind_reading:        "they think", "he must think i'm", "she sees me as"
  - personalization:     "it's my fault", "i caused this", "because of me"
  - should_statements:   "i must", "i should", "i have to", "i ought to"
  - emotional_reasoning: "i feel like it's true", "i know it's bad because i feel awful"
  - magnification:       "the worst thing", "unbearable", "i can't handle this"

OUTPUT STATE FIELDS:
  - distortion_type:        str | None
  - distortion_confidence:  float (0.0-1.0)
  - distortion_explanation: str | None
  - all_distortions:        list[str]
"""

from ..agent.state import MentalHealthState


# ============================================
# DISTORTION PATTERN LEXICONS
# ============================================

DISTORTION_PATTERNS: dict[str, list[str]] = {
    "catastrophizing": [
        "always", "never", "everything is", "nothing ever", "ruined",
        "hopeless", "disaster", "worst ever", "it's all over", "completely destroyed",
        "nothing will", "my whole life", "doomed", "total disaster",
    ],
    "black_white": [
        "total failure", "complete failure", "completely useless", "absolutely worthless",
        "perfect", "100% bad", "not at all", "entirely wrong", "always right",
        "never works", "either it works or", "all or nothing",
    ],
    "overgeneralization": [
        "always happens to me", "this always happens", "nobody", "everyone hates",
        "people always", "they always", "i always mess", "every time i try",
        "it never works out", "no one ever", "everyone thinks", "every single time",
    ],
    "mind_reading": [
        "they think", "he must think", "she thinks i'm", "people see me as",
        "everyone knows i'm", "they probably think", "i know they think",
        "they must be laughing", "she must hate", "he must think i'm",
        "i could tell they thought", "they assumed",
    ],
    "personalization": [
        "my fault", "it's my fault", "i caused", "because of me", "i made them",
        "i'm to blame", "it's all on me", "i ruined it", "i did this",
        "this happened because of me", "it wouldn't have happened if i",
    ],
    "should_statements": [
        "i should", "i must", "i have to", "i ought to", "i need to be",
        "i should have", "i must not", "i can't", "i shouldn't have",
        "one should", "people should", "they should",
    ],
    "emotional_reasoning": [
        "i feel like it's true", "it must be bad because i feel",
        "i just feel it", "i feel so", "my feelings prove",
        "i feel worthless so i must be", "because i feel scared",
        "since i feel anxious it means",
    ],
    "magnification": [
        "the worst thing", "unbearable", "i can't handle", "i can't cope",
        "too much to bear", "overwhelming", "i can't take it", "so bad i",
        "it's unbearable", "devastating", "this is destroying me",
    ],
}

# Weight by clinical importance (catastrophizing and black/white are highest priority)
DISTORTION_WEIGHTS: dict[str, float] = {
    "catastrophizing":     1.0,
    "black_white":         0.9,
    "mind_reading":        0.85,
    "personalization":     0.85,
    "overgeneralization":  0.80,
    "should_statements":   0.70,
    "magnification":       0.75,
    "emotional_reasoning": 0.65,
}

DISTORTION_EXPLANATIONS: dict[str, str] = {
    "catastrophizing":    "User uses absolute language suggesting the worst possible outcome is inevitable.",
    "black_white":        "User's language reflects all-or-nothing thinking with no middle ground.",
    "overgeneralization": "User overgeneralizes a single event into a universal pattern about themselves or others.",
    "mind_reading":       "User assumes they know what others are thinking without real evidence.",
    "personalization":    "User takes excessive personal responsibility for things outside their full control.",
    "should_statements":  "User places rigid, inflexible rules on themselves using 'should/must/have to' language.",
    "emotional_reasoning":"User treats their emotional state as objective proof of external reality.",
    "magnification":      "User significantly magnifies the severity or impact of a situation.",
}


# ============================================
# MAIN NODE FUNCTION
# ============================================

def cognitive_distortion_node(state: MentalHealthState) -> dict:
    """
    COGNITIVE DISTORTION DETECTOR — Pure deterministic pattern analysis.

    Process:
    1. Extract user's message text
    2. Scan against all distortion pattern lexicons
    3. Score by match count × distortion weight
    4. Return primary + secondary distortions

    No LLM involved. ~<50ms per message.
    """
    messages = state.get("messages", [])
    if not messages:
        return _no_distortion_result()

    user_message = messages[-1].content.lower()

    # Skip very short messages — distortions need context
    if len(user_message.split()) < 4:
        return _no_distortion_result()

    print(f"\n[NODE: DISTORTION] 🧠 Scanning for cognitive distortions...")

    # ============================================
    # SCORE EACH DISTORTION TYPE
    # ============================================
    distortion_scores: dict[str, float] = {}

    for distortion_type, patterns in DISTORTION_PATTERNS.items():
        match_count = sum(1 for pattern in patterns if pattern in user_message)
        if match_count > 0:
            # Score = (matches / total_patterns) × weight × bonus for multiple matches
            base_score = match_count / len(patterns)
            multi_match_bonus = min(0.2, (match_count - 1) * 0.1)
            raw_score = (base_score + multi_match_bonus) * DISTORTION_WEIGHTS[distortion_type]
            distortion_scores[distortion_type] = min(1.0, raw_score * 3.0)  # scale up for readability

    if not distortion_scores:
        print(f"[NODE: DISTORTION] ✅ No distortions detected")
        return _no_distortion_result()

    # Sort by score descending
    sorted_distortions = sorted(distortion_scores.items(), key=lambda x: x[1], reverse=True)
    primary_type, primary_confidence = sorted_distortions[0]
    all_distortions = [d[0] for d in sorted_distortions if d[1] > 0.1]

    print(f"[NODE: DISTORTION] ⚠️  Primary: {primary_type.upper()} (conf: {primary_confidence:.0%})")
    if len(all_distortions) > 1:
        print(f"[NODE: DISTORTION] 🔍 Also detected: {', '.join(all_distortions[1:])}")

    return {
        "distortion_type":        primary_type,
        "distortion_confidence":  round(primary_confidence, 3),
        "distortion_explanation": DISTORTION_EXPLANATIONS.get(primary_type, ""),
        "all_distortions":        all_distortions,
    }


def _no_distortion_result() -> dict:
    return {
        "distortion_type":        None,
        "distortion_confidence":  0.0,
        "distortion_explanation": None,
        "all_distortions":        [],
    }
