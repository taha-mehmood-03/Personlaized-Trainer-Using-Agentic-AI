"""
Emotion Fusion Node  v3.0 Voice-Only Safety Passthrough

ARCHITECTURE NODE 2.7:
Purpose: Apply safety post-processing to the emotion signal and output
         fused_emotion / fused_intensity for all downstream nodes.
Runs AFTER parallel_intake (which includes voice_preprocessing), BEFORE trend_analyzer.
No LLM call — pure deterministic Python.

THREE PATHS:
CASE 0  Voice present (voice_processed=True) AND gate_route is therapeutic/crisis:
    Gemini audio already read the transcript AND the vocal delivery in one call.
    No blending needed — voice result IS the ground truth.
    Apply safety checks only: passive ideation, hedge words, gate caps, distress anchor.
    For other routes (chitchat, memory_query, etc.), voice features are ignored.

  CASE 1  Text-only (no audio):
    Standard text path with intensity normalization, hedge reduction,
    passive ideation detection, gate caps, and distress anchor guard.

  CASE 2  Legacy three-way blend (kept for backward compat, not triggered in normal flow):
    text : voice_label : acoustic = 0.50/0.70 : 0.30/0.15 : 0.20/0.15
    Only reached if somehow both paths produce voice+text with voice_processed=False.

Acoustic override rules (Rule 1-3) still apply in CASE 0 as a clinical safety net.
"""

from ..agent.state import MentalHealthState
from ..utils.distress_anchor import (
    LOW_SIGNAL_EMOTIONS as ANCHOR_LOW_SIGNAL_EMOTIONS,
    calibrate_low_confidence_disclosure_intensity,
    gate_confirms_disclosure,
    has_active_therapeutic_thread,
)

# Canonical emotion ordering
_NEGATIVE_EMOTIONS = {"anger", "sadness", "fear", "anxiety", "disgust"}
_POSITIVE_EMOTIONS = {"joy", "surprise"}

# Valence weights for tie-breaking
_EMOTION_VALENCE = {
    "anger": -0.8,   "disgust": -0.7,  "fear": -0.9,  "anxiety": -0.85,
    "sadness": -0.9, "neutral": 0.0,   "surprise": 0.3, "joy": 0.9,
}

# ============================================
# FIX 1: INTENSITY NORMALIZATION
# Separates model confidence from emotional intensity.
# ============================================
_NEUTRAL_INTENSITY_CAP = 0.20
_LOW_SIGNAL_EMOTIONS   = {"neutral", "calm", "content"}
_LOW_SIGNAL_INTENSITY_CAP = 0.30
_FOLLOWUP_LOW_SIGNAL_EMOTIONS = {"neutral", "joy", "surprise", "calm", "content"}


def _is_authoritative_voice_features(features: dict | None) -> bool:
    """Return true for real Gemini audio emotion features, not fallback stubs."""
    if not isinstance(features, dict) or not features:
        return False

    method = str(features.get("extraction_method") or "").lower().strip()
    if "fallback" in method:
        return False
    if method == "gemini_audio":
        return True

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


def _merge_unique(*lists: list, limit: int = 6) -> list:
    merged: list[str] = []
    seen: set[str] = set()
    for values in lists:
        for value in values or []:
            item = str(value).lower().strip()
            if item and item not in seen:
                merged.append(item)
                seen.add(item)
            if len(merged) >= limit:
                return merged
    return merged


# ============================================
# FIX 2: PASSIVE IDEATION SAFETY OVERRIDE
# ============================================
_PASSIVE_IDEATION_PHRASES = {
    # Original set
    "sleep forever", "not wake up", "never wake up", "disappear forever",
    "wish i wasn't here", "wish i was gone", "wish i were gone",
    "better off without me", "don't want to be here anymore",
    "no point in waking up", "never existed", "want to disappear",
    # ── CRITICAL ADDITIONS ──────────────────────────────────────────────────
    # Direct statements of not wanting to live (explicit suicidal ideation)
    "don't want to live", "do not want to live",
    "i don't want to live", "i do not want to live",
    "don't wanna live", "no longer want to live",
    "want to end my life", "want to end it all", "end it all",
    "want to die", "wanna die", "i want to die",
    "wish i was dead", "wish i were dead", "wish i was never born",
    "should just die", "might as well die", "want to kill myself",
    "thinking about suicide", "thinking of suicide",
    "suicidal thoughts", "suicidal feelings",
    "can't go on", "can't do this anymore", "can't live like this",
    "no reason to live", "nothing to live for",
    "life isn't worth living", "life is not worth living",
    "would be better off dead", "better off dead",
}

