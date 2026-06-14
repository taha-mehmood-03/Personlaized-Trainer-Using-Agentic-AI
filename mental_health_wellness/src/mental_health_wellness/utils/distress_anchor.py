"""Shared helpers for preserving session distress anchors across short turns.

ANCHOR SYSTEM INVARIANT (v12.0):
  Once a genuine emotional disclosure establishes an anchor, that anchor is the
  session-level emotional truth.  Subsequent turns — narrative answers, short
  consent phrases — may not decrease it.  Only explicit recovery signals
  (positive_feedback / recovery gate routes) are permitted to let the anchor
  naturally de-escalate.

KEY CONSTANTS:
  ESTABLISHED_ANCHOR_THRESHOLD = 0.45  (was 0.50 — hedged disclosures land ~0.30–0.50
                                         after hedge penalty; 0.45 is the floor above
                                         genuine calm/mild states so the hold guard fires)
  FIRST_DISCLOSURE_FLOOR       = 0.50  (minimum intensity for ANY first therapeutic
                                         disclosure, regardless of model confidence or
                                         hedging.  Ensures an anchor is always written
                                         from a genuine emotional opening turn.)
  DISCLOSURE_FLOOR             = 0.55  (floor for subsequent low-confidence disclosures
                                         when an anchor already exists)
"""

from __future__ import annotations

from typing import Mapping, Sequence


ANCHOR_CONFIDENCE_THRESHOLD   = 0.65
DISCLOSURE_FLOOR              = 0.55
FIRST_DISCLOSURE_FLOOR        = 0.50   # v12.0: floor for the very first disclosure turn
ESTABLISHED_ANCHOR_THRESHOLD  = 0.45   # v12.0: lowered from 0.50 (see module docstring)

# Routes that are genuine emotional disclosures
DISCLOSURE_ROUTES = {"therapeutic", "crisis"}
DISCLOSURE_FLAGS  = {"emotional_disclosure", "new_emotional_disclosure"}

# Routes that are contextual / non-disclosure follow-ups
FOLLOWUP_ROUTES = {
    "contextual_followup",
    "chitchat",
    "memory_query",
    "positive_feedback",
    "technique_follow_up",
}

# Routes where the user is signalling positive outcome / de-escalation.
# These are the ONLY routes where anchor_write_policy will permit a decrease.
RECOVERY_ROUTES = {"positive_feedback"}
RECOVERY_FLAGS  = {"positive_feedback", "recovery_signal", "feeling_better"}

NEGATIVE_EMOTIONS = {"anxiety", "sadness", "anger", "fear", "disgust"}
LOW_SIGNAL_EMOTIONS = {
    "neutral",
    "joy",
    "surprise",
    "calm",
    "content",
    "desire",
    "relief",
    "acknowledgement",
    "approval",
    "optimism",
    "gratitude",
}


# ============================================================
# PRIMITIVE HELPERS
# ============================================================

def as_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def gate_confirms_disclosure(route: str | None, flags: Sequence[str] | None) -> bool:
    flag_set = {str(flag) for flag in (flags or [])}
    return str(route or "") in DISCLOSURE_ROUTES or bool(flag_set & DISCLOSURE_FLAGS)


def is_recovery_turn(route: str | None, flags: Sequence[str] | None) -> bool:
    """Return True when the current turn is a genuine positive de-escalation signal."""
    flag_set = {str(flag) for flag in (flags or [])}
    return str(route or "") in RECOVERY_ROUTES or bool(flag_set & RECOVERY_FLAGS)


def is_first_disclosure(state: Mapping) -> bool:
    """Return True when no prior anchor has been established this session.

    'First disclosure' means the anchor fields are unset (None / 0.0), i.e. this
    is the opening emotional turn.  The gate must have confirmed it as therapeutic.
    """
    last = state.get("last_detected_intensity")
    peak = state.get("peak_distress_intensity")
    return (last is None or as_float(last, 0.0) < 0.05) and (peak is None or as_float(peak, 0.0) < 0.05)


def has_active_therapeutic_thread(state: Mapping) -> bool:
    """Return True when structured context indicates an active clinical concern."""
    return bool(
        state.get("primary_concern")
        or state.get("active_thread_summary")
        or state.get("triggering_context")
        or state.get("core_belief")
    )


# ============================================================
# ANCHOR VALUE READERS
# ============================================================

def distress_anchor_value(*states: Mapping | None) -> float:
    values: list[float] = []
    for state in states:
        if not state:
            continue
        values.append(as_float(state.get("last_detected_intensity"), 0.0))
        values.append(as_float(state.get("peak_distress_intensity"), 0.0))
    return max(values or [0.0])


def anchored_negative_emotion(*states: Mapping | None) -> str | None:
    for state in states:
        if not state:
            continue
        emotion = str(state.get("last_detected_emotion") or "").lower()
        if emotion in NEGATIVE_EMOTIONS:
            return emotion
    return None


# ============================================================
# CONSENT TURN DETECTION
# ============================================================

def is_short_consent_turn(route: str | None, flags: Sequence[str] | None, message: str | None) -> bool:
    flag_set = {str(flag) for flag in (flags or [])}
    if "accept_technique" not in flag_set:
        return False
    text = (message or "").strip()
    return len(text) < 60 or str(route or "") == "technique_request"


def should_skip_mood_for_anchor_consent(state: Mapping, message: str | None) -> bool:
    return (
        str(state.get("gate_route") or "") == "technique_request"
        and is_short_consent_turn(state.get("gate_route"), state.get("gate_context_flags") or [], message)
        and distress_anchor_value(state) >= ESTABLISHED_ANCHOR_THRESHOLD
    )


