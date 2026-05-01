"""
Analysis & Planning Fused Node — SentiMind v6.0 Latency Optimization

Merges 4 separate graph nodes into a SINGLE LangGraph node to eliminate
4 checkpoint serialization events per message (~1-2s total saving).

Sub-nodes called INLINE (not as separate graph nodes):
  1. emotion_fusion_node     — merge text + voice emotion     (sync, <1ms)
  2. parallel_analysis_node  — distortion + trend (||)        (async, ~50-300ms)
  3. conversation_planner    — deterministic strategy          (async, <1ms usually)
  4. behavioral_activation   — micro-action lookup             (sync, <1ms)

Each sub-node reads from state + all preceding sub-node outputs (merged).
All original logging is preserved — you still see [NODE: EMISSION_FUSION] etc.

WHY THIS IS SAFE:
  The sub-nodes were already sequential in the graph (not parallel).
  They just happened to each be a separate LangGraph node triggering a
  checkpoint event. Calling them inline is functionally identical but
  avoids 4 checkpoint serialization cycles.
"""

from ..agent.state import MentalHealthState
from .emotion_fusion_node import fuse_emotions
from .parallel_analysis import run_parallel_analysis
from .conversation_planner_node import conversation_planner_node
from .behavioral_activation_node import activate_behavioral_intervention


async def run_analysis_and_planning(state: MentalHealthState) -> dict:
    """
    FUSED NODE: emotion_fusion + parallel_analysis + planner + activation.

    Runs all 4 sub-nodes inline and merges their state updates into a
    single return dict. This eliminates 4 LangGraph checkpoint events.

    Returns: merged dict of all 4 sub-nodes' outputs.
    """
    print("\n[NODE: ANALYSIS_AND_PLANNING] ⚡ Running fused pipeline (4 sub-nodes inline)...")

    merged = {}

    # ── 1. Emotion Fusion (sync, <1ms) ──────────────────────────────────
    # Reads: emotion, intensity, voice_features from state
    # Writes: fused_emotion, fused_intensity
    try:
        fusion_result = fuse_emotions(state)
        merged.update(fusion_result)
    except Exception as e:
        print(f"[ANALYSIS_AND_PLANNING] ⚠️ Emotion fusion failed: {str(e)[:100]}")
        merged.update({"fused_emotion": state.get("emotion", "neutral"), "fused_intensity": state.get("intensity", 0.5)})

    # Create merged state view so downstream sub-nodes see fusion results
    state_after_fusion = {**state, **merged}

    # ── 2. Parallel Analysis: distortion + trend (async, ~50-300ms) ─────
    # Reads: fused_emotion, fused_intensity, user_id, messages
    # Writes: distortion_type, distortion_confidence, emotional_trend, trend_window
    try:
        analysis_result = await run_parallel_analysis(state_after_fusion)
        merged.update(analysis_result)
    except Exception as e:
        print(f"[ANALYSIS_AND_PLANNING] ⚠️ Parallel analysis failed: {str(e)[:100]}")
        merged.update({
            "distortion_type": None, "distortion_confidence": 0.0,
            "distortion_explanation": None, "all_distortions": [],
            "emotional_trend": "stable", "trend_window": [],
        })

    state_after_analysis = {**state, **merged}

    # ── 3. Conversation Planner (async, typically <1ms — may call LLM as fallback) ───
    # Reads: fused_emotion, fused_intensity, emotional_trend, messages, prefetched_intent
    # Writes: conversation_strategy, conversation_phase, technique_readiness
    try:
        planner_result = await conversation_planner_node(state_after_analysis)
        merged.update(planner_result)
    except Exception as e:
        print(f"[ANALYSIS_AND_PLANNING] ⚠️ Conversation planner failed: {str(e)[:100]}")
        merged.update({
            "conversation_strategy": "validate_only",
            "conversation_phase": "venting",
            "technique_readiness": 0.0,
        })

    state_after_planner = {**state, **merged}
    strategy = merged.get("conversation_strategy", "validate_only")

    # ── 4. Behavioral Activation (sync, <1ms) ──────────────────────────
    # Skipped for no_action (chitchat) — no micro-actions for casual conversation
    # Reads: fused_emotion, fused_intensity, conversation_strategy, psych_profile
    # Writes: micro_action, micro_action_rationale, micro_action_category
    if strategy != "no_action":
        try:
            activation_result = activate_behavioral_intervention(state_after_planner)
            merged.update(activation_result)
        except Exception as e:
            print(f"[ANALYSIS_AND_PLANNING] ⚠️ Behavioral activation failed: {str(e)[:100]}")
            merged.update({"micro_action": None, "micro_action_rationale": None, "micro_action_category": None})
    else:
        merged.update({"micro_action": None, "micro_action_rationale": None, "micro_action_category": None})

    print(f"[NODE: ANALYSIS_AND_PLANNING] ✅ Fused complete | "
          f"Emotion: {merged.get('fused_emotion', '?')} | "
          f"Strategy: {merged.get('conversation_strategy', '?')} | "
          f"Trend: {merged.get('emotional_trend', '?')}")

    return merged
