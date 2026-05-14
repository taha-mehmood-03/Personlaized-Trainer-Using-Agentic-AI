"""
Emotion Fusion Node  3-Way Acoustic-Aware Fusion

ARCHITECTURE NODE 2.7:
Purpose: Merge text-based emotion (DistilBERT) with voice label (Wav2Vec2)
         AND raw acoustic features (distress_index, arousal, pause_density)
         into a single high-confidence, clinically-safe fused emotion signal.
Runs AFTER mood_analyzer, BEFORE trend_analyzer
No LLM call  pure deterministic Python.

FUSION LOGIC (v2):
  Text-only (no audio):            fused = text (passthrough with normalization)
  Voice high confidence (0.5):    text:voice label:acoustic = 0.50 : 0.30 : 0.20
  Voice low confidence (<0.5):     text:voice label:acoustic = 0.70 : 0.15 : 0.15

ACOUSTIC OVERRIDE RULES (new):
  distress_index > 0.65 AND text == neutral  override emotion to "sadness"
  arousal > 0.75        AND text == neutral  override emotion to "anxiety"
  pause_density > 0.40  AND intensity < 0.4  boost fused_intensity +0.15
  Voice + text agree    AND distress_index > 0.5  boost fused_intensity +10%
  Passive ideation phrases in text  safety override to sadness at 0.65

Output:
  fused_emotion:  str    (winning emotion label)
  fused_intensity: float (weighted + acoustically-adjusted intensity)
"""

from ..agent.state import MentalHealthState

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

# ============================================
# FIX 2: PASSIVE IDEATION SAFETY OVERRIDE
# ============================================
_PASSIVE_IDEATION_PHRASES = {
    "sleep forever", "not wake up", "never wake up", "disappear forever",
    "wish i wasn't here", "wish i was gone", "wish i were gone",
    "better off without me", "don't want to be here anymore",
    "no point in waking up", "never existed", "want to disappear",
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


def _check_passive_ideation(message: str) -> bool:
    """Detect passive suicidal ideation phrases misclassified by emotion model."""
    msg_lower = message.lower()
    return any(phrase in msg_lower for phrase in _PASSIVE_IDEATION_PHRASES)


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
    voice_features   = state.get("voice_features") or {}
    voice_processed  = bool(voice_features) and state.get("voice_processed", False)

    print(f"\n[NODE: EMOTION_FUSION]  Text: {text_emotion} ({text_intensity:.0%})")

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
        final_intensity = _apply_hedge_multiplier(raw_message, normalized)

        fused_emotion = text_emotion
        if _check_passive_ideation(raw_message) and fused_emotion in ("joy", "surprise", "neutral"):
            print(f"[EMOTION_FUSION]  SAFETY OVERRIDE: Passive ideation detected  "
                  f"{fused_emotion}  sadness at 0.65")
            fused_emotion   = "sadness"
            final_intensity = max(final_intensity, 0.65)

        return {
            "fused_emotion":   fused_emotion,
            "fused_intensity": final_intensity,
        }

    # ============================================
    # CASE 2: Voice + Text 3-way fusion
    # ============================================
    voice_emotion      = voice_features.get("emotion", "neutral")
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
    # Text:           text_intensity (DistilBERT confidence  intensity)
    # Voice label:    voice_arousal  (wav2vec2 arousal proxy)
    # Acoustic:       distress_index (psychoacoustic composite)
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

    print(f"[NODE: EMOTION_FUSION]  Fused: {fused_emotion.upper()} | "
          f"Intensity: {fused_intensity:.0%} | Mode: {mode}")

    return {
        "fused_emotion":   fused_emotion,
        "fused_intensity": fused_intensity,
    }
