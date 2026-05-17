"""
Analysis & Planning Fused Node  SentiMind v6.0 Latency Optimization

Merges 4 separate graph nodes into a SINGLE LangGraph node to eliminate
4 checkpoint serialization events per message (~1-2s total saving).

Sub-nodes called INLINE (not as separate graph nodes):
  1. emotion_fusion_node      merge text + voice emotion     (sync, <1ms)
  2. parallel_analysis_node   distortion + trend (||)        (async, ~50-300ms)
     + clinical_severity      PHQ-9/GAD-7 LLM check (||)    (async, ~300-500ms, v9.0 NEW)
  3. conversation_planner     deterministic strategy          (async, <1ms usually)
  4. behavioral_activation    micro-action lookup             (sync, <1ms)

Each sub-node reads from state + all preceding sub-node outputs (merged).
All original logging is preserved  you still see [NODE: EMISSION_FUSION] etc.

WHY THIS IS SAFE:
  The sub-nodes were already sequential in the graph (not parallel).
  They just happened to each be a separate LangGraph node triggering a
  checkpoint event. Calling them inline is functionally identical but
  avoids 4 checkpoint serialization cycles.
"""

import asyncio
from ..agent.state import MentalHealthState
from .emotion_fusion_node import fuse_emotions
from .parallel_analysis import run_parallel_analysis
from .conversation_planner_node import conversation_planner_node
from .behavioral_activation_node import activate_behavioral_intervention
from .clinical_aggregator import aggregate_clinical_assessment


