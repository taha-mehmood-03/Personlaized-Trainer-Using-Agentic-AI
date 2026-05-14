"""
Trend Analyzer Node - Emotional trajectory tracking over time

ARCHITECTURE NODE 2.8:
Purpose: Detect whether the user's emotional state is IMPROVING, WORSENING, or STABLE
         by analyzing recent MoodLog entries from the database.
Runs AFTER emotion_fusion, BEFORE conversation_planner
No LLM call - pure Python linear regression on intensity

TREND CLASSIFICATION:
  slope > +0.05   "worsening"  (intensity rising = more distressed)
  slope < -0.05   "improving"  (intensity falling = calming down)
  else            "stable"

Output:
  - emotional_trend: str ("improving" | "worsening" | "stable")
  - trend_window: list[dict]  last N {emotion, intensity, timestamp} snapshots
"""

from ..agent.state import MentalHealthState


async def analyze_emotional_trends(state: MentalHealthState) -> dict:
    """
    TREND ANALYZER NODE - Track emotional trajectory.

    Process:
    1. Query last 5 MoodLog entries for this user from DB
    2. Compute linear slope of intensity values
    3. Classify trend: improving / worsening / stable
    4. Return trend + window for downstream decision-making

    No LLM call  pure Python/SQL.
    """

    user_id = state.get("user_id", "")
    current_emotion = state.get("fused_emotion", state.get("emotion", "neutral"))
    current_intensity = state.get("fused_intensity", state.get("intensity", 0.5))

    print(f"\n[NODE: TREND_ANALYZER]  Analyzing trend for user: {user_id[:20] if user_id else 'UNKNOWN'}...")

    if not user_id:
        print("[NODE: TREND_ANALYZER]  No user_id  returning stable")
        return {
            "emotional_trend": "stable",
            "trend_window": [],
        }

    # FIX 10: Guard against anonymous users and insufficient session history.
    # Mood logs for anonymous users may belong to a shared/test profile,
    # making trend analysis unreliable. Require at least 3 real sessions.
    session_count = state.get("session_count", 0)
    if user_id == "anonymous" or session_count < 3:
        trend_reason = "anonymous user" if user_id == "anonymous" else f"only {session_count} session(s) (need 3)"
        print(f"[NODE: TREND_ANALYZER]  Insufficient data for trend ({trend_reason})  returning stable")
        # Still append current data point so trend_window has at least 1 entry
        return {
            "emotional_trend": "stable",  # Safe default  don't escalate intervention on guessed trend
            "trend_window": [{
                "emotion": current_emotion,
                "intensity": current_intensity,
            }],
        }

    # ============================================
    # STEP 1: QUERY RECENT MOOD LOGS
    # ============================================

    trend_window = []
    try:
        from ..db.client import get_prisma_client
        prisma = await get_prisma_client()

        recent_logs = await prisma.moodlog.find_many(
            where={"userId": user_id},
            order={"createdAt": "desc"},
            take=5,
        )

        # Convert to chronological order (oldest first)
        recent_logs.reverse()

        for log in recent_logs:
            trend_window.append({
                "emotion": log.emotion if hasattr(log, "emotion") else "neutral",
                "intensity": float(log.intensity) if hasattr(log, "intensity") else 0.5,
            })

        print(f"[NODE: TREND_ANALYZER]  Retrieved {len(trend_window)} mood logs")

    except Exception as e:
        print(f"[NODE: TREND_ANALYZER]  DB query failed: {str(e)[:80]}")
        # Continue with just the current data point

    # Append current message's emotion as the latest data point
    trend_window.append({
        "emotion": current_emotion,
        "intensity": current_intensity,
    })

    # ============================================
    # STEP 2: COMPUTE INTENSITY SLOPE
    # ============================================

    if len(trend_window) < 2:
        print("[NODE: TREND_ANALYZER]  Not enough data for trend  returning stable")
        return {
            "emotional_trend": "stable",
            "trend_window": trend_window,
        }

    intensities = [entry["intensity"] for entry in trend_window]
    slope = _compute_slope(intensities)

    # ============================================
    # STEP 3: CLASSIFY TREND
    # ============================================

    if slope > 0.05:
        trend = "worsening"  # Intensity rising = user getting more distressed
    elif slope < -0.05:
        trend = "improving"  # Intensity falling = user calming down
    else:
        trend = "stable"

    trend_emoji = {"worsening": "", "improving": "", "stable": ""}
    print(f"[NODE: TREND_ANALYZER] {trend_emoji.get(trend, '')} Trend: {trend.upper()} "
          f"(slope={slope:+.3f}, points={len(intensities)})")

    return {
        "emotional_trend": trend,
        "trend_window": trend_window,
    }


def _compute_slope(values: list[float]) -> float:
    """
    Simple linear regression slope over ordered intensity values.
    Positive slope = intensity increasing (worsening).
    Negative slope = intensity decreasing (improving).
    """
    n = len(values)
    if n < 2:
        return 0.0

    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n

    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    if denominator == 0:
        return 0.0

    return numerator / denominator
