"""
Emotion Fusion Node - Weighted combination of text and voice emotion

ARCHITECTURE NODE 2.7:
Purpose: Merge text-based emotion (DistilBERT) with voice-based emotion (Wav2Vec2)
         to produce a single, high-confidence fused emotion signal.
Runs AFTER mood_analyzer, BEFORE trend_analyzer
No LLM call - pure Python weighted averaging

FUSION LOGIC:
  - Text-only (no audio):  fused = text (passthrough)
  - Voice high confidence:  fused = 0.60 * text + 0.40 * voice
  - Voice low confidence:   fused = 0.85 * text + 0.15 * voice

Output:
  - fused_emotion: str   (the winning emotion label)
  - fused_intensity: float (weighted intensity)
"""

from ..agent.state import MentalHealthState

# Canonical emotion ordering for intensity-weighted selection
_NEGATIVE_EMOTIONS = {"anger", "sadness", "fear", "anxiety", "disgust"}
_POSITIVE_EMOTIONS = {"joy", "surprise"}

# Map sentiment polarity for tie-breaking
_EMOTION_VALENCE = {
    "anger": -0.8, "disgust": -0.7, "fear": -0.9, "anxiety": -0.85,
    "sadness": -0.9, "neutral": 0.0, "surprise": 0.3, "joy": 0.9,
}

# ============================================
# FIX 1: INTENSITY NORMALIZATION
# Separates model confidence from emotional intensity.
# A high-confidence neutral classification should NOT produce
# a high intensity score — neutral means low arousal.
# ============================================
_NEUTRAL_INTENSITY_CAP = 0.20   # neutral never exceeds 20%
_LOW_SIGNAL_EMOTIONS = {"neutral", "calm", "content"}
_LOW_SIGNAL_INTENSITY_CAP = 0.30  # other low-signal emotions capped at 30%

# ============================================
# FIX 2: PASSIVE IDEATION SAFETY OVERRIDE
# These phrases are clinically meaningful but the RoBERTa model reads
# literal surface positivity ("sleep", "disappear") and scores them as JOY.
# Override to sadness at therapeutic threshold.
# ============================================
_PASSIVE_IDEATION_PHRASES = {
    "sleep forever", "not wake up", "never wake up", "disappear forever",
    "wish i wasn't here", "wish i was gone", "wish i were gone",
    "better off without me", "don't want to be here anymore",
    "no point in waking up", "never existed", "want to disappear",
}

# ============================================
# FIX 3: HEDGE-WORD INTENSITY CALIBRATION
# When the user explicitly softens an emotion with hedging language,
# the model still scores full intensity. Apply a 50% multiplier.
# This also fixes no_action mis-routing for hedged messages.
# ============================================
_HEDGE_WORDS = [
    "a little", "a bit", "slightly", "kind of", "kinda", "somewhat",
    "a tad", "mildly", "not that", "not very", "not too", "pretty tired",
    "pretty bored", "sort of", "a small",
]
_HEDGE_MULTIPLIER = 0.50


def _normalize_intensity(label: str, raw_intensity: float, model_confidence: float) -> float:
    """
    Normalize emotional intensity to prevent model confidence from inflating
    perceived emotional arousal in low-signal or neutral messages.
    """
    if label == "neutral":
        return min(raw_intensity, _NEUTRAL_INTENSITY_CAP)
    if label in _LOW_SIGNAL_EMOTIONS:
        return min(raw_intensity, _LOW_SIGNAL_INTENSITY_CAP)
    return raw_intensity


def _apply_hedge_multiplier(message: str, intensity: float) -> float:
    """
    FIX 3: Reduce intensity when user uses softening/hedging language.
    
    "I'm a little annoyed" should NOT score the same as "I'm furious".
    Detects hedges and applies a 50% intensity reduction.
    """
    msg_lower = message.lower()

    # Exception for positive progress: "a bit better" is a standard confirmation, not a hedge that means low arousal.
    if "better" in msg_lower and any(h in msg_lower for h in ["a bit", "a little"]):
         return intensity

    for hedge in _HEDGE_WORDS:
        if hedge in msg_lower:
            reduced = round(intensity * _HEDGE_MULTIPLIER, 3)
            print(f"[EMOTION_FUSION] Hedge word '{hedge}' detected — reducing intensity: {intensity:.0%} -> {reduced:.0%}")
            return reduced
    return intensity


def _check_passive_ideation(message: str) -> bool:
    """
    FIX 2: Detect passive suicidal ideation phrases that the emotion model
    misclassifies as positive emotions due to literal surface-level reading.
    """
    msg_lower = message.lower()
    return any(phrase in msg_lower for phrase in _PASSIVE_IDEATION_PHRASES)


