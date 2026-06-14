"""
Parallel Intake Node  SentiMind v5.3 Latency Optimization

Runs FOUR tasks concurrently via asyncio.gather:
  1. Crisis Pre-Screener    Gemini safety LLM
  2. Context Loader         DB context + compact memory
  3. Mood Analyzer Node     Gemini mood model
  4. Intent Pre-Check       Gemini intent (now truly async)

WHY THIS IS SAFE:
  All four tasks only READ from the initial state (messages, user_id, session_id)
  and write to COMPLETELY DISJOINT state keys:
    - crisis_screener   crisis_detected, crisis_level, crisis_pre_screened
    - context_loader    is_new_user, session_count, memory_context, chat_history, ...
    - mood_analyzer     emotion, sentiment, intensity, confidence
    - intent_pre_check  prefetched_intent

BEFORE v5.2 (sequential ~700ms):
  START  crisis_screener (400ms)  intake (300ms)  mood_analyzer (400ms)  ...
  then in conversation_planner: intent_check (8001500ms)  ON CRITICAL PATH

AFTER v5.2 (parallel intake + serial mood ~400ms + serial intent ~1000ms):
  START  parallel_intake [crisis||intake] (400ms)  mood  ...  planner  intent_check

AFTER v5.3 (4-way parallel ~max(400,300,400,800) = ~800ms, intent OFF critical path):
  START  parallel_intake_v2 [crisis||intake||mood||intent] (~800ms)  emotion_fusion
  conversation_planner uses prefetched_intent  ZERO extra LLM call

  Net saving over v5.2: ~8001500ms (intent check moved off critical path)
  Net saving over v5.1: ~8001500ms (intent) + ~400ms (mood parallelised) = ~1.21.9s

v5.3 PERF BONUS:
  Mood and intent calls run asynchronously so intake DB queries, crisis
  screening, mood detection, and intent pre-check can overlap.
"""

import asyncio
import os
from ..agent.state import MentalHealthState
from ..utils.distress_anchor import (
    anchor_write_policy,
    has_active_therapeutic_thread,
    should_skip_mood_for_anchor_consent,
)
from ..utils.turn_signals import is_polite_acknowledgement


_MOOD_SKIP_ROUTES = {
    "chitchat",
    "contextual_followup",
    "technique_follow_up",
    "memory_query",
    "positive_feedback",
}

_NEGATIVE_EMOTIONS = {"anxiety", "sadness", "anger", "fear", "disgust"}
_LOW_SIGNAL_EMOTIONS = {
    "neutral", "joy", "surprise", "calm", "content",
    "desire", "relief", "acknowledgement", "approval", "optimism", "gratitude",
}


def _is_authoritative_voice_features(features: dict | None) -> bool:
    """Return true for real Gemini audio features, not neutral fallback stubs.

    A result is authoritative if:
    - extraction_method is 'gemini_audio' (confirmed server-side Gemini call), OR
    - acoustic cues are present and confidence > 0 (legacy callers without the field)

    Fallback stubs (extraction_method contains 'fallback') are always rejected.
    Neutral/calm speech legitimately returns confidence=0.0 from Gemini, so the
    confidence threshold is NOT applied when the extraction_method is explicit.
    """
    if not isinstance(features, dict) or not features:
        return False

    method = str(features.get("extraction_method") or "").lower().strip()
    if "fallback" in method:
        return False
    # Explicit Gemini audio result — authoritative regardless of confidence value.
    # Neutral/calm speech correctly returns confidence=0 from Gemini; that is
    # valid signal, not a missing/stubbed result.
    if method == "gemini_audio":
        return True

    # Legacy callers may pass the same payload without extraction_method.
    emotion = str(features.get("emotion") or "").lower().strip()
    if emotion in {"", "unknown", "none", "null"}:
        return False
    try:
        confidence = float(features.get("confidence", 0.0))
    except Exception:
        confidence = 0.0
    has_acoustic_cues = any(
        key in features
        for key in ("arousal", "valence", "distress_index", "pause_density", "acoustic_features")
    )
    return has_acoustic_cues and confidence > 0.0


