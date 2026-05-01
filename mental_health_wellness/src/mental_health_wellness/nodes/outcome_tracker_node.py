"""
Outcome Tracker Node - Technique effectiveness measurement

ARCHITECTURE NODE 8:
Purpose: Measure whether a previously suggested technique improved the user's 
         emotional state by comparing before/after emotion and intensity.
Runs AFTER session_saver (last node before END)
No LLM call - pure Python comparison + DB write

LOGIC:
  1. Check if a technique was recommended EARLIER in this session
  2. If yes, compare current emotion/intensity to the pre-technique state
  3. Calculate effectiveness: (intensity_before - intensity_after) / intensity_before
  4. Save TechniqueOutcome record to database
  5. Update BehaviorProfile based on technique acceptance patterns

Output:
  - (No state changes — pure side-effect node for analytics)
"""

from ..agent.state import MentalHealthState
from ..agent.preprocessing import normalize_emotion


# Prisma Emotion enum mapping (same as session_saver for consistency)
_EMOTION_TO_PRISMA = {
    "anger": "ANGER", "disgust": "DISGUST", "fear": "FEAR",
    "joy": "JOY", "neutral": "NEUTRAL", "sadness": "SADNESS",
    "surprise": "SURPRISE", "anxiety": "ANXIETY",
    "happy": "JOY", "sad": "SADNESS", "angry": "ANGER",
    "anxious": "ANXIETY", "worried": "ANXIETY", "scared": "FEAR",
    "frustrated": "ANGER", "hopeless": "SADNESS", "stressed": "ANXIETY",
    "depressed": "SADNESS", "overwhelmed": "ANXIETY",
}


async def track_outcome(state: MentalHealthState) -> dict:
    """
    OUTCOME TRACKER NODE - Measure technique effectiveness.

    Process:
    1. Check if a technique was delivered this session
    2. Look for previous emotional state (from trend_window)
    3. Compare before/after → effectiveness score
    4. Save TechniqueOutcome to database
    5. Update BehaviorProfile

    No LLM call — pure Python/SQL.
    Returns empty dict (side-effect only node).
    """

    recommended_technique = state.get("recommended_technique") or {}
    session_id = state.get("session_id", "")
    user_id = state.get("user_id", "")
    current_emotion = state.get("fused_emotion", state.get("emotion", "neutral"))
    current_intensity = state.get("fused_intensity", state.get("intensity", 0.5))
    trend_window = state.get("trend_window", [])
    strategy = state.get("conversation_strategy", "validate_only")

    print(f"\n[NODE: OUTCOME_TRACKER] 📊 Tracking outcomes for session: "
          f"{session_id[:20] if session_id else 'UNKNOWN'}...")

    # ============================================
    # GUARD: Only track if a technique was actually delivered
    # ============================================
    technique_id = recommended_technique.get("id", "")
    technique_name = recommended_technique.get("name", "")

    if not technique_id or strategy not in ("suggest_technique", "reframe"):
        print("[NODE: OUTCOME_TRACKER] ℹ️ No technique delivered — skipping")
        return {}

    # ============================================
    # FIX 5: WITHIN-SESSION BASELINE ONLY
    # Use session_start_emotion/intensity set at the BEGINNING of this session
    # (first turn). NEVER use cross-session historical mood from user_stats.
    # trend_window[-2] may contain cross-session DB logs — unsafe to rely on.
    # ============================================

    # Capture session start emotion on first turn if not already set
    # ============================================
    # FIX 4 + FIX 5: ACCURATE BEFORE-STATE BASELINE
    # Prefer technique_delivery_emotion/intensity (set the moment the technique was delivered).
    # Fallback to session_start_emotion/intensity (set at turn 1).
    # NEVER use cross-session historical mood.
    # This ensures effectiveness measures "did emotions improve AFTER the technique?"
    # not "did emotions change during the entire 15-message session?"
    # ============================================

    technique_delivery_emotion = state.get("technique_delivery_emotion")
    technique_delivery_intensity = state.get("technique_delivery_intensity")
    session_start_emotion = state.get("session_start_emotion")
    session_start_intensity = state.get("session_start_intensity")

    if technique_delivery_emotion is not None and technique_delivery_intensity is not None:
        # Best case: we have the exact delivery-moment snapshot
        emotion_before = technique_delivery_emotion
        intensity_before = float(technique_delivery_intensity)
        print("[NODE: OUTCOME_TRACKER] Using technique-delivery-moment baseline (FIX 4)")
    elif session_start_emotion is not None and session_start_intensity is not None:
        # Second best: use session-start baseline
        emotion_before = session_start_emotion
        intensity_before = float(session_start_intensity)
        print("[NODE: OUTCOME_TRACKER] Using session-start baseline (FIX 5 fallback)")
    else:
        print("[NODE: OUTCOME_TRACKER] No within-session baseline found — skipping outcome record")
        print("[NODE: OUTCOME_TRACKER] Baseline will be captured next turn")
        return {}

    emotion_after = current_emotion
    intensity_after = current_intensity

    # ============================================
    # STEP 2: CALCULATE EFFECTIVENESS
    # ============================================

    if intensity_before > 0:
        effectiveness = round(
            (intensity_before - intensity_after) / intensity_before, 3
        )
    else:
        effectiveness = 0.0

    effectiveness = max(-1.0, min(1.0, effectiveness))  # Clamp

    eff_label = "positive" if effectiveness > 0 else "negative" if effectiveness < 0 else "neutral"
    print(f"[NODE: OUTCOME_TRACKER] 📈 Technique: {technique_name}")
    print(f"[NODE: OUTCOME_TRACKER]   Before: {emotion_before} ({intensity_before:.0%})")
    print(f"[NODE: OUTCOME_TRACKER]   After:  {emotion_after} ({intensity_after:.0%})")
    print(f"[NODE: OUTCOME_TRACKER]   Effectiveness: {effectiveness:+.0%} ({eff_label})")

    # ============================================
    # STEP 3: SAVE TO DATABASE
    # ============================================

    try:
        from ..db.client import get_prisma_client
        prisma = await get_prisma_client()

        # Map emotions to Prisma enum
        norm_before = normalize_emotion(emotion_before) if emotion_before else "neutral"
        norm_after = normalize_emotion(emotion_after) if emotion_after else "neutral"
        db_emotion_before = _EMOTION_TO_PRISMA.get(norm_before.lower(), "NEUTRAL")
        db_emotion_after = _EMOTION_TO_PRISMA.get(norm_after.lower(), "NEUTRAL")

        await prisma.techniqueoutcome.create(
            data={
                "sessionId": session_id,
                "techniqueId": technique_id,
                "emotionBefore": db_emotion_before,
                "emotionAfter": db_emotion_after,
                "intensityBefore": intensity_before,
                "intensityAfter": intensity_after,
                "effectiveness": effectiveness,
            }
        )
        print(f"[NODE: OUTCOME_TRACKER] ✅ TechniqueOutcome saved")

    except Exception as e:
        print(f"[NODE: OUTCOME_TRACKER] ⚠️ Failed to save outcome: {str(e)[:100]}")

    # ============================================
    # STEP 4: UPDATE BEHAVIOR PROFILE
    # ============================================

    try:
        await _update_behavior_profile(user_id, strategy, effectiveness)
    except Exception as e:
        print(f"[NODE: OUTCOME_TRACKER] ⚠️ Failed to update behavior profile: {str(e)[:100]}")

    return {}


