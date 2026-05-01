"""
Psychological Profile Updater Node (Node 5b) - SentiMind v3.0

ARCHITECTURE NODE 5b:
Purpose: Update the user's persistent PsychProfile after every conversation turn.
         Builds a cumulative psychological model that personalizes all future interactions.
         Runs AFTER response_generator_node, BEFORE session_saver_node.
         No LLM call — pure stat accumulation and DB writes.

PROFILE FIELDS UPDATED:
  - coping_style:         avoidant | proactive | mixed (from technique acceptance rate)
  - resilience_score:     0.0-1.0 (increases on positive emotion trajectory)
  - anxiety_baseline:     rolling 30-session average of anxiety intensity
  - dominant_emotion:     most common emotion across all sessions
  - top_distortions:      list of most-detected distortion types
  - distortion_count:     total detected distortions (lifetime)
  - social_dependency:    estimate from social keyword frequency
  - reflection_depth:     measure of how often user uses reflective language
"""

import asyncio
from datetime import datetime, timezone
from ..agent.state import MentalHealthState
from ..db.client import get_prisma_client


# Keywords for social dependency and reflection depth scoring
_SOCIAL_KEYWORDS = {
    "friend", "family", "partner", "wife", "husband", "mother", "father",
    "sister", "brother", "colleague", "boss", "girlfriend", "boyfriend",
    "people", "they", "them", "he", "she", "everyone", "nobody",
}

_REFLECTION_KEYWORDS = {
    "why", "how", "i think", "i realize", "i wonder", "i notice",
    "maybe", "perhaps", "i understand", "makes sense", "i see",
    "i feel like", "i believe", "could be", "i'm not sure",
}