# ============================================
# FIX 3: HEDGE-WORD INTENSITY CALIBRATION
# ============================================
_HEDGE_WORDS = [
    "a little", "a bit", "slightly", "kind of", "kinda", "somewhat",
    "a tad", "mildly", "not that", "not very", "not too", "pretty tired",
    "pretty bored", "sort of", "a small",
]
_HEDGE_MULTIPLIER = 0.50


# ============================================
# HELPERS
# ============================================

def _normalize_intensity(label: str, raw_intensity: float, model_confidence: float) -> float:
    """Prevent model confidence from inflating emotional arousal in neutral messages."""
    if label == "neutral":
        return min(raw_intensity, _NEUTRAL_INTENSITY_CAP)
    if label in _LOW_SIGNAL_EMOTIONS:
        return min(raw_intensity, _LOW_SIGNAL_INTENSITY_CAP)
    return raw_intensity


def _apply_hedge_multiplier(message: str, intensity: float) -> float:
    """Reduce intensity 50% when user uses softening/hedging language."""
    msg_lower = message.lower()
    if "better" in msg_lower and any(h in msg_lower for h in ["a bit", "a little"]):
        return intensity   # "a bit better" is NOT a hedge that means low arousal
    for hedge in _HEDGE_WORDS:
        if hedge in msg_lower:
            reduced = round(intensity * _HEDGE_MULTIPLIER, 3)
            print(f"[EMOTION_FUSION] Hedge '{hedge}' detected  intensity: {intensity:.0%}  {reduced:.0%}")
            return reduced
    return intensity


def _should_skip_hedge_reduction(state: MentalHealthState) -> bool:
    """Confirmed disclosures should not be weakened by softening language."""
    return gate_confirms_disclosure(
        state.get("gate_route", ""),
        state.get("gate_context_flags") or [],
    )


def _apply_confidence_anchor_guard(state: MentalHealthState, intensity: float) -> float:
    guarded, reason = calibrate_low_confidence_disclosure_intensity(state, intensity)
    if guarded != intensity:
        print(
            f"[EMOTION_FUSION] Distress anchor guard: {reason} "
            f"{intensity:.0%} -> {guarded:.0%}"
        )
    return guarded


def _anchored_distress_emotion(state: MentalHealthState, current_emotion: str, current_message: str) -> str:
    """Recover the distress family for contextual replies with positive/neutral wording."""
    previous = str(state.get("last_detected_emotion") or "").lower()
    if previous in _NEGATIVE_EMOTIONS:
        return previous

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
    return current_emotion if current_emotion in _NEGATIVE_EMOTIONS else "sadness"


def _check_passive_ideation(message: str) -> bool:
    """Detect passive suicidal ideation phrases misclassified by emotion model."""
    msg_lower = message.lower()
    return any(phrase in msg_lower for phrase in _PASSIVE_IDEATION_PHRASES)