def _anchored_distress_emotion(state: MentalHealthState, current_message: str, fallback: str) -> str:
    """Infer the original distress family when a follow-up has low-signal wording."""
    if fallback in _NEGATIVE_EMOTIONS:
        return fallback

    text = " ".join(
        str(value or "")
        for value in (
            current_message,
            state.get("active_thread_summary"),
            state.get("primary_concern"),
            state.get("triggering_context"),
            state.get("functional_impact"),
            state.get("core_belief"),
        )
    ).lower()
    if any(marker in text for marker in ("panic", "anxious", "anxiety", "worried", "worry", "stress", "overwhelmed")):
        return "anxiety"
    if any(marker in text for marker in ("sad", "lonely", "alone", "depressed", "grief", "empty", "not feeling well")):
        return "sadness"
    if any(marker in text for marker in ("angry", "frustrated", "furious", "irritated")):
        return "anger"
    if any(marker in text for marker in ("scared", "afraid", "terrified", "fear")):
        return "fear"
    return "sadness"


def _fmt_list(values, limit: int = 4) -> str:
    cleaned = [str(value) for value in (values or []) if value]
    if not cleaned:
        return "none"
    suffix = f", +{len(cleaned) - limit}" if len(cleaned) > limit else ""
    return ", ".join(cleaned[:limit]) + suffix


def _append_unique_lower(values: list | None, additions: list | None, limit: int = 8) -> list[str]:
    result: list[str] = []
    for item in list(values or []) + list(additions or []):
        clean = str(item or "").lower().strip()
        if clean and clean not in result:
            result.append(clean)
    return result[:limit]


def _core_for_subemotion(sub_emotion: str, fallback: str) -> str:
    label = str(sub_emotion or "").lower().strip()
    if label in {
        "loneliness", "isolation", "grief", "shame", "guilt", "self_blame",
        "self_criticism", "rejection", "insecurity", "inadequacy", "embarrassment",
        "hopelessness", "low_mood", "sadness", "disappointment", "emptiness",
    }:
        return "sadness"
    if label in {
        "anxiety", "worry", "nervousness", "stress", "overwhelm", "rumination",
        "racing_thoughts", "bedtime_rumination", "academic_pressure",
        "fear_of_failure", "future_threat", "catastrophizing", "panic",
    }:
        return "anxiety"
    if label in {"anger", "frustration", "irritability", "resentment", "feeling_disrespected"}:
        return "anger"
    if label in {"fear", "panic_now", "distress", "high_anxiety"}:
        return "fear"
    return fallback if fallback not in _LOW_SIGNAL_EMOTIONS else "sadness"


def _derive_followup_enrichment(
    current_message: str,
    *,
    previous_sub_emotion: str,
    previous_secondary: list[str] | None,
    previous_symptoms: list[str] | None,
    previous_behaviors: list[str] | None,
    previous_contexts: list[str] | None,
) -> dict:
    try:
        from ..tools.mood_tools import _derive_structured_tags

        subs, symptoms, behaviors, contexts = _derive_structured_tags(current_message)
    except Exception:
        subs, symptoms, behaviors, contexts = [], [], [], []

    if not any((subs, symptoms, behaviors, contexts)):
        return {
            "enriched": False,
            "primary_sub_emotion": previous_sub_emotion,
            "secondary_sub_emotions": list(previous_secondary or []),
            "detected_symptoms": list(previous_symptoms or []),
            "detected_behaviors": list(previous_behaviors or []),
            "detected_contexts": list(previous_contexts or []),
        }

    generic_previous = {
        "", "neutral", "joy", "surprise", "calm", "content", "desire",
        "relief", "approval", "optimism", "gratitude", "acknowledgement",
        "sadness", "anxiety", "fear", "anger", "stress", "worry", "nervousness",
    }
    previous = str(previous_sub_emotion or "").lower().strip()
    primary = subs[0] if subs and previous in generic_previous else previous or (subs[0] if subs else "")
    secondary = _append_unique_lower(
        [item for item in [previous] if item and item != primary] + list(previous_secondary or []),
        [item for item in subs if item != primary],
    )
    return {
        "enriched": True,
        "primary_sub_emotion": primary,
        "secondary_sub_emotions": secondary,
        "detected_symptoms": _append_unique_lower(previous_symptoms, symptoms),
        "detected_behaviors": _append_unique_lower(previous_behaviors, behaviors),
        "detected_contexts": _append_unique_lower(previous_contexts, contexts),
    }