async def update_psych_profile(state: MentalHealthState) -> dict:
    """
    PSYCHOLOGICAL PROFILE UPDATER — Persistent behavioral model update.

    Process:
    1. Read current profile from state (loaded by Intake)
    2. Compute updates from this turn's data
    3. Upsert to PsychProfile DB table
    4. Return updated profile in state

    No LLM involved. ~100ms (DB write).
    """
    user_id = state.get("user_id", "")
    if not user_id:
        return {}

    emotion = state.get("fused_emotion", state.get("emotion", "neutral"))
    intensity = state.get("fused_intensity", state.get("intensity", 0.5))
    distortion_type = state.get("distortion_type")
    all_distortions = state.get("all_distortions", [])
    emotion_delta = state.get("emotion_delta", "stable")
    technique = state.get("recommended_technique", {})
    messages = state.get("messages", [])

    current_profile = state.get("psych_profile", {})
    print(f"\n[NODE: PROFILE] 🧬 Updating psychological profile for user: {user_id}")

    # ============================================
    # FIX 9: PROFILE UPDATE THRESHOLDS
    # Prevent premature profile hardening from low-signal messages.
    # Require at least 3 sessions of history and a meaningful emotional signal.
    # ============================================
    _PROFILE_MIN_SESSIONS = 3      # don't establish baseline from fewer than 3 sessions
    _PROFILE_MIN_INTENSITY = 0.30  # don't update on neutral/chitchat turns

    session_count = state.get("session_count", 0)
    if session_count < _PROFILE_MIN_SESSIONS:
        print(f"[NODE: PROFILE] ⏭️  Skipping update — insufficient session history ({session_count} < {_PROFILE_MIN_SESSIONS})")
        return {}

    if intensity < _PROFILE_MIN_INTENSITY and not all_distortions:
        print(f"[NODE: PROFILE] ⏭️  Skipping update — low-signal message (intensity={intensity:.0%} < {_PROFILE_MIN_INTENSITY:.0%}, no distortions)")
        return {}

    try:
        db = await get_prisma_client()

        # ============================================
        # COMPUTE PROFILE UPDATES
        # ============================================

        # 1. Resilience Score: goes up when emotion_delta is improving
        old_resilience = current_profile.get("resilience_score", 0.5)
        if emotion_delta == "improving":
            new_resilience = min(1.0, old_resilience + 0.02)
        elif emotion_delta == "worsening":
            new_resilience = max(0.0, old_resilience - 0.01)
        else:
            new_resilience = old_resilience  # stable → no change

        # 2. Anxiety Baseline: rolling average
        old_baseline = current_profile.get("anxiety_baseline", 0.5)
        # Exponential moving average with alpha=0.1
        if emotion in ("anxiety", "fear", "panic"):
            new_baseline = round(0.1 * intensity + 0.9 * old_baseline, 4)
        else:
            new_baseline = old_baseline

        # 3. Distortion tracking
        old_top = current_profile.get("top_distortions", [])
        old_count = current_profile.get("distortion_count", 0)
        new_count = old_count + len(all_distortions)
        # Merge and deduplicate, keeping order by insertion
        combined = old_top + [d for d in all_distortions if d not in old_top]
        new_top = combined[:5]  # cap at 5

        # 4. Social dependency: count social keywords in this message
        user_message = messages[-1].content.lower() if messages else ""
        social_hits = sum(1 for kw in _SOCIAL_KEYWORDS if kw in user_message)
        old_social = current_profile.get("social_dependency", 0.5)
        # EMA update
        turn_social = min(1.0, social_hits / 5.0)
        new_social = round(0.1 * turn_social + 0.9 * old_social, 4)

        # 5. Reflection depth: count reflection language
        reflection_hits = sum(1 for kw in _REFLECTION_KEYWORDS if kw in user_message)
        old_reflection = current_profile.get("reflection_depth", 0.5)
        turn_reflection = min(1.0, reflection_hits / 3.0)
        new_reflection = round(0.1 * turn_reflection + 0.9 * old_reflection, 4)

        # 6. Coping style: based on whether user accepted a technique
        technique_offered = bool(technique)
        old_acc_rate = current_profile.get("technique_acc_rate", 0.5)
        if technique_offered:
            # We'll track this more precisely using TechniqueOutcome, but here
            # we approximate: if technique was offered AND emotion improved → acceptance
            if emotion_delta == "improving":
                new_acc_rate = round(0.1 * 1.0 + 0.9 * old_acc_rate, 4)
            else:
                new_acc_rate = round(0.1 * 0.3 + 0.9 * old_acc_rate, 4)
        else:
            new_acc_rate = old_acc_rate

        # Derive coping style from acceptance rate and reflection depth
        if new_acc_rate >= 0.6 and new_reflection >= 0.4:
            coping_style = "proactive"
        elif new_acc_rate <= 0.35:
            coping_style = "avoidant"
        else:
            coping_style = "mixed"

        # ============================================
        # UPSERT TO DATABASE
        # ============================================
        update_data = {
            "copingStyle":        coping_style,
            "techniqueAccRate":   new_acc_rate,
            "reflectionDepth":    new_reflection,
            "anxietyBaseline":    new_baseline,
            "resilienceScore":    new_resilience,
            "dominantEmotion":    emotion,
            "socialDependency":   new_social,
            "topDistortions":     new_top,
            "distortionCount":    new_count,
        }

        try:
            # Try to update existing profile
            await db.psychprofile.upsert(
                where={"userId": user_id},
                data={
                    "update": update_data,
                    "create": {"userId": user_id, **update_data},
                }
            )
            print(f"[NODE: PROFILE] ✅ Profile updated | Coping: {coping_style} | Resilience: {new_resilience:.2f} | Anxiety baseline: {new_baseline:.2f}")
        except Exception as db_err:
            # Table may not exist yet — fail silently
            print(f"[NODE: PROFILE] ⚠️  DB update skipped (PsychProfile table may not exist): {str(db_err)[:60]}")

        # Return updated profile into state for next intake
        updated_profile = {**current_profile, **{k: v for k, v in {
            "coping_style":      coping_style,
            "technique_acc_rate": new_acc_rate,
            "reflection_depth":  new_reflection,
            "anxiety_baseline":  new_baseline,
            "resilience_score":  new_resilience,
            "dominant_emotion":  emotion,
            "social_dependency": new_social,
            "top_distortions":   new_top,
            "distortion_count":  new_count,
        }.items()}}

        return {"psych_profile": updated_profile}

    except Exception as e:
        print(f"[NODE: PROFILE] ❌ Error updating profile: {str(e)[:80]}")
        return {}