def _apply_gate_intensity_caps(state: MentalHealthState, emotion: str, intensity: float) -> tuple[str, float]:
    """Keep contextual follow-ups and technique feedback from inflating distress.

    For contextual follow-ups, mirrors the progressive decay anchor used in
    _gate_calibrated_mood: when a prior high-distress anchor (>=0.5) exists,
    we allow proportional decay across follow-up turns rather than hard-capping
    at 0.35 — which would silently undo the parallel_intake anchoring.
    """
    route = state.get("gate_route", "")
    flags = state.get("gate_context_flags") or []
    hint = state.get("gate_intensity_hint")
    try:
        hint_value = float(hint) if hint is not None else intensity
    except Exception:
        hint_value = intensity

    if route == "chitchat":
        return "neutral", 0.0
    if route == "memory_query":
        return "neutral", min(hint_value, 0.1)
    if "gratitude_acknowledgement" in flags or "low_signal_affirmation" in flags:
        return "neutral", min(hint_value, 0.08)
    if route == "positive_feedback" or "positive_feedback" in flags:
        return "joy", min(hint_value if hint is not None else 0.15, 0.25)
    if route == "technique_follow_up" and (
        "reject_technique" in flags or "technique_rejection" in flags
    ):
        return emotion if emotion != "anger" else "neutral", min(intensity, hint_value, 0.45)
    if route == "contextual_followup":
        message = state.get("messages", [])
        current = message[-1].content.lower() if message else ""
        strong_distress = any(
            marker in current
            for marker in ("panic", "terrified", "can't breathe", "hopeless", "worthless", "want to die")
        )
        # Check whether a high-distress anchor exists from the initial disclosure.
        # last_detected_intensity is only written on therapeutic turns, so it
        # correctly represents the undecayed original anchor value.
        try:
            anchor = max(
                float(state.get("last_detected_intensity") or 0.0),
                float(state.get("peak_distress_intensity") or 0.0),
                float(hint_value or 0.0),
            )
        except Exception:
            anchor = hint_value
        followup_turn = int(state.get("followup_turn_count") or 0)
        if anchor >= 0.5:
            # Progressive decay — same formula as _gate_calibrated_mood
            decay_factor = 0.85 if followup_turn == 0 else (0.75 if followup_turn == 1 else 0.65)
            floor = anchor * decay_factor
            cap = 0.90 if strong_distress else max(anchor, 0.75)
            anchored = min(max(intensity, floor), cap)
            if str(emotion or "").lower() in _FOLLOWUP_LOW_SIGNAL_EMOTIONS:
                emotion = _anchored_distress_emotion(state, str(emotion or "neutral").lower(), current)
            return emotion, anchored
        # v12.0: Thread-aware floor for near-zero anchors.
        # If Defects 1-2 prevented a real anchor from being written (anchor ≈ 0.0)
        # but we know there is an active therapeutic concern, apply a minimum floor
        # of 0.35 so the follow-up chain doesn't start decaying from zero.
        if not strong_distress:
            thread_floor = 0.35 if has_active_therapeutic_thread(state) else 0.0
            floored = max(thread_floor, min(intensity, hint_value, 0.35))
            if thread_floor > 0 and floored != min(intensity, hint_value, 0.35):
                print(
                    f"[EMOTION_FUSION] Contextual follow-up thread-aware floor: "
                    f"anchor={anchor:.2f} -> floored to {floored:.2f} (therapeutic thread exists)"
                )
            return emotion, floored
    return emotion, intensity


# ============================================
# ACOUSTIC OVERRIDE RULES
# ============================================

