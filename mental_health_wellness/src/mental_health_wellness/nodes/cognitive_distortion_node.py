"""
Cognitive Distortion Detector Node (Node 2b) — v8.0 Deterministic Keyword Engine

ARCHITECTURE NODE 2b:
Purpose: Detect cognitive distortions (maladaptive thinking patterns) using a
         deterministic keyword/phrase pattern engine.

Runs AFTER emotion_fusion_node, BEFORE conversation_planner_node.

v8.0 CHANGES (latency optimisation):
  - Removed LLM call entirely — zero network roundtrip, ~0ms latency
  - Pattern-matched keyword engine covers all 8 CBT distortion types
  - Confidence derived from hit density (number of matching phrases)
  - Falls back cleanly to no-distortion for low-signal messages

DISTORTION TYPES DETECTED:
  - catastrophizing:     Expecting worst possible outcome is inevitable
  - black_white:         All-or-nothing thinking with no middle ground
  - overgeneralization:  Single event becomes universal pattern
  - mind_reading:        Assuming knowledge of others' thoughts
  - personalization:     Excessive personal responsibility
  - should_statements:   Rigid, inflexible rules on oneself
  - emotional_reasoning: Treating emotions as objective proof
  - magnification:       Significantly magnifying severity/impact

OUTPUT STATE FIELDS:
  - distortion_type:        str | None
  - distortion_confidence:  float (0.0-1.0)
  - distortion_explanation: str | None
  - all_distortions:        list[str]
"""

from ..agent.state import MentalHealthState


# ============================================================
# DETERMINISTIC DISTORTION PATTERN ENGINE
# Each entry is a list of phrases/substrings that strongly signal
# that specific distortion type in user messages.
# ============================================================
_DISTORTION_PATTERNS: dict[str, list[str]] = {
    "catastrophizing": [
        "will fail", "going to fail", "going to be terrible", "ruin everything",
        "disaster", "never recover", "completely fail", "everything will go wrong",
        "end of the world", "worst thing ever", "nothing will ever work",
        "it's all going to fall apart", "life is over", "everything is ruined",
        "will never be okay", "pointless now", "no way out", "nothing will get better",
    ],
    "black_white": [
        "always wrong", "always do this", "never does", "never works for me",
        "complete failure", "total failure", "either i", "all or nothing",
        "nothing right", "everything wrong", "completely useless", "totally useless",
        "never good enough", "always mess up", "always messed up", "always the problem",
        "if i'm not perfect", "perfect or", "all bad", "either perfect",
    ],
    "overgeneralization": [
        "this always happens", "it always happens to me", "always happen",
        "never works", "it never works", "things never", "nothing ever works",
        "this is always the case", "it's always me", "always the same",
        "every single time", "every time i try", "nothing ever goes right",
        "all my relationships", "all my attempts", "always end up",
    ],
    "mind_reading": [
        "they think i", "they hate me", "everyone thinks", "i know they",
        "they must think", "people think i", "they're judging", "they all think",
        "she thinks i", "he thinks i", "they probably think", "i bet they hate",
        "everyone can tell", "they noticed", "they all noticed", "they saw",
        "they know i", "i could tell they",
    ],
    "personalization": [
        "it's my fault", "my fault", "i ruined it", "i ruined everything",
        "because of me", "i caused this", "it happened because i",
        "all my fault", "i'm to blame", "i made this happen",
        "i brought this on", "i let everyone down", "i failed everyone",
    ],
    "should_statements": [
        "i should", "i must be", "i have to be", "i need to be stronger",
        "i ought to", "should be better", "must be stronger",
        "have to be perfect", "should know better", "must do better",
        "i should have", "i shouldn't feel", "i should not feel",
        "i'm supposed to", "i need to handle", "people like me should",
    ],
    "emotional_reasoning": [
        "i feel stupid so", "i feel like a failure", "i feel worthless",
        "i feel it therefore", "i feel it so it must", "because i feel",
        "i feel like everyone", "i feel like nobody", "i feel like i'm",
        "it feels real so", "if i feel anxious", "since i feel this way",
    ],
    "magnification": [
        "ruined my entire", "worst ever", "absolutely terrible",
        "completely destroyed", "absolutely ruined", "the absolute worst",
        "catastrophic", "unbearable", "completely overwhelmed by",
        "devastating", "shattered everything", "destroyed everything",
        "ruined my whole", "the biggest failure",
    ],
}