async def _update_behavior_profile(
    user_id: str, strategy: str, effectiveness: float
) -> None:
    """
    Update user's BehaviorProfile based on how they respond to strategies.
    Uses exponential moving average for smooth adaptation.
    """
    if not user_id:
        return

    try:
        from ..db.client import get_prisma_client
        prisma = await get_prisma_client()

        profile = await prisma.behaviorprofile.find_unique(
            where={"userId": user_id}
        )

        if profile is None:
            # Create initial profile
            await prisma.behaviorprofile.create(
                data={
                    "userId": user_id,
                    "prefersAdvice": strategy == "suggest_technique",
                    "prefersListening": strategy == "validate_only",
                    "prefersShortResponse": False,
                    "avgTechniqueAcceptance": max(0.0, effectiveness),
                }
            )
            print(f"[NODE: OUTCOME_TRACKER] ✅ Created new BehaviorProfile for user")
        else:
            # EMA update: new_avg = 0.7 * old_avg + 0.3 * new_value
            alpha = 0.3
            old_avg = float(profile.avgTechniqueAcceptance or 0.5)
            new_avg = round(alpha * max(0.0, effectiveness) + (1 - alpha) * old_avg, 3)
            new_avg = max(0.0, min(1.0, new_avg))

            await prisma.behaviorprofile.update(
                where={"userId": user_id},
                data={
                    "avgTechniqueAcceptance": new_avg,
                    "prefersAdvice": strategy == "suggest_technique",
                    "prefersListening": strategy == "validate_only",
                }
            )
            print(f"[NODE: OUTCOME_TRACKER] ✅ Updated BehaviorProfile (acceptance={new_avg:.0%})")

    except Exception as e:
        print(f"[NODE: OUTCOME_TRACKER] ⚠️ Behavior profile error: {str(e)[:100]}")
