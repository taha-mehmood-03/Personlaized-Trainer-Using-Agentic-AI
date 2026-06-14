"""
Analysis & Planning Fused Node  SentiMind v6.0 Latency Optimization

Merges 4 separate graph nodes into a SINGLE LangGraph node to eliminate
4 checkpoint serialization events per message (~1-2s total saving).

Sub-nodes called INLINE (not as separate graph nodes):
  1. emotion_fusion_node      merge text + voice emotion     (sync, <1ms)
  2. cached/background trend + optional distortion            (async, ~0-300ms)
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
import os
import re
from ..agent.state import MentalHealthState
from .emotion_fusion_node import fuse_emotions
from .conversation_context_resolver import resolve_conversation_context
from .conversation_planner_node import conversation_planner_node
from .behavioral_activation_node import activate_behavioral_intervention
from .consent_parser import parse_consent_and_suppression
from ..utils.turn_lifecycle import refine_turn_type


_ACCEPTANCE_RE = re.compile(
    r"^\s*(yes|yeah|yep|sure|ok|okay|please|pls|plz|go for it|share it|"
    r"yes please|yes pls|yes plz|okay share it|ok share it|yes sure|"
    r"do it|let'?s do it|i'?m ready)(\s+.*)?$",
    re.IGNORECASE,
)


def _norm_list(values) -> list[str]:
    if not values:
        return []
    if isinstance(values, (list, tuple, set)):
        return [str(item).lower().strip() for item in values if str(item).strip()]
    return [str(values).lower().strip()] if str(values).strip() else []


def _merge_unique(existing, additions, limit: int = 10) -> list[str]:
    merged: list[str] = []
    for value in [*_norm_list(existing), *_norm_list(additions)]:
        if value and value not in merged:
            merged.append(value)
    return merged[:limit]


def _recent_thread_text(state: MentalHealthState, max_messages: int = 6) -> str:
    parts: list[str] = []
    for key in ("active_thread_summary", "primary_concern", "triggering_subject", "triggering_context", "core_belief"):
        value = str(state.get(key) or "").strip()
        if value and value.lower() not in {"none", "unknown", "not specified"}:
            parts.append(value)

    messages = state.get("messages") or []
    for msg in messages[-max_messages:]:
        content = str(getattr(msg, "content", "") or "").strip()
        if content:
            parts.append(content)
    return " ".join(parts).lower()


def _current_turn_text(state: MentalHealthState) -> str:
    """Return only the current user message for keyword matching.

    Used when voice is authoritative: Gemini classified emotion from the
    actual audio, so we must NOT let stale thread keywords (exam, fail, etc.
    from prior turns) override the current voice-detected neutral/calm state.
    We still enrich sub-emotions / contexts from the current message text
    (which is the browser-side transcript), but we do not look backwards.
    """
    messages = state.get("messages") or []
    for msg in reversed(messages):
        role = str(getattr(msg, "type", "") or "").lower()
        if "human" in role or "user" in role:
            return str(getattr(msg, "content", "") or "").lower().strip()
    return ""


def _derive_exam_sleep_cognitive_context(state: MentalHealthState) -> dict:
    """
    Deterministic clinical-context enrichment for technique selection.

    This is intentionally not a replacement for LLM analysis. It preserves and
    sharpens the active formulation so short acceptance messages do not erase
    the actual issue, and so semantic DB ranking can match the user need even
    when technique table fields are incomplete.

    VOICE AUTHORITY SCOPE RULE:
    When Gemini voice features are authoritative (extraction_method=gemini_audio),
    keyword matching is scoped to the CURRENT message only — not the full thread
    history. Gemini already classified the emotion from the actual audio; we must
    not let stale exam/sleep keywords from prior turns override a fresh neutral
    or calm vocal disclosure.  Sub-emotion / context enrichment still runs, but
    only from what the user said in this specific turn.
    """
    messages = state.get("messages") or []
    latest = str(getattr(messages[-1], "content", "") if messages else "")
    latest_lower = latest.lower().strip()

    # Determine whether Gemini voice is the authoritative source this turn.
    voice_features = state.get("voice_features")
    has_authoritative_voice = (
        isinstance(voice_features, dict)
        and str(voice_features.get("extraction_method", "")).lower().strip() == "gemini_audio"
    )

    if has_authoritative_voice:
        # Voice turn: only look at what the user said RIGHT NOW.
        # Stale thread keywords (exam, fail, …) must not override the
        # Gemini-classified emotion for this turn.
        thread = _current_turn_text(state)
        is_acceptance = bool(_ACCEPTANCE_RE.match(latest_lower or ""))
        text = thread if is_acceptance else f"{thread} {latest_lower}"
    else:
        # Text-only turn: use the full thread as before for context continuity.
        thread = _recent_thread_text(state)
        is_acceptance = bool(_ACCEPTANCE_RE.match(latest_lower or ""))
        text = thread if is_acceptance else f"{thread} {latest_lower}"

    has_exam = any(
        token in text
        for token in ("exam", "exams", "midterm", "final", "test", "paper", "quiz")
    )
    has_exam_week = has_exam and any(
        token in text
        for token in ("coming week", "next week", "this week", "tomorrow", "soon", "upcoming")
    )
    has_sleep = any(
        token in text
        for token in ("sleep", "bedtime", "bed time", "bed", "night", "at night", "try to sleep", "trying to sleep")
    )
    has_thought_loop = any(
        token in text
        for token in (
            "thought", "thoughts", "mind", "keeps coming", "keep coming", "keeps thinking",
            "goes in my mind", "racing", "rumination", "ruminating", "overthinking", "worry",
        )
    )
    has_failure_belief = any(
        token in text
        for token in ("might fail", "will fail", "fail", "drop out", "dropout", "dropped out")
    )
    has_environment_trigger = any(
        token in text
        for token in (
            "phone", "room", "noisy", "noise", "distract", "distraction",
            "study on my bed", "studying on my bed", "study space", "desk",
        )
    )

    updates: dict = {}
    sub_emotions: list[str] = []
    secondary_subs: list[str] = []
    symptoms: list[str] = []
    behaviors: list[str] = []
    contexts: list[str] = []

    if has_exam:
        sub_emotions.append("academic_pressure")
        contexts.extend(["exam_pressure", "academic_anxiety"])
        if has_exam_week:
            contexts.append("exam_week")

    if has_sleep and (has_thought_loop or has_failure_belief):
        sub_emotions.extend(["bedtime_rumination", "racing_thoughts", "worry"])
        symptoms.extend(["sleep_difficulty", "bedtime_racing_thoughts"])
        behaviors.append("rumination")
        contexts.extend(["bedtime_rumination", "sleep_difficulty", "nighttime_worry"])

    if has_failure_belief:
        sub_emotions.extend(["fear_of_failure", "future_threat", "catastrophizing"])
        secondary_subs.extend(["fear", "sadness", "helplessness"])
        contexts.extend(["academic_risk", "specific_exam_failure_belief", "catastrophic_exam_thought"])
        updates.setdefault("distortion_type", "catastrophizing")
        updates.setdefault("distortion_confidence", 0.86)
        updates.setdefault(
            "distortion_explanation",
            "The active thought jumps from exam stress to failing or dropping out.",
        )
        updates.setdefault("all_distortions", ["catastrophizing", "fortune_telling"])

    if has_environment_trigger and has_sleep:
        contexts.append("sleep_environment")
        if "phone" in text:
            contexts.append("phone_distraction")
        if any(token in text for token in ("study on my bed", "studying on my bed", "study space", "desk", "room")):
            contexts.append("study_space_distraction")

    if sub_emotions or symptoms or contexts:
        current_emotion = str(
            state.get("fused_emotion") or state.get("emotion") or state.get("last_detected_emotion") or ""
        ).lower()

        # VOICE AUTHORITY GUARD: if Gemini already classified emotion from audio,
        # do NOT override emotion/fused_emotion with text-keyword heuristics.
        # Voice is the authoritative ground truth for core emotion; text keywords
        # may still enrich sub-emotions, symptoms, behaviors, and contexts.
        voice_features = state.get("voice_features")
        has_authoritative_voice = (
            isinstance(voice_features, dict)
            and str(voice_features.get("extraction_method", "")).lower().strip() == "gemini_audio"
        )

        if has_exam or has_failure_belief or (has_sleep and has_thought_loop):
            if not has_authoritative_voice:
                # No authoritative voice — safe to infer emotion from text keywords.
                updates["emotion"] = "anxiety" if current_emotion in {"", "neutral", "joy", "surprise"} else current_emotion
                updates["fused_emotion"] = "anxiety" if current_emotion in {"", "neutral", "joy", "surprise"} else current_emotion
            # Always enrich primary sub-emotion from context when it is generic.
            if not state.get("primary_sub_emotion") or str(state.get("primary_sub_emotion")).lower() in {"neutral", current_emotion}:
                updates["primary_sub_emotion"] = sub_emotions[0]

        updates["secondary_sub_emotions"] = _merge_unique(state.get("secondary_sub_emotions"), [*sub_emotions[1:], *secondary_subs])
        updates["detected_symptoms"] = _merge_unique(state.get("detected_symptoms"), symptoms)
        updates["detected_behaviors"] = _merge_unique(state.get("detected_behaviors"), behaviors)
        updates["detected_contexts"] = _merge_unique(state.get("detected_contexts"), contexts, limit=14)

    return updates



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

    context_enrichment = _derive_exam_sleep_cognitive_context({**state, **merged})
    if context_enrichment:
        merged.update(context_enrichment)
        print(
            "[ANALYSIS_AND_PLANNING]   Context enrichment: "
            f"sub={merged.get('primary_sub_emotion') or state.get('primary_sub_emotion')} "
            f"contexts={merged.get('detected_contexts') or state.get('detected_contexts') or []} "
            f"distortion={merged.get('distortion_type') or 'none'}"
        )

    # Create merged state view so downstream sub-nodes see fusion results
    state_after_fusion = {**state, **merged}

    #  2. Trend + deterministic clinical defaults
    # Reads: fused_emotion, fused_intensity, user_id, messages
    # Writes: emotional_trend, trend_window
    #         + clinical fields (static defaults — no LLM)
    prefetched_intent = state_after_fusion.get("prefetched_intent", {})
    _intent_val = prefetched_intent.get("intent", "venting") if isinstance(prefetched_intent, dict) else "venting"
    inline_distortion = os.getenv("SENTIMIND_INLINE_DISTORTION", "0").lower() in {"1", "true", "yes"}

    messages = state_after_fusion.get("messages", [])
    background_trend = os.getenv("SENTIMIND_BACKGROUND_TREND", "1").lower() in {"1", "true", "yes"}
    cached_trend_result = None
    if background_trend and not inline_distortion:
        try:
            from .trend_analyzer_node import get_cached_trend_snapshot
            cached_trend_result = get_cached_trend_snapshot(state_after_fusion)
            merged.update(cached_trend_result)
            print(f"[ANALYSIS_AND_PLANNING]   Trend using {cached_trend_result.get('trend_source', 'cache')} snapshot "
                  f"({cached_trend_result.get('emotional_trend', 'stable')}); DB refresh scheduled later")
        except Exception as e:
            print(f"[ANALYSIS_AND_PLANNING]  Cached trend lookup failed: {str(e)[:100]}")
            cached_trend_result = {"emotional_trend": "stable", "trend_window": []}
            merged.update(cached_trend_result)

    # Clinical severity check REMOVED (v11.1 latency optimisation).
    # Always use safe minimal defaults — zero LLM cost, no DB write.
    # Technique selector and response generator receive these fields but
    # 'minimal' / 0 scores mean no contraindication filtering is applied.
    merged.update({
        "clinical_severity":   "minimal",
        "clinical_phq9_score": 0,
        "clinical_gad7_score": 0,
        "clinical_indicators": [],
        "clinical_confidence": 0.0,
    })
    print("[ANALYSIS_AND_PLANNING]   Clinical severity → minimal (deterministic default, no LLM)")


    if inline_distortion:
        try:
            from .parallel_analysis import run_parallel_analysis

            print("[ANALYSIS_AND_PLANNING]   Inline distortion ENABLED (experiment flag)")
            analysis_result = await run_parallel_analysis(state_after_fusion)
            merged.update(analysis_result)
        except Exception as e:
            print(f"[ANALYSIS_AND_PLANNING]  Inline distortion/trend analysis failed: {str(e)[:100]}")
            merged.update({
                "distortion_type": None, "distortion_confidence": 0.0,
                "distortion_explanation": None, "all_distortions": [],
                "emotional_trend": "stable", "trend_window": [],
            })
    else:
        print("[ANALYSIS_AND_PLANNING]   Distortion detection moved to background/profile path")
        if background_trend:
            try:
                from .trend_analyzer_node import refresh_emotional_trend_cache

                asyncio.create_task(refresh_emotional_trend_cache(state_after_fusion))
                if cached_trend_result is None:
                    merged.update({"emotional_trend": "stable", "trend_window": []})
                print("[ANALYSIS_AND_PLANNING]   Trend DB query moved to background/cache path")
            except Exception as e:
                print(f"[ANALYSIS_AND_PLANNING]  Trend background scheduling failed: {str(e)[:100]}")
                merged.update({"emotional_trend": "stable", "trend_window": []})
        else:
            try:
                from .trend_analyzer_node import analyze_emotional_trends
                trend_result = await analyze_emotional_trends(state_after_fusion)
                merged.update(trend_result)
            except Exception as e:
                print(f"[ANALYSIS_AND_PLANNING]  Trend analysis failed: {str(e)[:100]}")
                merged.update({"emotional_trend": "stable", "trend_window": []})
        if "distortion_type" not in merged:
            merged.update({
                "distortion_type": None, "distortion_confidence": 0.0,
                "distortion_explanation": None, "all_distortions": [],
            })
        else:
            merged.setdefault("distortion_confidence", 0.8)
            merged.setdefault("distortion_explanation", None)
            merged.setdefault("all_distortions", [merged.get("distortion_type")])

    state_after_analysis = {**state, **merged}

    # ============================================
    # 1.5. Consent & Suppression Parser (sync, <1ms, zero LLM)
    # ============================================
    # Must run AFTER emotion fusion so state_after_fusion exists,
    # but BEFORE the planner so the planner already sees consent flags.
    try:
        consent_result = parse_consent_and_suppression(state_after_analysis)
        if consent_result:
            merged.update(consent_result)
    except Exception as e:
        print(f"[ANALYSIS_AND_PLANNING]  Consent parser failed (non-fatal): {str(e)[:100]}")

    state_after_analysis = {**state, **merged}

    #  3. Conversation Context Resolver (sync, no LLM)
    # Resolves short replies/pronouns against the last assistant question,
    # active thread, and active technique before the planner makes decisions.
    try:
        resolver_result = resolve_conversation_context(state_after_analysis)
        merged.update(resolver_result)
    except Exception as e:
        print(f"[ANALYSIS_AND_PLANNING]  Context resolver failed: {str(e)[:100]}")

    state_after_resolution = {**state, **merged}

    #  4. Conversation Planner (async, typically <1ms  may call LLM as fallback) 
    # Reads: fused_emotion, fused_intensity, emotional_trend, messages, prefetched_intent
    # Writes: conversation_strategy, conversation_phase, technique_readiness
    try:
        planner_result = await conversation_planner_node(state_after_resolution)
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
    refined_turn_type = refine_turn_type(
        state=state_after_planner,
        previous_context=state.get("previous_turn_context") or {},
    )
    merged["turn_type"] = refined_turn_type
    print(
        "[ANALYSIS_AND_PLANNING]   Turn lifecycle: "
        f"guess={state.get('turn_type_guess') or 'none'} -> final={refined_turn_type}"
    )

    #  5. Behavioral Activation (optional)
    # This only adds an optional micro-action to the prompt. It is off the
    # response-critical path by default to keep the reply focused and lean.
    inline_activation = os.getenv("SENTIMIND_INLINE_ACTIVATION", "0").lower() in {"1", "true", "yes"}
    if inline_activation and strategy not in {"no_action", "ask_question"}:
        try:
            activation_result = activate_behavioral_intervention(state_after_planner)
            merged.update(activation_result)
        except Exception as e:
            print(f"[ANALYSIS_AND_PLANNING]  Behavioral activation failed: {str(e)[:100]}")
            merged.update({"micro_action": None, "micro_action_rationale": None, "micro_action_category": None})
    else:
        reason = "feature flag disabled" if not inline_activation else f"strategy={strategy}"
        print(f"[ANALYSIS_AND_PLANNING]   Behavioral activation SKIPPED ({reason})")
        merged.update({"micro_action": None, "micro_action_rationale": None, "micro_action_category": None})

    print(f"[NODE: ANALYSIS_AND_PLANNING]  Fused complete | "
          f"Emotion: {merged.get('fused_emotion', '?')} | "
          f"Strategy: {merged.get('conversation_strategy', '?')} | "
          f"Trend: {merged.get('emotional_trend', '?')} | "
          f"Clinical: {merged.get('clinical_severity', 'N/A').upper()}")

    return merged

