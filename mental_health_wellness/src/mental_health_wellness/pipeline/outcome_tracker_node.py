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
  5. Update PsychProfile based on technique acceptance patterns

Output:
  - (No state changes  pure side-effect node for analytics)
"""

from datetime import datetime, timezone, timedelta

from ..agent.state import MentalHealthState
from ..agent.preprocessing import normalize_emotion
from ..utils.turn_lifecycle import RESOLUTION_TURN_TYPES, has_new_emotional_content, normalize_turn_type


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


def _db_emotion(value: str | None) -> str:
    norm = normalize_emotion(value or "neutral")
    return _EMOTION_TO_PRISMA.get(str(norm).lower(), "NEUTRAL")


def _effectiveness(intensity_before: float, intensity_after: float) -> float:
    if intensity_before > 0:
        value = (intensity_before - intensity_after) / intensity_before
    else:
        value = 0.0
    return max(-1.0, min(1.0, round(value, 3)))


async def _create_pending_outcome(state: MentalHealthState, technique: dict) -> dict:
    session_id = state.get("session_id", "")
    if not session_id:
        return {}
    technique_id = technique.get("id") or technique.get("technique_id") or technique.get("techniqueId")
    if not technique_id:
        return {}

    try:
        from ..db.client import get_prisma_client

        prisma = await get_prisma_client()
        existing = await prisma.techniqueoutcome.find_first(
            where={
                "sessionId": session_id,
                "techniqueId": technique_id,
                "intensityAfter": None,
            },
            order={"createdAt": "desc"},
        )
        if existing:
            print("[NODE: OUTCOME_TRACKER] Pending TechniqueOutcome already exists")
            return {"pending_outcome_id": existing.id}

        current_emotion = state.get("fused_emotion", state.get("emotion", "neutral"))
        current_intensity = float(state.get("fused_intensity", state.get("intensity", 0.5)) or 0.5)

        # GAP 6: If intensity has decayed significantly from peak (>0.15 gap), use the
        # peak so that intensityBefore reflects what the user actually disclosed, not a
        # follow-up turn reading that has been progressively attenuated.
        peak_intensity = float(state.get("peak_distress_intensity") or current_intensity)
        intensity_before = peak_intensity if (peak_intensity - current_intensity) > 0.15 else current_intensity

        outcome = await prisma.techniqueoutcome.create(
            data={
                "sessionId": session_id,
                "techniqueId": technique_id,
                "emotionBefore": _db_emotion(current_emotion),
                "subEmotionBefore": state.get("primary_sub_emotion"),
                "symptomsBefore": state.get("detected_symptoms") or [],
                "behaviorsBefore": state.get("detected_behaviors") or [],
                "intensityBefore": intensity_before,
                "interventionType": "pending_technique_offer",
                "followThrough": None,
                "confidence": None,
            }
        )
        print(f"[NODE: OUTCOME_TRACKER] Pending TechniqueOutcome created: {outcome.id}")
        return {"pending_outcome_id": outcome.id}
    except Exception as e:
        print(f"[NODE: OUTCOME_TRACKER] Pending outcome create failed: {str(e)[:100]}")
        return {}


def _follow_through_from_behaviors(behaviors: list[str] | None) -> bool | None:
    signals = {str(item or "").lower().strip() for item in (behaviors or [])}
    if signals & {"completed_technique", "tried_exercise", "practiced_technique", "used_technique"}:
        return True
    return None


def _resolution_confidence(state: MentalHealthState, pending: object) -> float:
    turn_type = normalize_turn_type(state.get("turn_type"), "FOLLOW_UP_DISCLOSURE")
    same_session = getattr(pending, "sessionId", None) == state.get("session_id")
    confidence = 0.85 if same_session else 0.55
    if turn_type == "POST_RECOMMENDATION_REACTION":
        confidence -= 0.1
    messages = state.get("messages") or []
    latest = str(getattr(messages[-1], "content", "") if messages else "")
    if len(latest.split()) <= 6 and not has_new_emotional_content(dict(state), state.get("previous_turn_context") or {}):
        confidence -= 0.2
    return max(0.2, min(1.0, round(confidence, 2)))


async def _resolve_pending_outcome(state: MentalHealthState) -> dict:
    user_id = state.get("user_id", "")
    session_id = state.get("session_id", "")
    if not user_id or not session_id:
        return {}

    turn_type = normalize_turn_type(state.get("turn_type"), None)
    if turn_type not in RESOLUTION_TURN_TYPES:
        return {}
    if not has_new_emotional_content(dict(state), state.get("previous_turn_context") or {}):
        return {}

    try:
        from ..db.client import get_prisma_client

        prisma = await get_prisma_client()
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        sessions = await prisma.session.find_many(
            where={
                "userId": user_id,
                "startedAt": {"gte": cutoff},
            },
            order={"startedAt": "desc"},
            take=20,
        )
        session_ids = [session.id for session in sessions]
        if session_id not in session_ids:
            session_ids.insert(0, session_id)
        pending = await prisma.techniqueoutcome.find_first(
            where={
                "sessionId": {"in": session_ids},
                "intensityAfter": None,
            },
            order={"createdAt": "desc"},
        )
        if not pending:
            return {}

        current_emotion = state.get("fused_emotion", state.get("emotion", "neutral"))
        current_intensity = float(state.get("fused_intensity", state.get("intensity", 0.5)) or 0.5)
        effectiveness = _effectiveness(float(getattr(pending, "intensityBefore", 0.0) or 0.0), current_intensity)
        confidence = _resolution_confidence(state, pending)
        follow_through = _follow_through_from_behaviors(state.get("detected_behaviors") or [])

        await prisma.techniqueoutcome.update(
            where={"id": pending.id},
            data={
                "emotionAfter": _db_emotion(current_emotion),
                "subEmotionAfter": state.get("primary_sub_emotion"),
                "symptomsAfter": state.get("detected_symptoms") or [],
                "behaviorsAfter": state.get("detected_behaviors") or [],
                "intensityAfter": current_intensity,
                "effectiveness": effectiveness,
                "followThrough": follow_through,
                "confidence": confidence,
                "interventionType": "resolved_pending_technique",
            },
        )
        print(
            "[NODE: OUTCOME_TRACKER] Pending TechniqueOutcome resolved "
            f"id={pending.id} effectiveness={effectiveness:+.0%} confidence={confidence:.0%}"
        )
        return {
            "resolved_outcome_id": pending.id,
            "resolved_outcome_effectiveness": effectiveness,
            "resolved_outcome_confidence": confidence,
        }
    except Exception as e:
        print(f"[NODE: OUTCOME_TRACKER] Pending outcome resolution failed: {str(e)[:100]}")
        return {}


_CLOSURE_RESPONSE_TASKS = {"warm_close_and_invite", "compassionate_close"}


async def _resolve_pending_on_session_close(state: MentalHealthState) -> dict:
    """Fallback resolver for the abandonment gap.

    The strict resolver (`_resolve_pending_outcome`) only fires on a distinct
    reaction turn WITH new emotional content. A user who accepts a technique and
    then leaves — or simply closes warmly ("thanks, bye") with no fresh emotional
    content — would otherwise leave the outcome permanently pending
    (intensityAfter=None), so the technique's effectiveness never counts.

    When the session reaches a natural close, resolve any still-pending outcome
    for THIS session using the last known intensity. Confidence is modest because
    the user gave no explicit post-technique reaction.
    """
    session_id = state.get("session_id", "")
    if not session_id:
        return {}

    response_task = str(state.get("response_task") or "")
    is_close = (
        response_task in _CLOSURE_RESPONSE_TASKS
        or bool(state.get("session_disclosure_complete"))
    )
    if not is_close:
        return {}

    try:
        from ..db.client import get_prisma_client

        prisma = await get_prisma_client()
        pending = await prisma.techniqueoutcome.find_first(
            where={"sessionId": session_id, "intensityAfter": None},
            order={"createdAt": "desc"},
        )
        if not pending:
            return {}

        current_emotion = state.get("fused_emotion", state.get("emotion", "neutral"))
        current_intensity = float(state.get("fused_intensity", state.get("intensity", 0.5)) or 0.5)
        effectiveness = _effectiveness(
            float(getattr(pending, "intensityBefore", 0.0) or 0.0), current_intensity
        )
        # Inferred at close — no explicit reaction turn, so keep confidence modest.
        confidence = 0.4
        follow_through = _follow_through_from_behaviors(state.get("detected_behaviors") or [])

        await prisma.techniqueoutcome.update(
            where={"id": pending.id},
            data={
                "emotionAfter": _db_emotion(current_emotion),
                "subEmotionAfter": state.get("primary_sub_emotion"),
                "symptomsAfter": state.get("detected_symptoms") or [],
                "behaviorsAfter": state.get("detected_behaviors") or [],
                "intensityAfter": current_intensity,
                "effectiveness": effectiveness,
                "followThrough": follow_through,
                "confidence": confidence,
                "interventionType": "session_close_inferred",
            },
        )
        print(
            "[NODE: OUTCOME_TRACKER] Pending TechniqueOutcome resolved at SESSION CLOSE "
            f"id={pending.id} effectiveness={effectiveness:+.0%} confidence={confidence:.0%}"
        )
        return {
            "resolved_outcome_id": pending.id,
            "resolved_outcome_effectiveness": effectiveness,
            "resolved_outcome_confidence": confidence,
        }
    except Exception as e:
        print(f"[NODE: OUTCOME_TRACKER] Session-close resolution failed: {str(e)[:100]}")
        return {}


async def _infer_previous_technique_baseline(session_id: str) -> dict | None:
    """
    Find the most recent assistant technique in this same session and use the
    immediately preceding user emotion/intensity as the before-state.

    This keeps outcome tracking session-independent and avoids relying on
    LangGraph state from a previous turn, which is not persisted in this app.
    """
    if not session_id:
        return None

    try:
        from ..db.client import get_prisma_client
        prisma = await get_prisma_client()

        messages = await prisma.message.find_many(
            where={"sessionId": session_id},
            order={"createdAt": "asc"},
            include={"technique": True},
        )

        last_tech_idx = None
        for idx, msg in enumerate(messages):
            role = str(getattr(msg, "role", "")).upper()
            if role == "ASSISTANT" and getattr(msg, "techniqueId", None):
                last_tech_idx = idx

        if last_tech_idx is None:
            return None

        tech_msg = messages[last_tech_idx]
        before_msg = None
        for msg in reversed(messages[:last_tech_idx]):
            if str(getattr(msg, "role", "")).upper() == "USER":
                before_msg = msg
                break

        if before_msg is None:
            return None

        intensity_before = getattr(before_msg, "intensity", None)

        # GAP 7 fallback: if message.intensity was never written to DB, look up
        # the existing TechniqueOutcome record for this technique which stores
        # intensityBefore at offer time — that value is reliable.
        if intensity_before is None:
            try:
                existing_outcome = await prisma.techniqueoutcome.find_first(
                    where={
                        "techniqueId": tech_msg.techniqueId,
                        "intensityAfter": None,
                    },
                    order={"createdAt": "desc"},
                )
                if existing_outcome and getattr(existing_outcome, "intensityBefore", None) is not None:
                    intensity_before = float(existing_outcome.intensityBefore)
                    print(f"[NODE: OUTCOME_TRACKER]  GAP 7 fallback: using TechniqueOutcome.intensityBefore={intensity_before:.2f}")
            except Exception:
                pass

        if intensity_before is None:
            return None

        emotion_before = str(getattr(before_msg, "emotion", "NEUTRAL") or "NEUTRAL").lower()
        technique = getattr(tech_msg, "technique", None)
        return {
            "technique_id": tech_msg.techniqueId,
            "technique_name": getattr(technique, "name", "") if technique else tech_msg.techniqueId,
            "emotion_before": emotion_before,
            "sub_emotion_before": getattr(before_msg, "primarySubEmotion", None),
            "symptoms_before": getattr(before_msg, "detectedSymptoms", []) or [],
            "behaviors_before": getattr(before_msg, "detectedBehaviors", []) or [],
            "intensity_before": float(intensity_before),
        }
    except Exception as e:
        print(f"[NODE: OUTCOME_TRACKER]  DB baseline inference failed: {str(e)[:100]}")
        return None


def _latest_feedback_technique(state: MentalHealthState) -> dict:
    """Return the technique the user is giving feedback about, if known."""
    for key in ("recommended_technique", "active_technique", "latest_recommended_technique"):
        value = state.get(key) or {}
        if isinstance(value, dict) and (value.get("id") or value.get("name")):
            return value
    return {}


def _is_explicit_positive_feedback(state: MentalHealthState) -> bool:
    flags = set(state.get("gate_context_flags") or [])
    return (
        state.get("intent") in {"positive_feedback", "technique_preference_update"}
        or state.get("gate_route") == "positive_feedback"
        or state.get("response_task") in {"positive_feedback", "record_preference"}
        or "positive_feedback" in flags
        or "preference_update" in flags
    )


async def record_explicit_technique_feedback(state: MentalHealthState) -> dict:
    """
    Persist explicit "this helped / I prefer this" feedback for personalization.

    This is separate from intensity-based TechniqueOutcome. Outcome measures
    before/after emotion; this records the user's direct preference so future
    recommendations can prefer the same technique and category for this user.
    """
    if not _is_explicit_positive_feedback(state):
        return {}

    user_id = state.get("user_id", "")
    if not user_id:
        return {}

    technique = _latest_feedback_technique(state)
    technique_id = technique.get("id") if isinstance(technique, dict) else None
    technique_name = technique.get("name") if isinstance(technique, dict) else None
    category_name = technique.get("category") if isinstance(technique, dict) else None

    if not technique_id and not technique_name:
        print("[NODE: OUTCOME_TRACKER]  Positive feedback had no known technique  skipping preference write")
        return {}

    messages = state.get("messages") or []
    # Use the last HUMAN message — on bypass routes messages[-1] is the assistant
    # reply (which would otherwise be stored as the user's "feedback" text).
    user_message = ""
    for _m in reversed(messages):
        _t = (getattr(_m, "type", "") or getattr(_m, "role", "") or "").lower()
        if _t in ("human", "user") or _m.__class__.__name__ == "HumanMessage":
            user_message = getattr(_m, "content", "") or ""
            break
    feedback = (user_message or "User said this technique helped.").strip()[:500]
    rating = 5

    try:
        from ..db.client import get_prisma_client
        prisma = await get_prisma_client()

        technique_record = None
        if technique_id:
            technique_record = await prisma.technique.find_unique(
                where={"id": technique_id},
                include={"category": True},
            )
        elif technique_name:
            hits = await prisma.technique.find_many(
                where={
                    "isActive": True,
                    "name": {"equals": technique_name, "mode": "insensitive"},
                },
                include={"category": True},
                take=1,
            )
            technique_record = hits[0] if hits else None

        if technique_record:
            technique_id = getattr(technique_record, "id", technique_id)
            technique_name = getattr(technique_record, "name", technique_name)
            category = getattr(technique_record, "category", None)
            category_name = getattr(category, "name", category_name) if category else category_name

        if not technique_id:
            print("[NODE: OUTCOME_TRACKER]  Positive feedback technique could not be verified  skipping")
            return {}

        session_id = state.get("session_id")
        existing = await prisma.usertechniquerating.find_first(
            where={
                "userId": user_id,
                "techniqueId": technique_id,
                "sessionId": session_id,
            }
        )

        if existing:
            await prisma.usertechniquerating.update(
                where={"id": existing.id},
                data={
                    "rating": rating,
                    "feedback": feedback,
                    "completed": True,
                }
            )
        else:
            await prisma.usertechniquerating.create(
                data={
                    "userId": user_id,
                    "techniqueId": technique_id,
                    "rating": rating,
                    "feedback": feedback,
                    "completed": True,
                    "sessionId": session_id,
                }
            )

        preferred_categories = []
        if category_name:
            pref = await prisma.userpreference.find_unique(where={"userId": user_id})
            preferred_categories = list(getattr(pref, "preferredCategories", []) or []) if pref else []
            if category_name not in preferred_categories:
                preferred_categories.append(category_name)
            if pref:
                await prisma.userpreference.update(
                    where={"userId": user_id},
                    data={"preferredCategories": preferred_categories},
                )
            else:
                await prisma.userpreference.create(
                    data={"userId": user_id, "preferredCategories": preferred_categories},
                )

        if technique_record:
            try:
                old_total = int(getattr(technique_record, "totalRatings", 0) or 0)
                old_avg = float(getattr(technique_record, "avgRating", 0.0) or 0.0)
                new_total = old_total + 1
                new_avg = round(((old_avg * old_total) + rating) / new_total, 3)
                await prisma.technique.update(
                    where={"id": technique_id},
                    data={"avgRating": new_avg, "totalRatings": {"increment": 1}},
                )
            except Exception as e:
                print(f"[NODE: OUTCOME_TRACKER]  Technique aggregate update skipped: {str(e)[:100]}")

        try:
            await prisma.userstatistics.update(
                where={"userId": user_id},
                data={
                    "totalTechniquesUsed": {"increment": 1},
                    "mostUsedTechniqueId": technique_id,
                    "avgTechniqueRating": float(rating),
                },
            )
        except Exception as e:
            print(f"[NODE: OUTCOME_TRACKER]  User statistics update skipped: {str(e)[:100]}")

        try:
            from ..services.cache_state import invalidate_user_cache

            invalidate_user_cache(user_id, session_id=state.get("session_id"))
        except Exception as cache_err:
            print(f"[NODE: OUTCOME_TRACKER]  Cache invalidation skipped: {str(cache_err)[:100]}")

        print(
            f"[NODE: OUTCOME_TRACKER]  Positive feedback saved | "
            f"technique={technique_name or technique_id} | category={category_name or 'unknown'}"
        )
        return {
            "feedback_preference_saved": True,
            "feedback_technique_id": technique_id,
            "feedback_technique_name": technique_name,
            "preferred_category_added": category_name,
            "preferred_categories": preferred_categories,
        }
    except Exception as e:
        print(f"[NODE: OUTCOME_TRACKER]  Positive feedback preference save failed: {str(e)[:120]}")
        return {"feedback_preference_saved": False}


async def track_outcome(state: MentalHealthState) -> dict:
    """
    OUTCOME TRACKER NODE - Measure technique effectiveness.

    Process:
    1. Check if a technique was delivered this session
    2. Look for previous emotional state (from trend_window)
    3. Compare before/after  effectiveness score
    4. Save TechniqueOutcome to database
    5. Update PsychProfile

    No LLM call  pure Python/SQL.
    Returns empty dict (side-effect only node).
    """

    feedback_updates = await record_explicit_technique_feedback(state)

    recommended_technique = state.get("recommended_technique") or {}
    session_id = state.get("session_id", "")
    user_id = state.get("user_id", "")
    current_emotion = state.get("fused_emotion", state.get("emotion", "neutral"))
    current_intensity = state.get("fused_intensity", state.get("intensity", 0.5))
    strategy = state.get("conversation_strategy", "validate_only")

    print(f"\n[NODE: OUTCOME_TRACKER]  Tracking outcomes for session: "
          f"{session_id[:20] if session_id else 'UNKNOWN'}...")

    technique_id = (
        recommended_technique.get("id")
        or recommended_technique.get("technique_id")
        or recommended_technique.get("techniqueId")
        or ""
    )
    technique_name = recommended_technique.get("name", "")

    if state.get("technique_offered_this_turn") and technique_id:
        pending_updates = await _create_pending_outcome(state, recommended_technique)
        return {**feedback_updates, **pending_updates}

    resolved_updates = await _resolve_pending_outcome(state)
    if resolved_updates:
        return {**feedback_updates, **resolved_updates}

    # Abandonment fallback: if the session is closing and a pending outcome was
    # never resolved by a reaction turn, resolve it now from the last known state.
    close_updates = await _resolve_pending_on_session_close(state)
    if close_updates:
        return {**feedback_updates, **close_updates}

    technique_delivery_emotion = state.get("technique_delivery_emotion")
    technique_delivery_intensity = state.get("technique_delivery_intensity")
    session_start_emotion = state.get("session_start_emotion")
    session_start_intensity = state.get("session_start_intensity")

    if technique_id and strategy in ("suggest_technique", "reframe") and technique_delivery_emotion is not None and technique_delivery_intensity is not None:
        # Best case: we have the exact delivery-moment snapshot
        emotion_before = technique_delivery_emotion
        intensity_before = float(technique_delivery_intensity)
        sub_emotion_before = state.get("technique_delivery_sub_emotion")
        symptoms_before = state.get("technique_delivery_symptoms") or []
        behaviors_before = state.get("technique_delivery_behaviors") or []
        print("[NODE: OUTCOME_TRACKER] Using in-state technique-delivery baseline")
    elif technique_id and strategy in ("suggest_technique", "reframe") and session_start_emotion is not None and session_start_intensity is not None:
        # Second best: use session-start baseline
        emotion_before = session_start_emotion
        intensity_before = float(session_start_intensity)
        sub_emotion_before = state.get("session_start_sub_emotion")
        symptoms_before = state.get("session_start_symptoms") or []
        behaviors_before = state.get("session_start_behaviors") or []
        print("[NODE: OUTCOME_TRACKER] Using in-state session-start baseline")
    else:
        # Stateless graph fallback: infer the previous delivered technique and
        # its before-state from persisted messages in this same session.
        inferred = await _infer_previous_technique_baseline(session_id)
        if not inferred:
            print("[NODE: OUTCOME_TRACKER]  No previous technique baseline found  skipping")
            return feedback_updates
        technique_id = inferred["technique_id"]
        technique_name = inferred["technique_name"]
        emotion_before = inferred["emotion_before"]
        sub_emotion_before = inferred.get("sub_emotion_before")
        symptoms_before = inferred.get("symptoms_before", [])
        behaviors_before = inferred.get("behaviors_before", [])
        intensity_before = inferred["intensity_before"]
        print("[NODE: OUTCOME_TRACKER] Using DB-inferred previous technique baseline")
    if "sub_emotion_before" not in locals():
        sub_emotion_before = state.get("primary_sub_emotion")
    if "symptoms_before" not in locals():
        symptoms_before = state.get("detected_symptoms") or []
    if "behaviors_before" not in locals():
        behaviors_before = state.get("detected_behaviors") or []

    emotion_after = current_emotion
    intensity_after = current_intensity

    # ============================================
    # STEP 1b: BASELINE VALIDITY CHECK
    # ============================================
    # If the technique was delivered when intensity was already corrupted
    # (collapsed by the follow-up overwrite bug), the before/after comparison
    # is meaningless. The effectiveness number looks positive but the baseline
    # was artificially low — recording it would poison future Layer 3 scoring.
    #
    # Rule: if intensity_before is more than 35% below peak_distress_intensity
    # for this session, the baseline is unreliable — skip the outcome write.
    peak_distress = state.get("peak_distress_intensity")
    if peak_distress and isinstance(peak_distress, (int, float)):
        peak = float(peak_distress)
        gap = peak - intensity_before
        if gap > (peak * 0.35):
            print(
                f"[NODE: OUTCOME_TRACKER]  ⚠ BASELINE INVALID — "
                f"intensity_before={intensity_before:.0%} is {gap:.0%} below "
                f"session peak={peak:.0%} (>{peak * 0.35:.0%} threshold). "
                f"Outcome for '{technique_name}' flagged as unreliable and skipped. "
                f"This was likely captured during an intensity-collapse turn."
            )
            return feedback_updates

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
    print(f"[NODE: OUTCOME_TRACKER]  Technique: {technique_name}")
    print(f"[NODE: OUTCOME_TRACKER]   Before: {emotion_before} ({intensity_before:.0%})")
    print(f"[NODE: OUTCOME_TRACKER]   After:  {emotion_after} ({intensity_after:.0%})")
    print(f"[NODE: OUTCOME_TRACKER]   Effectiveness: {effectiveness:+.0%} ({eff_label})")

    # ============================================
    # STEP 3: SAVE TO DATABASE
    # ============================================

    try:
        from ..db.client import get_prisma_client
        prisma = await get_prisma_client()

        existing = await prisma.techniqueoutcome.find_first(
            where={
                "sessionId": session_id,
                "techniqueId": technique_id,
            }
        )
        if existing:
            print("[NODE: OUTCOME_TRACKER]  Outcome already exists for this session technique  skipping duplicate")
            return feedback_updates

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
                "subEmotionBefore": sub_emotion_before,
                "subEmotionAfter": state.get("primary_sub_emotion"),
                "symptomsBefore": symptoms_before,
                "symptomsAfter": state.get("detected_symptoms") or [],
                "behaviorsBefore": behaviors_before,
                "behaviorsAfter": state.get("detected_behaviors") or [],
                "intensityBefore": intensity_before,
                "intensityAfter": intensity_after,
                "effectiveness": effectiveness,
            }
        )
        print(f"[NODE: OUTCOME_TRACKER]  TechniqueOutcome saved")

    except Exception as e:
        print(f"[NODE: OUTCOME_TRACKER]  Failed to save outcome: {str(e)[:100]}")

    # ============================================
    # STEP 4: UPDATE PSYCH PROFILE PERSONALIZATION
    # ============================================

    try:
        await _update_behavior_profile(user_id, strategy, effectiveness)
    except Exception as e:
        print(f"[NODE: OUTCOME_TRACKER]  Failed to update behavior profile: {str(e)[:100]}")

    try:
        from ..services.cache_state import invalidate_user_cache

        invalidate_user_cache(user_id, session_id=session_id)
    except Exception as cache_err:
        print(f"[NODE: OUTCOME_TRACKER]  Cache invalidation skipped: {str(cache_err)[:100]}")

    return feedback_updates


async def _update_behavior_profile(
    user_id: str, strategy: str, effectiveness: float
) -> None:
    """
    Update user's PsychProfile based on how they respond to techniques.

    Older code wrote to a BehaviorProfile table, but the current schema stores
    behavior personalization in PsychProfile. Keep the function name local to
    avoid touching caller code, but write to the real table.
    """
    if not user_id:
        return

    try:
        from ..db.client import get_prisma_client
        prisma = await get_prisma_client()

        profile = await prisma.psychprofile.find_unique(where={"userId": user_id})

        alpha = 0.3
        old_rate = float(getattr(profile, "techniqueAccRate", 0.5) or 0.5) if profile else 0.5
        new_signal = max(0.0, min(1.0, max(0.0, effectiveness)))
        new_rate = round(alpha * new_signal + (1 - alpha) * old_rate, 3)
        new_rate = max(0.0, min(1.0, new_rate))

        if strategy == "suggest_technique" and new_rate >= 0.6:
            coping_style = "proactive"
        elif new_rate <= 0.35:
            coping_style = "avoidant"
        else:
            coping_style = "mixed"

        await prisma.psychprofile.upsert(
            where={"userId": user_id},
            data={
                "create": {
                    "userId": user_id,
                    "techniqueAccRate": new_rate,
                    "copingStyle": coping_style,
                },
                "update": {
                    "techniqueAccRate": new_rate,
                    "copingStyle": coping_style,
                },
            },
        )
        print(f"[NODE: OUTCOME_TRACKER]  Updated PsychProfile technique acceptance={new_rate:.0%}")

    except Exception as e:
        print(f"[NODE: OUTCOME_TRACKER]  PsychProfile personalization error: {str(e)[:100]}")
