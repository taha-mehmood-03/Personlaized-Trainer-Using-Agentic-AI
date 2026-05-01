"""
Cognitive Distortion Detector Node (Node 2b) - v7.0 LLM-Based

ARCHITECTURE NODE 2b:
Purpose: Detect cognitive distortions (maladaptive thinking patterns) using LLM semantic analysis.
         This enables the conversation planner to choose a 'reframe' strategy and the
         LLM to be explicitly instructed to address the specific distortion type.

Runs AFTER emotion_fusion_node, BEFORE conversation_planner_node.

v7.0 CHANGES:
  - Removed keyword pattern matching entirely
  - LLM semantic analysis for accurate distortion detection
  - Understands context and nuance better than keywords
  - Consistent with therapeutic standards

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
from ..llm.llm_classifier import llm_distortion_check


# Distortion explanations for reference
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

async def detect_cognitive_distortions(state: MentalHealthState) -> dict:
    """
    COGNITIVE DISTORTION DETECTOR — LLM-Based Analysis (v7.0).

    Process:
    1. Extract user's message text
    2. Use LLM semantic understanding to detect distortions
    3. Return primary + secondary distortions with confidence

    LLM provides nuanced, context-aware analysis.
    """
    messages = state.get("messages", [])
    if not messages:
        return _no_distortion_result()

    user_message = messages[-1].content.lower()

    # Skip very short messages — distortions need context
    if len(user_message.split()) < 4:
        return _no_distortion_result()

    emotion = state.get("fused_emotion", state.get("emotion", "neutral"))
    intensity = state.get("fused_intensity", state.get("intensity", 0.5))
    
    # CHITCHAT/POSITIVE BYPASS: If emotion is neutral or positive
    # with low intensity, skip the LLM call entirely for efficiency
    if emotion in ["neutral", "joy", "surprise"] and intensity < 0.3:
        print(f"[NODE: DISTORTION] ⏩ Skipping distortion check (positive/neutral mood: {emotion} {intensity:.0%})")
        return _no_distortion_result()

    print(f"\n[NODE: DISTORTION] 🧠 Analyzing for cognitive distortions using LLM...")

    # ============================================
    # LLM-BASED DISTORTION DETECTION
    # ============================================
    llm_result = await llm_distortion_check(user_message)
    
    if llm_result.get("distortion_type"):
        print(f"[NODE: DISTORTION] ✅ Detected: {llm_result['distortion_type']} ({llm_result.get('confidence', 0):.0%})")
        if llm_result.get("all_distortions") and len(llm_result["all_distortions"]) > 1:
            print(f"[NODE: DISTORTION] 🔍 Also found: {', '.join(llm_result['all_distortions'][1:])}")
        
        return {
            "distortion_type":        llm_result.get("distortion_type"),
            "distortion_confidence":  llm_result.get("confidence", 0.5),
            "distortion_explanation": llm_result.get("explanation", ""),
            "all_distortions":        llm_result.get("all_distortions", []),
        }
    
    print(f"[NODE: DISTORTION] ✅ No cognitive distortions detected")
    return _no_distortion_result()


def _no_distortion_result() -> dict:
    return {
        "distortion_type":        None,
        "distortion_confidence":  0.0,
        "distortion_explanation": None,
        "all_distortions":        [],
    }