def _gate_calibrated_mood(state: MentalHealthState, current_message: str) -> dict:
    """Return a low-latency mood result for routes that should not be re-analyzed standalone."""
    route = state.get("gate_route", "")
    flags = state.get("gate_context_flags") or []
    hint = state.get("gate_intensity_hint")
    previous_emotion = state.get("last_detected_emotion") or state.get("fused_emotion") or state.get("emotion") or "neutral"
    previous_sub_emotion = state.get("primary_sub_emotion") or previous_emotion
    # last_detected_intensity is only written on genuine therapeutic turns (not follow-ups),
    # so it correctly represents the established distress anchor.
    previous_intensity = state.get("last_detected_intensity")
    peak_intensity = state.get("peak_distress_intensity")
    followup_turn = int(state.get("followup_turn_count") or 0)
    previous_symptoms = state.get("detected_symptoms") or []
    previous_behaviors = state.get("detected_behaviors") or []
    previous_contexts = state.get("detected_contexts") or []

    def _result(
        emotion: str,
        sentiment: str,
        intensity: float,
        confidence: float,
        sub_emotion: str | None = None,
        secondary: list[str] | None = None,
        symptoms: list[str] | None = None,
        behaviors: list[str] | None = None,
        contexts: list[str] | None = None,
        enriched: bool = False,
    ) -> dict:
        sub = sub_emotion or emotion
        return {
            "emotion": emotion,
            "sentiment": sentiment,
            "intensity": intensity,
            "confidence": confidence,
            "raw_emotion_label": sub,
            "primary_sub_emotion": sub,
            "secondary_sub_emotions": secondary or [],
            "detected_symptoms": previous_symptoms if symptoms is None else symptoms,
            "detected_behaviors": previous_behaviors if behaviors is None else behaviors,
            "detected_contexts": previous_contexts if contexts is None else contexts,
            "emotion_scores": {emotion: confidence},
            "emotion_reasoning": "calibrated from smart gate route",
            "followup_sub_emotion_enriched": enriched,
        }

    def _float(value, default):
        try:
            return float(value)
        except Exception:
            return default

    if route == "crisis":
        return _result("sadness", "negative", 0.95, 0.95, "hopelessness")

    if route == "chitchat":
        return _result("neutral", "neutral", 0.0, 0.9, "neutral")

    if route == "memory_query":
        return _result("neutral", "neutral", 0.05, 0.9, "curiosity")

    if "gratitude_acknowledgement" in flags or "low_signal_affirmation" in flags or is_polite_acknowledgement(current_message):
        return _result("neutral", "neutral", 0.05, 0.9, "acknowledgement")

    if route == "positive_feedback" or "positive_feedback" in flags:
        return _result("joy", "positive", 0.15, 0.85, "relief")

    if route == "accept_technique" or "accept_technique" in flags or "technique_acceptance_answer" in flags:
        inherited = previous_emotion if previous_emotion and previous_emotion != "neutral" else "anxiety"
        anchor = max(
            _float(previous_intensity, 0.0),
            _float(peak_intensity, 0.0),
            _float(hint, 0.35),
        )
        # v12.0: thread-aware floor — if an active therapeutic concern is known,
        # a short consent phrase ("yes share it with me") must never be assigned
        # below 0.45.  Using primary_concern presence as the trigger is more
        # reliable than gate_intensity_hint because the hint is derived from the
        # same short text that caused the problem.
        if has_active_therapeutic_thread(state) and anchor < 0.45:
            anchor = 0.45
            print(
                "[MOOD_CALIBRATE] Consent turn: thread-aware floor applied "
                "(primary_concern/thread exists) -> anchor floored to 0.45"
            )
        intensity = min(max(anchor, 0.25), 0.85)
        sentiment = "negative" if inherited in {"anxiety", "sadness", "anger", "fear", "disgust"} else "neutral"
        sub = previous_sub_emotion if previous_sub_emotion and previous_sub_emotion != "neutral" else inherited
        return _result(
            inherited,
            sentiment,
            intensity,
            0.88,
            sub,
            [str(item).lower() for item in (state.get("secondary_sub_emotions") or []) if item],
        )

    if route in {"therapeutic", "technique_request"}:
        lower = (current_message or "").lower()
        anchor = max(
            _float(previous_intensity, 0.0),
            _float(peak_intensity, 0.0),
            _float(hint, 0.55),
        )
        intensity = min(max(anchor, 0.25), 0.85)
        if any(marker in lower for marker in ("panic", "anxious", "anxiety", "worried", "stress", "overwhelmed")):
            return _result("anxiety", "negative", intensity, 0.78, "stress")
        if any(marker in lower for marker in ("sad", "lonely", "alone", "depressed", "grief", "hopeless", "empty")):
            return _result("sadness", "negative", intensity, 0.78, "sadness")
        if any(marker in lower for marker in ("angry", "frustrated", "furious", "irritated")):
            return _result("anger", "negative", intensity, 0.72, "frustration")
        if any(marker in lower for marker in ("scared", "afraid", "terrified", "fear")):
            return _result("fear", "negative", intensity, 0.72, "fear")

        inherited = previous_emotion if previous_emotion and previous_emotion != "neutral" else "anxiety"
        sentiment = "negative" if inherited in {"anxiety", "sadness", "anger", "fear", "disgust"} else "neutral"
        sub = previous_sub_emotion if previous_sub_emotion != "neutral" else inherited
        return _result(inherited, sentiment, intensity, 0.7, sub)

    if route == "technique_follow_up" and (
        "reject_technique" in flags or "technique_rejection" in flags
    ):
        return _result("neutral", "negative", min(_float(hint, 0.35), 0.45), 0.85, "disapproval", ["annoyance"])

    if route == "contextual_followup":
        anchor = max(
            _float(previous_intensity, 0.0),
            _float(peak_intensity, 0.0),
            _float(hint, 0.2),
        )
        lower = (current_message or "").lower()
        strong_distress = any(
            marker in lower
            for marker in ("panic", "terrified", "can't breathe", "hopeless", "worthless", "want to die")
        )
        if anchor >= 0.5:
            # Progressive distress anchoring: proportionally decay the established distress
            # rather than collapsing to 0.35. Decay is turn-aware so calm answers
            # naturally walk intensity down without snapping it.
            #   Turn 0 (first follow-up)  → floor = anchor × 0.85
            #   Turn 1 (second follow-up) → floor = anchor × 0.75
            #   Turn 2+ (third+)          → floor = anchor × 0.65 (hard minimum)
            decay_factor = 0.85 if followup_turn == 0 else (0.75 if followup_turn == 1 else 0.65)
            floor = anchor * decay_factor
            cap = 0.90 if strong_distress else max(anchor, 0.75)
            intensity = min(floor, cap)
            print(
                f"[MOOD_CALIBRATE] Distress anchor={anchor:.0%} followup_turn={followup_turn} "
                f"decay={decay_factor} floor={floor:.0%} → intensity={intensity:.0%}"
            )
        else:
            cap = 0.75 if strong_distress else 0.35
            intensity = min(max(anchor, _float(hint, 0.2)), cap)
        inherited_emotion = previous_emotion if previous_emotion not in _LOW_SIGNAL_EMOTIONS else _anchored_distress_emotion(
            state,
            current_message,
            previous_emotion,
        )
        enrichment = _derive_followup_enrichment(
            current_message,
            previous_sub_emotion=previous_sub_emotion,
            previous_secondary=state.get("secondary_sub_emotions") or [],
            previous_symptoms=previous_symptoms,
            previous_behaviors=previous_behaviors,
            previous_contexts=previous_contexts,
        )
        primary_sub = enrichment["primary_sub_emotion"]
        if enrichment["enriched"]:
            inherited_emotion = _core_for_subemotion(primary_sub, inherited_emotion)
            print(
                "[MOOD_CALIBRATE] Follow-up sub-emotion enriched: "
                f"primary={primary_sub} secondary={_fmt_list(enrichment['secondary_sub_emotions'])}"
            )
        return _result(
            inherited_emotion,
            "negative" if inherited_emotion in _NEGATIVE_EMOTIONS else "neutral",
            intensity,
            0.8,
            primary_sub if primary_sub not in _LOW_SIGNAL_EMOTIONS else inherited_emotion,
            enrichment["secondary_sub_emotions"],
            symptoms=enrichment["detected_symptoms"],
            behaviors=enrichment["detected_behaviors"],
            contexts=enrichment["detected_contexts"],
            enriched=enrichment["enriched"],
        )

    return _result("neutral", "neutral", min(_float(hint, 0.2), 0.35), 0.75, "neutral")