def _apply_acoustic_overrides(
    text_emotion: str,
    fused_emotion: str,
    fused_intensity: float,
    voice_features: dict,
) -> tuple:
    """
    Apply psychoacoustic override rules to catch emotion masking.

    Rules (in priority order):
    1. High distress index + neutral text  user is masking distress  sadness
    2. High arousal + neutral text         suppressed anxiety  anxiety
    3. High pause density + low intensity  hesitant speech  boost intensity
    4. No override triggered               return unchanged

    Returns:
        (fused_emotion, fused_intensity, override_applied: bool, override_reason: str)
    """
    distress_index = float(voice_features.get("distress_index", 0.0))
    arousal        = float(voice_features.get("arousal", 0.5))
    pause_density  = float(voice_features.get("pause_density", 0.25))

    override_applied = False
    override_reason  = ""

    # Rule 1: High psychoacoustic distress despite neutral text label
    if distress_index > 0.65 and text_emotion in ("neutral", "joy", "surprise"):
        print(f"[EMOTION_FUSION]  ACOUSTIC OVERRIDE: distress_index={distress_index:.2f} > 0.65 "
              f"with text={text_emotion}  overriding to 'sadness'")
        fused_emotion    = "sadness"
        fused_intensity  = max(fused_intensity, 0.55)
        override_applied = True
        override_reason  = f"distress_index={distress_index:.2f}"

    # Rule 2: Elevated arousal despite neutral/positive text  suppressed anxiety
    elif arousal > 0.75 and text_emotion in ("neutral", "joy") and not override_applied:
        print(f"[EMOTION_FUSION]  ACOUSTIC OVERRIDE: arousal={arousal:.2f} > 0.75 "
              f"with text={text_emotion}  overriding to 'anxiety'")
        fused_emotion    = "anxiety"
        fused_intensity  = max(fused_intensity, 0.50)
        override_applied = True
        override_reason  = f"arousal={arousal:.2f}"

    # Rule 3: Hesitant speech (high pause_density) + low intensity  boost intensity
    # This catches flat, monotone depressive speech
    if pause_density > 0.40 and fused_intensity < 0.40:
        boosted = min(1.0, fused_intensity + 0.15)
        print(f"[EMOTION_FUSION]  PAUSE BOOST: pause_density={pause_density:.2f} > 0.40 "
              f" intensity: {fused_intensity:.2f}  {boosted:.2f}")
        fused_intensity = round(boosted, 3)

    return fused_emotion, fused_intensity, override_applied, override_reason


def _fusion_metadata(
    *,
    state: MentalHealthState,
    text_emotion: str,
    voice_emotion: str | None,
    fused_emotion: str,
    fused_intensity: float,
    voice_confidence: float = 0.0,
    distress_index: float = 0.0,
    override_applied: bool = False,
) -> dict:
    text_norm = str(text_emotion or "neutral").lower()
    voice_norm = str(voice_emotion or "").lower()
    fused_norm = str(fused_emotion or "neutral").lower()
    mismatch = bool(voice_norm and voice_norm != text_norm)

    messages = state.get("messages", [])
    latest_text = str(getattr(messages[-1], "content", "") if messages else state.get("message", "") or "").lower()
    transcription = str(state.get("transcription") or latest_text or "").lower()
    masking_language = any(
        phrase in transcription
        for phrase in ("i'm fine", "im fine", "i am fine", "i'm okay", "im okay", "i am okay", "i'm good", "im good")
    )
    possible_masking = bool(
        override_applied
        or (
            (masking_language or text_norm in {"neutral", "joy", "surprise"})
            and (distress_index >= 0.55 or fused_norm in {"sadness", "anxiety", "fear"})
            and fused_intensity >= 0.45
        )
    )

    text_confidence = float(state.get("confidence", 0.5) or 0.5)
    fusion_confidence = max(text_confidence, voice_confidence) if voice_norm else text_confidence
    transcript_conf = state.get("transcription_confidence")
    try:
        if transcript_conf is not None:
            fusion_confidence = min(float(fusion_confidence), float(transcript_conf))
    except (TypeError, ValueError):
        pass

    return {
        "mismatch": mismatch,
        "possible_masking": possible_masking,
        "fusion_confidence": round(max(0.0, min(1.0, float(fusion_confidence))), 3),
        "voice_feature_snapshot": state.get("voice_features") or {},
    }


# ============================================
# MAIN FUSION NODE
# ============================================