def calibrate_low_confidence_disclosure_intensity(state: Mapping, intensity: float) -> tuple[float, str]:
    """Return a planner-safe intensity for low-confidence disclosure reads.

    v12.0 additions:
    - First disclosures (no prior anchor) on a therapeutic route are floored to
      FIRST_DISCLOSURE_FLOOR (0.50) so that hedged opening phrases always write
      a meaningful anchor.  This is the root fix for the hedge-penalty problem.
    - Existing anchor hold fires at ESTABLISHED_ANCHOR_THRESHOLD = 0.45 (was 0.50)
      so hedged-phrase anchors in the 0.45–0.50 range are now protected.
    """
    confidence = as_float(state.get("confidence"), 0.0)
    route = str(state.get("gate_route") or "")
    flags = state.get("gate_context_flags") or []
    anchor = distress_anchor_value(state)
    disclosure = gate_confirms_disclosure(route, flags)

    if confidence >= ANCHOR_CONFIDENCE_THRESHOLD:
        # High-confidence read: trust it, but never let the anchor decrease below
        # FIRST_DISCLOSURE_FLOOR on a first disclosure even when model is confident.
        if disclosure and is_first_disclosure(state):
            floored = max(float(intensity), FIRST_DISCLOSURE_FLOOR)
            if floored != intensity:
                return floored, "first_disclosure_confidence_floored"
        return intensity, "confidence_ok"

    # Low-confidence branch ---
    if anchor >= ESTABLISHED_ANCHOR_THRESHOLD:
        # Monotonic invariant: an established anchor may not be lowered by a
        # low-confidence read.  Return the anchor unchanged.
        return anchor, "held_existing_anchor_low_confidence"

    if disclosure and is_first_disclosure(state):
        # First-ever disclosure with low confidence (e.g. hedged phrase + model
        # uncertainty). Force to FIRST_DISCLOSURE_FLOOR so an anchor is always written.
        floored = max(float(intensity), FIRST_DISCLOSURE_FLOOR)
        return floored, "first_disclosure_floored"

    if disclosure:
        return max(float(intensity), DISCLOSURE_FLOOR), "floored_low_confidence_disclosure"

    return intensity, "low_confidence_ambiguous"


def anchor_write_policy(
    state: Mapping,
    previous: Mapping | None,
    intensity: float | None,
) -> tuple[bool, float | None, str]:
    """Decide whether this turn may update the distress anchor.

    SESSION INVARIANT (v12.0):
      The distress anchor is monotonically non-decreasing within a session.
      It may only decrease when the user explicitly signals de-escalation via a
      recovery route (positive_feedback, recovery_signal flag, etc.).
      Any other turn — narrative answers, consent phrases, clarifying questions —
      that reads a lower intensity than the existing anchor must NOT overwrite it.

    Returns (should_write: bool, anchor_intensity: float | None, reason: str).
    """
    route = str(state.get("gate_route") or "")
    messages = state.get("messages") or []
    current_message = getattr(messages[-1], "content", "") if messages else ""
    flags = state.get("gate_context_flags") or []

    # ── Recovery exception: check FIRST — positive_feedback is in FOLLOWUP_ROUTES,
    # so it must be whitelisted before the followup block fires. This is the ONLY
    # path where a lower intensity is permitted to write.
    if intensity is not None and is_recovery_turn(route, flags):
        return True, float(intensity), "recovery_allows_decrease"

    # ── Hard blocks: these turns must never update the anchor ──────────────
    if is_short_consent_turn(route, flags, current_message):
        return False, None, "short_consent_preserve_anchor"
    if route in FOLLOWUP_ROUTES:
        return False, None, "followup_route_preserve_anchor"
    if intensity is None:
        return False, None, "missing_intensity"

    # (Recovery exception already handled above)

    confidence = as_float(state.get("confidence"), 0.0)
    existing_anchor = distress_anchor_value(previous, state)
    disclosure = gate_confirms_disclosure(route, flags)

    # ── High-confidence read ───────────────────────────────────────────────
    if confidence >= ANCHOR_CONFIDENCE_THRESHOLD:
        if disclosure and is_first_disclosure(state):
            # First disclosure: floor to FIRST_DISCLOSURE_FLOOR regardless.
            anchored = max(float(intensity), FIRST_DISCLOSURE_FLOOR)
            return True, anchored, "first_disclosure_confidence_floored" if anchored != intensity else "confidence_ok"

        # Monotonic invariant: never let a high-confidence read lower a real anchor.
        if existing_anchor >= ESTABLISHED_ANCHOR_THRESHOLD and float(intensity) < existing_anchor:
            return False, existing_anchor, "monotonic_hold_high_confidence"

        return True, float(intensity), "confidence_ok"

    # ── Low-confidence read ────────────────────────────────────────────────
    if existing_anchor >= ESTABLISHED_ANCHOR_THRESHOLD:
        # Monotonic invariant: hold without exception.
        return False, existing_anchor, "hold_existing_anchor_low_confidence"

    if disclosure and is_first_disclosure(state):
        # First-ever disclosure, low confidence → floor to FIRST_DISCLOSURE_FLOOR.
        anchored = max(float(intensity), FIRST_DISCLOSURE_FLOOR)
        return True, anchored, "first_disclosure_floored"

    if disclosure:
        return True, max(float(intensity), DISCLOSURE_FLOOR), "floor_low_confidence_disclosure"

    return False, None, "skip_low_confidence_ambiguous"