async def _intent_pre_check_task(message: str, recent_context: str = "") -> dict:
    """
    Calls llm_intent_pre_check asynchronously.
    """
    try:
        from ..llm.llm_classifier import llm_intent_pre_check
        return await llm_intent_pre_check(message, recent_context)
    except Exception as e:
        print(f"[PARALLEL_INTAKE]  Intent prefetch failed: {str(e)[:80]}  using venting fallback")
        return {"intent": "venting", "confidence": 0.0}


async def run_parallel_intake(state: MentalHealthState) -> dict:
    """
    v5.4: Run crisis screening, context loading, mood analysis, and intent
    pre-check CONCURRENTLY via asyncio.gather (4-way parallel).

    Gate-aware optimizations:
      - Skips intent pre-check when smart_pipeline_gate already seeded intent
      - Skips crisis screener when smart_pipeline_gate already made a route
        decision; set SENTIMIND_DUPLICATE_CRISIS_CHECK=1 to restore backup check

    All tasks read from the initial state only and write to disjoint keys.
    Returns: merged dict across all nodes' outputs.
    """
    from ..nodes.context_loader import load_user_context
    from ..nodes.mood_analyzer_node import analyze_mood

    messages = state.get("messages", [])
    current_message = messages[-1].content if messages else ""

    recent_context = ""
    if len(messages) > 1:
        # Get up to the last 3 messages before the current one
        ctx_msgs = messages[-4:-1]
        lines = []
        for m in ctx_msgs:
            role = "User" if getattr(m, "type", "") == "human" else "System"
            content = getattr(m, "content", "")
            lines.append(f"{role}: {content}")
        recent_context = "\n".join(lines)

    from ..nodes.voice_preprocessing import preprocess_voice_input

    # --- Gate-aware skip flags ---
    prefetched = state.get("prefetched_intent") or {}
    gate_source = isinstance(prefetched, dict) and prefetched.get("source") == "smart_gate"
    gate_route  = state.get("gate_route", "")
    gate_flags = state.get("gate_context_flags") or []
    gate_confidence = float(prefetched.get("confidence", 0.0)) if isinstance(prefetched, dict) else 0.0
    state_voice_features = state.get("voice_features")
    has_authoritative_voice_features = _is_authoritative_voice_features(state_voice_features)
    has_audio_input = bool(state.get("audio_file_path") or state.get("audio_bytes"))
    has_voice = bool(
        has_audio_input
        or state_voice_features
        or state.get("has_voice")
    )
    has_transcription = bool(str(state.get("transcription") or "").strip())
    voice_already_processed = bool(
        (state.get("voice_processed") and isinstance(state_voice_features, dict))
        or has_authoritative_voice_features
    )
    needs_voice_preprocessing = bool(has_audio_input and not voice_already_processed)

    if has_voice:
        print(
            f"[PARALLEL_INTAKE] Voice present: gate_route={gate_route!r} | has_transcription={has_transcription} | "
            f"already_processed={voice_already_processed} | preprocessing_needed={needs_voice_preprocessing}"
        )
    blocking_mood_llm = os.getenv("SENTIMIND_BLOCKING_MOOD_LLM", "0").lower() in {"1", "true", "yes", "on"}
    fast_gate_skip_mood = os.getenv("SENTIMIND_FAST_GATE_SKIP_MOOD", "0").lower() in {"1", "true", "yes", "on"}
    should_skip_mood = (
        bool(state.get("gate_should_skip_mood_analysis"))
        or gate_route in _MOOD_SKIP_ROUTES
        or should_skip_mood_for_anchor_consent(state, current_message)
        or (fast_gate_skip_mood and gate_source and gate_route != "crisis" and not blocking_mood_llm)
        or has_audio_input
        or has_authoritative_voice_features  # Authoritative voice override: skip text mood when voice data is present
    )

    # Skip intent pre-check when gate already seeded intent
    has_gate_intent = gate_source

    # v9.2 latency mode: the smart gate is authoritative for crisis routing.
    # Set SENTIMIND_DUPLICATE_CRISIS_CHECK=1 to restore the backup crisis LLM.
    duplicate_crisis_check = os.getenv("SENTIMIND_DUPLICATE_CRISIS_CHECK", "0").lower() in {"1", "true", "yes"}
    skip_crisis = (
        not duplicate_crisis_check
        and gate_source
        and gate_route != "crisis"
        and "gate_error" not in gate_flags
    )

    # --- Build task log ---
    if skip_crisis:
        print(f"   screen_for_crisis       SKIPPED (smart_gate non-crisis, conf={gate_confidence:.0%})")
    else:
        print(f"   screen_for_crisis     (Gemini via Google AI Studio)")
    print("   load_user_context     (Prisma DB context)")
    if should_skip_mood:
        if has_voice:
            _skip_reason = "voice data present - using voice features as authoritative"
        else:
            _skip_reason = f"gate={gate_route or 'unknown'} contextual/low-signal route"
        print(f"   analyze_mood            SKIPPED ({_skip_reason})")
    else:
        print("   analyze_mood          (Gemini mood)")
    if has_gate_intent:
        print("   intent_pre_check        SKIPPED (gate intent already available)")
    else:
        print("   intent_pre_check      (llama-3.3-70b-free async, off critical path)")
    if needs_voice_preprocessing:
        print("   preprocess_voice_input  (Gemini ASR + voice features)")
    elif has_voice:
        print(f"   preprocess_voice_input  SKIPPED (transcription already present)")

    # --- Assemble task list ---
    tasks = []
    _task_map = []  # track which result slot maps to which task

    if not skip_crisis:
        from ..agent.graph import screen_for_crisis
        tasks.append(screen_for_crisis(state))
        _task_map.append("crisis")

    tasks.append(load_user_context(state))
    _task_map.append("intake")
    if not should_skip_mood:
        tasks.append(analyze_mood(state))
        _task_map.append("mood")

    if not has_gate_intent:
        tasks.append(_intent_pre_check_task(current_message, recent_context))
        _task_map.append("intent")

    if needs_voice_preprocessing:
        tasks.append(preprocess_voice_input(state))
        _task_map.append("voice_preprocessing")

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Map results dynamically based on which tasks actually ran
    result_map = dict(zip(_task_map, results))

    crisis_result = result_map.get("crisis")
    intake_result = result_map.get("intake")
    mood_result   = result_map.get("mood")
    voice_prep_result = result_map.get("voice_preprocessing")

    if has_gate_intent:
        intent_result = state.get("prefetched_intent", {"intent": "venting", "confidence": 0.5})
    else:
        _raw = result_map.get("intent")
        intent_result = _raw if isinstance(_raw, dict) else {"intent": "venting", "confidence": 0.0}

    merged = {}

    #  Crisis screener 
    if crisis_result is None:
        # Smart gate already routed this request as non-crisis.
        print(f"[NODE: PARALLEL_INTAKE]  Crisis screener skipped (gate={gate_route or 'unknown'}) - defaulting to no-crisis")
        merged.update({
            "crisis_detected": False,
            "crisis_level": "none",
            "crisis_pre_screened": True,   # Mark screened so downstream skips re-check
        })
    elif isinstance(crisis_result, Exception):
        print(f"[NODE: PARALLEL_INTAKE]  Crisis screener failed: {str(crisis_result)[:100]}")
        merged.update({
            "crisis_detected": False,
            "crisis_level": "none",
            "crisis_pre_screened": False,
        })
    else:
        merged.update(crisis_result)

    #  Intake node 
    if isinstance(intake_result, Exception):
        print(f"[NODE: PARALLEL_INTAKE]  Intake failed: {str(intake_result)[:100]}")
        merged.update({
            "is_new_user": True,
            "session_count": 0,
            "most_common_emotion": "neutral",
            "historical_mood": "neutral",
            "user_preferences": {},
            "chat_history": [],
            "memory_context": "",
            "context_ready": False,
            "messages": state.get("messages", []),
        })
    else:
        merged.update(intake_result)

    #  Mood analyzer 
    if should_skip_mood:
        if has_voice:
            # If we have voice, calibrate mood directly using voice features as authoritative
            vf = None
            if voice_prep_result and not isinstance(voice_prep_result, Exception) and isinstance(voice_prep_result, dict):
                candidate = voice_prep_result.get("voice_features")
                if voice_prep_result.get("voice_processed") and _is_authoritative_voice_features(candidate):
                    vf = candidate
            if not vf and _is_authoritative_voice_features(state_voice_features):
                vf = state_voice_features

            if vf:
                # Top-level fields mapping for voice
                calibrated = {
                    "emotion": vf.get("emotion", "neutral"),
                    "sentiment": vf.get("sentiment", "neutral"),
                    "intensity": float(vf.get("intensity", vf.get("arousal", 0.5))),
                    "confidence": float(vf.get("confidence", 0.8)),
                    "raw_emotion_label": vf.get("primary_sub_emotion") or vf.get("emotion", "neutral"),
                    "primary_sub_emotion": vf.get("primary_sub_emotion") or vf.get("emotion", "neutral"),
                    "secondary_sub_emotions": vf.get("secondary_sub_emotions") or [],
                    "detected_symptoms": vf.get("detected_symptoms") or [],
                    "detected_behaviors": vf.get("detected_behaviors") or [],
                    "detected_contexts": vf.get("detected_contexts") or [],
                    "emotion_scores": vf.get("emotion_scores") or {},
                    "emotion_reasoning": vf.get("emotion_reasoning", "extracted from voice input"),
                    "voice_processed": True,
                    "voice_features": vf,
                }
                merged.update(calibrated)
                print(
                    f"[NODE: PARALLEL_INTAKE]  Mood inherited from VOICE features: "
                    f"{calibrated.get('emotion')} ({calibrated.get('intensity', 0.0):.0%})"
                )
            else:
                calibrated = _gate_calibrated_mood(state, current_message)
                merged.update(calibrated)
                print(
                    f"[NODE: PARALLEL_INTAKE]  Voice present but features missing. Mood calibrated: "
                    f"{calibrated.get('emotion')} ({calibrated.get('intensity', 0.0):.0%})"
                )
        else:
            calibrated = _gate_calibrated_mood(state, current_message)
            merged.update(calibrated)
            print(
                f"[NODE: PARALLEL_INTAKE]  Mood inherited/calibrated: "
                f"{calibrated.get('emotion')} ({calibrated.get('intensity', 0.0):.0%})"
            )
    elif isinstance(mood_result, Exception):
        print(f"[NODE: PARALLEL_INTAKE]  Mood analyzer failed: {str(mood_result)[:100]}")
        merged.update({
            "emotion": "neutral",
            "sentiment": "neutral",
            "intensity": 0.5,
            "confidence": 0.0,
            "raw_emotion_label": "neutral",
            "primary_sub_emotion": "neutral",
            "secondary_sub_emotions": [],
            "detected_symptoms": [],
            "detected_behaviors": [],
            "detected_contexts": [],
            "emotion_scores": {"neutral": 1.0},
        })
    else:
        merged.update(mood_result)
        _em = mood_result.get("emotion", "neutral")
        _it = mood_result.get("intensity", 0.5)
        print(f"[NODE: PARALLEL_INTAKE]  Mood pre-computed: {_em} ({_it:.0%})")

    #  Intent pre-check 
    if isinstance(intent_result, Exception):
        print(f"[NODE: PARALLEL_INTAKE]  Intent prefetch failed: {str(intent_result)[:100]}")
        merged["prefetched_intent"] = None
    elif isinstance(intent_result, dict):
        merged["prefetched_intent"] = intent_result
        print(f"[NODE: PARALLEL_INTAKE]  Intent pre-computed: "
              f"{intent_result.get('intent')} ({intent_result.get('confidence', 0):.0%})")
    else:
        merged["prefetched_intent"] = None

    #  Voice preprocessing (transcription + features)
    if voice_prep_result is not None:
        if isinstance(voice_prep_result, Exception):
            print(
                "[NODE: PARALLEL_INTAKE]  Voice preprocessing failed: "
                f"{str(voice_prep_result)[:100]}"
            )
        else:
            merged.update(voice_prep_result)
            gemini_transcript = voice_prep_result.get("transcription", "")
            if gemini_transcript:
                # Prefer Gemini audio transcription over browser SpeechRecognition text.
                merged["message"] = gemini_transcript
                print(f"[NODE: PARALLEL_INTAKE]  Gemini transcription override '{gemini_transcript[:80]}'")
            
            # Print voice feature details for server log
            vf = voice_prep_result.get("voice_features")
            if vf:
                print(
                    f"[NODE: PARALLEL_INTAKE]  Voice features parsed: emotion={vf.get('emotion')} "
                    f"({vf.get('confidence', 0.0):.0%}) | distress_index={vf.get('distress_index', 0.0):.2f}"
                )
    elif voice_already_processed:
        vf = state.get("voice_features")
        if vf:
            print(
                f"[NODE: PARALLEL_INTAKE]  Using pre-existing voice features: emotion={vf.get('emotion')} "
                f"({vf.get('confidence', 0.0):.0%}) | distress_index={vf.get('distress_index', 0.0):.2f}"
            )

    crisis_flag = merged.get("crisis_detected", False)
    crisis_level = merged.get("crisis_level", "none")
    # CRITICAL: Only overwrite last_detected_intensity on genuine disclosures.
    # On contextual follow-up turns, the intensity in `merged` is already the
    # DECAYED value (e.g. anchor × 0.85). If we write that back into
    # last_detected_intensity, the NEXT follow-up will decay from the decayed
    # value, causing exponential compounding:
    #   Turn 1: 0.87 (anchor) → Turn 2: 0.87×0.85=0.74 → Turn 3: 0.74×0.75=0.56
    # Instead, keep the original undecayed anchor so decay is always proportional
    # to the peak:
    #   Turn 1: 0.87 (anchor) → Turn 2: 0.87×0.85=0.74 → Turn 3: 0.87×0.75=0.65
    _intensity_preserve_routes = {
        "contextual_followup", "chitchat", "memory_query",
        "positive_feedback", "technique_follow_up",
    }
    should_write_anchor, anchor_intensity, anchor_reason = anchor_write_policy(
        {**state, **merged},
        state,
        merged.get("intensity"),
    )
    if merged.get("emotion") and gate_route not in _intensity_preserve_routes and should_write_anchor:
        merged["last_detected_emotion"] = merged.get("emotion")
    if gate_route not in _intensity_preserve_routes and should_write_anchor and anchor_intensity is not None:
        merged["last_detected_intensity"] = anchor_intensity
        if anchor_intensity != merged.get("intensity"):
            merged["intensity"] = anchor_intensity
    if gate_route not in _intensity_preserve_routes and not should_write_anchor:
        print(f"[NODE: PARALLEL_INTAKE]  Anchor write skipped: {anchor_reason}")
    vf_to_log = merged.get("voice_features") or state.get("voice_features")
    print(
        "\n[NODE: PARALLEL_INTAKE] Complete"
        f"\n  crisis={crisis_flag} ({crisis_level}) | context_ready={merged.get('context_ready', False)}"
        f"\n  mood={merged.get('emotion', '?')} | primary_sub={merged.get('primary_sub_emotion') or 'none'}"
        f"\n  secondary={_fmt_list(merged.get('secondary_sub_emotions'))}"
        f"\n  symptoms={_fmt_list(merged.get('detected_symptoms'))} | behaviors={_fmt_list(merged.get('detected_behaviors'))}"
        f"\n  voice={vf_to_log.get('emotion', '?') if vf_to_log else 'None'}"
        f"\n  intent={merged.get('prefetched_intent', {}).get('intent', '?')}"
    )

    return merged