def emotion_fusion_node(state: MentalHealthState) -> dict:
    """
    EMOTION FUSION NODE - Merge text + voice emotion into single signal.

    Process:
    1. Read text emotion (from mood_analyzer_node)
    2. Read voice features (from voice_preprocessing_node, if present)
    3. Compute weighted fusion based on voice confidence
    4. Output fused_emotion and fused_intensity

    No LLM call — pure deterministic Python.
    """

    text_emotion = state.get("emotion", "neutral")
    text_intensity = state.get("intensity", 0.5)
    voice_features = state.get("voice_features") or {}
    voice_processed = bool(voice_features)

    print(f"\n[NODE: EMOTION_FUSION] 🔗 Text: {text_emotion} ({text_intensity:.0%})")

    # ============================================
    # CASE 1: No voice data → passthrough text
    # Apply Fix 1: normalize intensity for low-signal emotions
    # ============================================
    if not voice_processed:
        print("[EMOTION_FUSION] Text-only mode (no voice data)")
        # FIX 1: Normalize intensity — prevent neutral from having high intensity
        model_confidence = state.get("confidence", text_intensity)
        normalized_intensity = _normalize_intensity(text_emotion, text_intensity, model_confidence)
        if normalized_intensity != text_intensity:
            print(f"[EMOTION_FUSION] Intensity normalized: {text_intensity:.0%} -> {normalized_intensity:.0%} (label: {text_emotion})")
        
        # FIX 3: Apply hedge-word multiplier
        raw_message = state.get("messages", [])
        raw_message = raw_message[-1].content if raw_message else ""
        final_intensity = _apply_hedge_multiplier(raw_message, normalized_intensity)
        
        # FIX 2: Passive ideation safety override
        fused_emotion = text_emotion
        if _check_passive_ideation(raw_message) and fused_emotion in ("joy", "surprise", "neutral"):
            print(f"[EMOTION_FUSION] SAFETY OVERRIDE: Passive ideation detected in message — overriding {fused_emotion}->sadness at 0.65")
            fused_emotion = "sadness"
            final_intensity = max(final_intensity, 0.65)  # Ensure therapeutic threshold
        
        return {
            "fused_emotion": fused_emotion,
            "fused_intensity": final_intensity,
        }

    # ============================================
    # CASE 2: Voice + text fusion
    # ============================================
    voice_emotion = voice_features.get("emotion", "neutral")
    voice_confidence = float(voice_features.get("confidence", 0.0))
    voice_arousal = float(voice_features.get("arousal", 0.5))

    print(f"[NODE: EMOTION_FUSION] 🎤 Voice: {voice_emotion} (conf={voice_confidence:.0%}, arousal={voice_arousal:.0%})")

    # Derive voice intensity from arousal (0-1 scale)
    voice_intensity = voice_arousal

    # Dynamic weight assignment based on voice confidence
    if voice_confidence >= 0.5:
        text_weight, voice_weight = 0.60, 0.40
        mode = "balanced (voice high-conf)"
    else:
        text_weight, voice_weight = 0.85, 0.15
        mode = "text-dominant (voice low-conf)"

    # ============================================
    # WEIGHTED INTENSITY (with Fix 1 normalization)
    # ============================================
    raw_fused_intensity = round(
        text_weight * text_intensity + voice_weight * voice_intensity, 3
    )
    raw_fused_intensity = max(0.0, min(1.0, raw_fused_intensity))
    # FIX 1: Apply normalization AFTER fusion
    model_confidence = state.get("confidence", text_intensity)
    fused_intensity = _normalize_intensity(text_emotion, raw_fused_intensity, model_confidence)

    # ============================================
    # EMOTION LABEL SELECTION
    # ============================================
    # If both agree → that emotion wins trivially
    if text_emotion == voice_emotion:
        fused_emotion = text_emotion
    else:
        # Pick the more *negative* emotion when they disagree
        # (therapeutic safety: lean towards detecting distress)
        text_val = _EMOTION_VALENCE.get(text_emotion, 0.0) * text_weight
        voice_val = _EMOTION_VALENCE.get(voice_emotion, 0.0) * voice_weight
        combined_valence = text_val + voice_val

        if combined_valence < -0.3:
            # Negative — pick the most negative contributor
            fused_emotion = (
                text_emotion if text_emotion in _NEGATIVE_EMOTIONS
                else voice_emotion if voice_emotion in _NEGATIVE_EMOTIONS
                else text_emotion
            )
        elif combined_valence > 0.3:
            fused_emotion = (
                text_emotion if text_emotion in _POSITIVE_EMOTIONS
                else voice_emotion if voice_emotion in _POSITIVE_EMOTIONS
                else text_emotion
            )
        else:
            # Ambiguous — defer to text (higher baseline accuracy)
            fused_emotion = text_emotion

    print(f"[NODE: EMOTION_FUSION] ✅ Fused: {fused_emotion.upper()} | "
          f"Intensity: {fused_intensity:.0%} | Mode: {mode}")

    return {
        "fused_emotion": fused_emotion,
        "fused_intensity": fused_intensity,
    }