def fuse_emotions(state: MentalHealthState) -> dict:
    """
    EMOTION FUSION NODE v2  3-way text + voice label + acoustic fusion.

    Process:
    1. Read text emotion (from mood_analyzer_node via parallel_intake)
    2. Read voice features (from voice_preprocessing_node, if present)
    3. Compute weighted blend: text  voice_label  acoustic_distress
    4. Apply acoustic override rules (catch emotion masking)
    5. Apply safety overrides (passive ideation)
    6. Output fused_emotion and fused_intensity

    No LLM call  pure deterministic Python.
    """
    text_emotion     = state.get("emotion", "neutral")
    text_intensity   = state.get("intensity", 0.5)
    primary_sub_emotion = state.get("primary_sub_emotion") or text_emotion
    secondary_sub_emotions = state.get("secondary_sub_emotions") or []
    detected_symptoms = state.get("detected_symptoms") or []
    detected_behaviors = state.get("detected_behaviors") or []
    detected_contexts = state.get("detected_contexts") or []
    voice_features   = state.get("voice_features") or {}
    gate_route = str(state.get("gate_route", "") or "").lower()
    
    # Only use voice features if gate_route is therapeutic or crisis
    # (other routes like chitchat, memory_query, etc. should not use voice emotion analysis)
    voice_features_authoritative = _is_authoritative_voice_features(voice_features)
    use_voice_features = (
        bool(voice_features)
        and voice_features_authoritative
        and (
            state.get("voice_processed", False)
            or state.get("has_voice", False)
            or voice_features.get("extraction_method") == "gemini_audio"
        )
        and gate_route in ("therapeutic", "crisis")
    )
    voice_processed = use_voice_features

    print(f"\n[NODE: EMOTION_FUSION]  Text-based input: emotion={text_emotion} intensity={text_intensity:.0%} | gate_route={gate_route}")
    if use_voice_features:
        print("[NODE: EMOTION_FUSION] Voice features detected and route is therapeutic/crisis. Enforcing voice as authoritative.")
    elif voice_features and not voice_features_authoritative:
        print("[NODE: EMOTION_FUSION] Voice features present but marked fallback/non-authoritative; using text/gate mood.")
    elif voice_features and gate_route not in ("therapeutic", "crisis"):
        print(f"[NODE: EMOTION_FUSION] Voice features present but gate_route={gate_route!r}; ignoring voice for this route.")

    # ============================================
    # CASE 0: Therapeutic voice feature safety passthrough
    # voice_processed=True means the therapeutic route already ran Gemini audio
    # feature extraction on the transcript and vocal delivery.
    # No blending needed — apply safety checks directly on voice output.
    # ============================================
    if voice_processed:
        print("[NODE: EMOTION_FUSION] CASE 0: Therapeutic voice feature passthrough (authoritative override)")

        voice_emotion     = voice_features.get("emotion", "neutral")
        voice_intensity   = float(voice_features.get("intensity", voice_features.get("arousal", 0.5)))
        voice_primary_sub = voice_features.get("primary_sub_emotion") or voice_emotion
        voice_secondary   = voice_features.get("secondary_sub_emotions") or []
        voice_confidence  = float(voice_features.get("confidence", 0.0))
        voice_symptoms    = voice_features.get("detected_symptoms") or []
        voice_behaviors   = voice_features.get("detected_behaviors") or []
        voice_contexts    = voice_features.get("detected_contexts") or []

        print(
            f"[NODE: EMOTION_FUSION] Voice Data Details:\n"
            f"  Emotion: {voice_emotion} (confidence={voice_confidence:.0%})\n"
            f"  Intensity: {voice_intensity:.0%} (arousal={voice_features.get('arousal', 0.5):.0%})\n"
            f"  Acoustic cues: distress_index={float(voice_features.get('distress_index', 0.0)):.2f}, "
            f"pause_density={float(voice_features.get('pause_density', 0.25)):.2f}\n"
            f"  Sub-emotions: primary={voice_primary_sub}, secondary={voice_secondary}\n"
            f"  Handoff status: bypassing text-based mood analysis, using voice features as authoritative ground truth."
        )

        fused_emotion    = voice_emotion
        fused_intensity  = voice_intensity

        # Acoustic safety overrides (still apply as clinical safety net)
        fused_emotion, fused_intensity, override_applied, override_reason = _apply_acoustic_overrides(
            text_emotion=voice_emotion,   # voice IS the text in this path
            fused_emotion=fused_emotion,
            fused_intensity=fused_intensity,
            voice_features=voice_features,
        )
        if override_applied:
            print(f"[EMOTION_FUSION]  Acoustic override applied: {override_reason}")
            voice_primary_sub = voice_features.get("primary_sub_emotion") or (
                "hopelessness" if fused_emotion == "sadness"
                else "panic" if fused_emotion == "anxiety"
                else voice_primary_sub
            )

        # Passive ideation check on transcription
        raw_message = state.get("messages", [])
        raw_message = raw_message[-1].content if raw_message else ""
        transcription = state.get("transcription", "") or raw_message
        if _check_passive_ideation(transcription) and fused_emotion in ("joy", "surprise", "neutral"):
            print(
                f"[EMOTION_FUSION]  SAFETY OVERRIDE: Passive ideation in transcription  "
                f"{fused_emotion}  sadness at 0.65"
            )
            fused_emotion   = "sadness"
            fused_intensity = max(fused_intensity, 0.65)
            voice_primary_sub = "hopelessness"

        # Hedge word check on transcription
        if not _should_skip_hedge_reduction(state):
            fused_intensity = _apply_hedge_multiplier(transcription, fused_intensity)

        # Gate intensity caps and distress anchor guard
        fused_emotion, fused_intensity = _apply_gate_intensity_caps(state, fused_emotion, fused_intensity)
        fused_intensity = _apply_confidence_anchor_guard(state, fused_intensity)

        if str(fused_emotion or "").lower() in ANCHOR_LOW_SIGNAL_EMOTIONS:
            anchored_emotion = _anchored_distress_emotion(state, str(fused_emotion or "neutral").lower(), transcription)
            if anchored_emotion != fused_emotion and fused_intensity >= 0.5:
                fused_emotion = anchored_emotion

        print(
            f"[NODE: EMOTION_FUSION]  Fused (therapeutic voice): {fused_emotion.upper()} | "
            f"Intensity: {fused_intensity:.0%}"
        )
        metadata = _fusion_metadata(
            state=state,
            text_emotion=text_emotion,
            voice_emotion=voice_emotion,
            fused_emotion=fused_emotion,
            fused_intensity=fused_intensity,
            voice_confidence=voice_confidence,
            distress_index=float(voice_features.get("distress_index", 0.0)),
            override_applied=override_applied,
        )

        return {
            "emotion":                 fused_emotion,
            "intensity":               fused_intensity,
            "fused_emotion":           fused_emotion,
            "fused_intensity":         fused_intensity,
            "voice_processed":         True,
            "voice_features":          voice_features,
            "primary_sub_emotion":     voice_primary_sub,
            "secondary_sub_emotions":  voice_secondary,
            "detected_symptoms":       voice_symptoms,
            "detected_behaviors":      voice_behaviors,
            "detected_contexts":       voice_contexts,
            **metadata,
        }

    # ============================================
    # CASE 1: No voice data  passthrough text
    # Apply normalization + hedge + passive ideation checks only
    # ============================================
    if not voice_processed:
        print("[EMOTION_FUSION] Text-only mode (no voice data)")

        model_confidence  = state.get("confidence", text_intensity)
        normalized        = _normalize_intensity(text_emotion, text_intensity, model_confidence)
        if normalized != text_intensity:
            print(f"[EMOTION_FUSION] Intensity normalized: {text_intensity:.0%}  {normalized:.0%} ({text_emotion})")

        raw_message = state.get("messages", [])
        raw_message = raw_message[-1].content if raw_message else ""
        if _should_skip_hedge_reduction(state):
            final_intensity = normalized
            if normalized != text_intensity or any(hedge in raw_message.lower() for hedge in _HEDGE_WORDS):
                print(
                    "[EMOTION_FUSION] Hedge reduction skipped "
                    "(gate-confirmed disclosure)"
                )
        else:
            final_intensity = _apply_hedge_multiplier(raw_message, normalized)

        fused_emotion = text_emotion
        if _check_passive_ideation(raw_message) and fused_emotion in ("joy", "surprise", "neutral"):
            print(f"[EMOTION_FUSION]  SAFETY OVERRIDE: Passive ideation detected  "
                  f"{fused_emotion}  sadness at 0.65")
            fused_emotion   = "sadness"
            final_intensity = max(final_intensity, 0.65)

        fused_emotion, final_intensity = _apply_gate_intensity_caps(state, fused_emotion, final_intensity)
        final_intensity = _apply_confidence_anchor_guard(state, final_intensity)
        if str(fused_emotion or "").lower() in ANCHOR_LOW_SIGNAL_EMOTIONS:
            anchored_emotion = _anchored_distress_emotion(state, str(fused_emotion or "neutral").lower(), raw_message)
            if anchored_emotion != fused_emotion and final_intensity >= 0.5:
                fused_emotion = anchored_emotion
        if fused_emotion != text_emotion:
            if fused_emotion == "sadness":
                primary_sub_emotion = "hopelessness"
            elif fused_emotion == "anxiety":
                primary_sub_emotion = "panic"
            elif fused_emotion == "neutral":
                primary_sub_emotion = "neutral"
            elif fused_emotion == "joy":
                primary_sub_emotion = "relief"

        metadata = _fusion_metadata(
            state=state,
            text_emotion=text_emotion,
            voice_emotion=None,
            fused_emotion=fused_emotion,
            fused_intensity=final_intensity,
        )
        return {
            "fused_emotion":   fused_emotion,
            "fused_intensity": final_intensity,
            "primary_sub_emotion": primary_sub_emotion,
            "secondary_sub_emotions": secondary_sub_emotions,
            "detected_symptoms": detected_symptoms,
            "detected_behaviors": detected_behaviors,
            "detected_contexts": detected_contexts,
            **metadata,
        }

    # ============================================
    # CASE 2: Voice + Text 3-way fusion
    # ============================================
    voice_emotion      = voice_features.get("emotion", "neutral")
    voice_primary_sub  = voice_features.get("primary_sub_emotion")
    voice_secondary_subs = voice_features.get("secondary_sub_emotions") or []
    detected_symptoms = _merge_unique(detected_symptoms, voice_features.get("detected_symptoms") or [])
    detected_behaviors = _merge_unique(detected_behaviors, voice_features.get("detected_behaviors") or [])
    detected_contexts = _merge_unique(detected_contexts, voice_features.get("detected_contexts") or [])
    voice_confidence   = float(voice_features.get("confidence", 0.0))
    voice_arousal      = float(voice_features.get("arousal", 0.5))
    distress_index     = float(voice_features.get("distress_index", 0.0))

    print(f"[NODE: EMOTION_FUSION]  Voice: {voice_emotion} "
          f"(conf={voice_confidence:.0%}, arousal={voice_arousal:.0%}, "
          f"distress_index={distress_index:.2f})")

    #  Dynamic weight assignment 
    if voice_confidence >= 0.5:
        text_weight, voice_label_weight, acoustic_weight = 0.50, 0.30, 0.20
        mode = "balanced (voice high-conf)"
    else:
        text_weight, voice_label_weight, acoustic_weight = 0.70, 0.15, 0.15
        mode = "text-dominant (voice low-conf)"

    #  Compute voice intensity from arousal (voice_label contribution) 
    voice_intensity = voice_arousal

    #  3-way weighted intensity blend 
    # Text:           text_intensity from the text emotion path
    # Voice label:    Gemini-estimated arousal from audio delivery
    # Vocal cue:      Gemini-estimated distress_index
    raw_fused_intensity = round(
        text_weight * text_intensity
        + voice_label_weight * voice_intensity
        + acoustic_weight * distress_index,
        3
    )
    raw_fused_intensity = max(0.0, min(1.0, raw_fused_intensity))

    # Apply Fix 1 normalization AFTER fusion
    model_confidence = state.get("confidence", text_intensity)
    fused_intensity  = _normalize_intensity(text_emotion, raw_fused_intensity, model_confidence)

    #  Emotion label: pick winner 
    if text_emotion == voice_emotion:
        fused_emotion = text_emotion
        if voice_primary_sub and primary_sub_emotion in {None, "", "neutral", text_emotion}:
            primary_sub_emotion = voice_primary_sub
        secondary_sub_emotions = _merge_unique(
            secondary_sub_emotions,
            [voice_primary_sub] if voice_primary_sub and voice_primary_sub != primary_sub_emotion else [],
            voice_secondary_subs,
            limit=4,
        )
        # Agreement bonus: boost intensity slightly
        if distress_index > 0.5:
            boosted = min(1.0, fused_intensity * 1.10)
            print(f"[EMOTION_FUSION] Agreement + distress boost: {fused_intensity:.2f}  {boosted:.2f}")
            fused_intensity = round(boosted, 3)
    else:
        # Disagreement: valence-weighted selection
        text_val   = _EMOTION_VALENCE.get(text_emotion, 0.0) * text_weight
        voice_val  = _EMOTION_VALENCE.get(voice_emotion, 0.0) * voice_label_weight
        combined   = text_val + voice_val

        if combined < -0.3:
            fused_emotion = (
                text_emotion  if text_emotion  in _NEGATIVE_EMOTIONS
                else voice_emotion if voice_emotion in _NEGATIVE_EMOTIONS
                else text_emotion
            )
        elif combined > 0.3:
            fused_emotion = (
                text_emotion  if text_emotion  in _POSITIVE_EMOTIONS
                else voice_emotion if voice_emotion in _POSITIVE_EMOTIONS
                else text_emotion
            )
        else:
            fused_emotion = text_emotion   # ambiguous  defer to text

    #  Apply acoustic override rules 
    fused_emotion, fused_intensity, override_applied, override_reason = _apply_acoustic_overrides(
        text_emotion=text_emotion,
        fused_emotion=fused_emotion,
        fused_intensity=fused_intensity,
        voice_features=voice_features,
    )
    if override_applied:
        print(f"[NODE: EMOTION_FUSION]  Acoustic override applied: {override_reason}")

    fused_emotion, fused_intensity = _apply_gate_intensity_caps(state, fused_emotion, fused_intensity)
    fused_intensity = _apply_confidence_anchor_guard(state, fused_intensity)
    if str(fused_emotion or "").lower() in ANCHOR_LOW_SIGNAL_EMOTIONS:
        raw_message = state.get("messages", [])
        raw_message = raw_message[-1].content if raw_message else ""
        anchored_emotion = _anchored_distress_emotion(state, str(fused_emotion or "neutral").lower(), raw_message)
        if anchored_emotion != fused_emotion and fused_intensity >= 0.5:
            fused_emotion = anchored_emotion
    if fused_emotion != text_emotion:
        if fused_emotion == "sadness":
            primary_sub_emotion = voice_primary_sub or ("hopelessness" if override_applied else "sadness")
        elif fused_emotion == "anxiety":
            primary_sub_emotion = voice_primary_sub or ("panic" if override_applied else "stress")
        elif fused_emotion == "neutral":
            primary_sub_emotion = voice_primary_sub or "neutral"
        elif fused_emotion == "joy":
            primary_sub_emotion = voice_primary_sub or "relief"
        if voice_secondary_subs:
            secondary_sub_emotions = voice_secondary_subs

    print(f"[NODE: EMOTION_FUSION]  Fused: {fused_emotion.upper()} | "
          f"Intensity: {fused_intensity:.0%} | Mode: {mode}")
    metadata = _fusion_metadata(
        state=state,
        text_emotion=text_emotion,
        voice_emotion=voice_emotion,
        fused_emotion=fused_emotion,
        fused_intensity=fused_intensity,
        voice_confidence=voice_confidence,
        distress_index=distress_index,
        override_applied=override_applied,
    )

    return {
        "emotion":         fused_emotion,
        "intensity":       fused_intensity,
        "fused_emotion":   fused_emotion,
        "fused_intensity": fused_intensity,
        "primary_sub_emotion": primary_sub_emotion,
        "secondary_sub_emotions": secondary_sub_emotions,
        "detected_symptoms": detected_symptoms,
        "detected_behaviors": detected_behaviors,
        "detected_contexts": detected_contexts,
        **metadata,
    }