# Human-readable explanation template for each detected distortion
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


def _detect_distortion_keywords(message: str) -> dict:
    """
    Deterministic, zero-latency cognitive distortion detector.

    Scans the normalised message for phrase-level pattern hits across all 8 CBT
    distortion types. Confidence is proportional to the number of phrase hits so
    that single incidental words don't inflate the score.

    Returns the same shape as the old llm_distortion_check output so all
    downstream consumers (planner, response generator, technique selector)
    continue to work without modification.
    """
    lower = message.lower()
    hits: dict[str, int] = {}
    for dtype, patterns in _DISTORTION_PATTERNS.items():
        count = sum(1 for p in patterns if p in lower)
        if count > 0:
            hits[dtype] = count

    if not hits:
        return {
            "distortion_type": None,
            "distortion_confidence": 0.0,
            "distortion_explanation": None,
            "all_distortions": [],
        }

    # Pick the type with the most phrase hits as primary
    primary = max(hits, key=hits.get)
    all_distortions = sorted(hits, key=hits.get, reverse=True)
    # Confidence: base 0.55 + 0.10 per additional hit, capped at 0.92
    confidence = min(0.55 + 0.10 * (hits[primary] - 1), 0.92)

    return {
        "distortion_type": primary,
        "distortion_confidence": round(confidence, 2),
        "distortion_explanation": DISTORTION_EXPLANATIONS.get(primary, ""),
        "all_distortions": all_distortions,
    }


# ============================================
# MAIN NODE FUNCTION
# ============================================

async def detect_cognitive_distortions(state: MentalHealthState) -> dict:
    """
    COGNITIVE DISTORTION DETECTOR — Deterministic Keyword Engine (v8.0).

    Process:
    1. Extract user's message text
    2. Apply phrase-level keyword patterns across all 8 CBT distortion types
    3. Return primary + secondary distortions with confidence

    Zero LLM calls — ~0ms latency, no network dependency.
    """
    messages = state.get("messages", [])
    if not messages:
        return _no_distortion_result()

    user_message = messages[-1].content

    # Skip very short messages — distortions need context
    if len(user_message.split()) < 4:
        return _no_distortion_result()

    emotion = state.get("fused_emotion", state.get("emotion", "neutral"))
    intensity = state.get("fused_intensity", state.get("intensity", 0.5))

    # CHITCHAT/POSITIVE BYPASS: skip for clearly non-distress turns
    if emotion in ["neutral", "joy", "surprise"] and intensity < 0.3:
        print(f"[NODE: DISTORTION]  Skipping (positive/neutral: {emotion} {intensity:.0%})")
        return _no_distortion_result()

    # ============================================
    # DETERMINISTIC KEYWORD DETECTION (~0ms)
    # ============================================
    result = _detect_distortion_keywords(user_message)

    if result.get("distortion_type"):
        primary = result["distortion_type"]
        conf = result["distortion_confidence"]
        others = result["all_distortions"][1:]
        print(f"[NODE: DISTORTION]  Detected: {primary} ({conf:.0%}) [keyword engine]")
        if others:
            print(f"[NODE: DISTORTION]  Also found: {', '.join(others)}")
        return result

    print("[NODE: DISTORTION]  No cognitive distortions detected")
    return _no_distortion_result()


def _no_distortion_result() -> dict:
    return {
        "distortion_type":        None,
        "distortion_confidence":  0.0,
        "distortion_explanation": None,
        "all_distortions":        [],
    }