async def run_analysis_and_planning(state: MentalHealthState) -> dict:
    """
    FUSED NODE: emotion_fusion + parallel_analysis + clinical_severity + planner + activation.

    Runs all sub-nodes inline and merges their state updates into a
    single return dict. This eliminates 4 LangGraph checkpoint events.

    Returns: merged dict of all sub-nodes' outputs.
    """
    print("\n[NODE: ANALYSIS_AND_PLANNING]  Running fused pipeline (4 sub-nodes inline)...")

    merged = {}

    #  1. Emotion Fusion (sync, <1ms) 
    # Reads: emotion, intensity, voice_features from state
    # Writes: fused_emotion, fused_intensity
    try:
        fusion_result = fuse_emotions(state)
        merged.update(fusion_result)
    except Exception as e:
        print(f"[ANALYSIS_AND_PLANNING]  Emotion fusion failed: {str(e)[:100]}")
        merged.update({"fused_emotion": state.get("emotion", "neutral"), "fused_intensity": state.get("intensity", 0.5)})

    # Create merged state view so downstream sub-nodes see fusion results
    state_after_fusion = {**state, **merged}

    #  2. Parallel Analysis: distortion + trend + clinical severity (async)
    # Reads: fused_emotion, fused_intensity, user_id, messages
    # Writes: distortion_type, distortion_confidence, emotional_trend, trend_window
    #         + clinical_severity, clinical_phq9_score, clinical_gad7_score, clinical_indicators
    #
    # OPTIMIZATION: Cognitive distortion detection (LLM call) is only useful
    # when strategy may become "reframe". For technique_request, advice_seeking,
    # and chitchat intents the planner will NEVER choose "reframe", so skip it.
    prefetched_intent = state_after_fusion.get("prefetched_intent", {})
    _intent_val = prefetched_intent.get("intent", "venting") if isinstance(prefetched_intent, dict) else "venting"
    _skip_distortion_intents = {"technique_request", "advice_seeking", "chitchat", "crisis_signal"}
    
    # Get user message count from state or calculate from messages array
    session_msg_count = state_after_fusion.get("session_message_count", 0)
    messages = state_after_fusion.get("messages", [])
    user_msg_count = max(
        session_msg_count,
        sum(1 for m in messages if getattr(m, "type", "") == "human")
    )
    
    # Skip distortion if intent doesn't need it, or if it's too early in the conversation
    # (distortions require context and early turns are purely venting/validation)
    skip_distortion = (_intent_val in _skip_distortion_intents) or (user_msg_count <= 2)

    # v9.1: Clinical screening is independent from distortion detection.
    # A first-turn message can contain clinically important evidence, so do not
    # skip clinical just because distortion is skipped for early conversation.
    _skip_clinical_intents = {"chitchat", "technique_request"}
    _skip_clinical = _intent_val in _skip_clinical_intents

    clinical_task = None
    if not _skip_clinical:
        try:
            from ..llm.llm_classifier import clinical_severity_check

            _recent_msgs = messages[-5:] if len(messages) > 4 else messages
            _clinical_ctx_lines = []
            for m in _recent_msgs[:-1]:  # exclude current message (passed separately)
                role = "User" if getattr(m, "type", "") == "human" else "Assistant"
                _clinical_ctx_lines.append(f"{role}: {getattr(m, 'content', '')}")
            _clinical_context = "\n".join(_clinical_ctx_lines[-4:])
            user_msg = messages[-1].content if messages else ""

            # Start the clinical LLM call now so it overlaps with trend/distortion
            # analysis. It only needs the fused current-turn emotion, so waiting for
            # trend first was unnecessary critical-path latency.
            clinical_task = asyncio.create_task(clinical_severity_check(
                message=user_msg,
                recent_context=_clinical_context,
                emotion=state_after_fusion.get("fused_emotion", state.get("emotion", "neutral")),
                intensity=state_after_fusion.get("fused_intensity", state.get("intensity", 0.5)),
                emotional_trend=state.get("emotional_trend", "stable"),
            ))
        except Exception as e:
            print(f"[ANALYSIS_AND_PLANNING]  Clinical task setup failed: {str(e)[:100]}")
            clinical_task = None

    if skip_distortion:
        skip_reason = f"intent={_intent_val}" if _intent_val in _skip_distortion_intents else f"early_turn={user_msg_count}"
        print(f"[ANALYSIS_AND_PLANNING]   Distortion detection SKIPPED ({skip_reason})")
        # Still run trend analysis  it's a cheap DB query and always useful
        try:
            from .trend_analyzer_node import analyze_emotional_trends
            trend_result = await analyze_emotional_trends(state_after_fusion)
            merged.update(trend_result)
        except Exception as e:
            print(f"[ANALYSIS_AND_PLANNING]  Trend analysis failed: {str(e)[:100]}")
            merged.update({"emotional_trend": "stable", "trend_window": []})
        merged.update({
            "distortion_type": None, "distortion_confidence": 0.0,
            "distortion_explanation": None, "all_distortions": [],
        })
    else:
        try:
            analysis_result = await run_parallel_analysis(state_after_fusion)
            merged.update(analysis_result)
        except Exception as e:
            print(f"[ANALYSIS_AND_PLANNING]  Parallel analysis failed: {str(e)[:100]}")
            merged.update({
                "distortion_type": None, "distortion_confidence": 0.0,
                "distortion_explanation": None, "all_distortions": [],
                "emotional_trend": "stable", "trend_window": [],
            })

    # v9.0: Clinical severity check. The current-turn LLM call was started
    # above and has been running while trend/distortion analysis completed.
    if not _skip_clinical:
        try:
            if clinical_task is None:
                raise RuntimeError("clinical task was not created")

            current_clinical_result = await clinical_task

            clinical_result = await aggregate_clinical_assessment(
                user_id=state_after_fusion.get("user_id", ""),
                current=current_clinical_result,
            )

            merged.update({
                "clinical_severity": clinical_result.get("severity", "minimal"),
                "clinical_phq9_score": clinical_result.get("phq9_total", 0),
                "clinical_gad7_score": clinical_result.get("gad7_total", 0),
                "clinical_indicators": clinical_result.get("clinical_indicators", []),
                "clinical_confidence": clinical_result.get("confidence", 0.0),
            })
            print(f"[ANALYSIS_AND_PLANNING] Clinical severity: {merged['clinical_severity'].upper()} "
                  f"(PHQ-9={merged['clinical_phq9_score']}, GAD-7={merged['clinical_gad7_score']}) "
                  f"| source={clinical_result.get('aggregation_source')} "
                  f"| history={clinical_result.get('history_count', 0)}")

        except Exception as e:
            print(f"[ANALYSIS_AND_PLANNING]  Clinical severity check failed: {str(e)[:100]}")
            merged.update({
                "clinical_severity": "minimal",
                "clinical_phq9_score": 0,
                "clinical_gad7_score": 0,
                "clinical_indicators": [],
                "clinical_confidence": 0.0,
            })
    else:
        print(f"[ANALYSIS_AND_PLANNING]   Clinical severity SKIPPED (non-therapeutic turn)")

    state_after_analysis = {**state, **merged}

    #  3. Conversation Planner (async, typically <1ms  may call LLM as fallback) 
    # Reads: fused_emotion, fused_intensity, emotional_trend, messages, prefetched_intent
    # Writes: conversation_strategy, conversation_phase, technique_readiness
    try:
        planner_result = await conversation_planner_node(state_after_analysis)
        merged.update(planner_result)
    except Exception as e:
        print(f"[ANALYSIS_AND_PLANNING]  Conversation planner failed: {str(e)[:100]}")
        merged.update({
            "conversation_strategy": "validate_only",
            "conversation_phase": "venting",
            "technique_readiness": 0.0,
        })

    state_after_planner = {**state, **merged}
    strategy = merged.get("conversation_strategy", "validate_only")

    #  4. Behavioral Activation (sync, <1ms) 
    # Skipped for no_action (chitchat)  no micro-actions for casual conversation
    # Reads: fused_emotion, fused_intensity, conversation_strategy, psych_profile
    # Writes: micro_action, micro_action_rationale, micro_action_category
    if strategy != "no_action":
        try:
            activation_result = activate_behavioral_intervention(state_after_planner)
            merged.update(activation_result)
        except Exception as e:
            print(f"[ANALYSIS_AND_PLANNING]  Behavioral activation failed: {str(e)[:100]}")
            merged.update({"micro_action": None, "micro_action_rationale": None, "micro_action_category": None})
    else:
        merged.update({"micro_action": None, "micro_action_rationale": None, "micro_action_category": None})

    print(f"[NODE: ANALYSIS_AND_PLANNING]  Fused complete | "
          f"Emotion: {merged.get('fused_emotion', '?')} | "
          f"Strategy: {merged.get('conversation_strategy', '?')} | "
          f"Trend: {merged.get('emotional_trend', '?')} | "
          f"Clinical: {merged.get('clinical_severity', 'N/A').upper()}")

    return merged

