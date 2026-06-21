"""
Trend Analyzer Node - Emotional trajectory tracking over time

ARCHITECTURE NODE 2.8:
Purpose: Detect whether the user's emotional state is IMPROVING, WORSENING, or STABLE
         by analyzing recent user messages in the current session.
Runs AFTER emotion_fusion, BEFORE conversation_planner
No LLM call - pure Python linear regression on intensity

TREND CLASSIFICATION:
  slope > +0.05   "worsening"  (intensity rising = more distressed)
  slope < -0.05   "improving"  (intensity falling = calming down)
  else            "stable"

Output:
  - emotional_trend: str ("improving" | "worsening" | "stable")
  - trend_window: list[dict]  current-session {emotion, intensity} snapshots
"""

from ..agent.state import MentalHealthState
import time


_trend_cache: dict[str, dict] = {}
_trend_cache_ttl = 180  # seconds


def _current_trend_point(state: MentalHealthState) -> dict:
    return {
        "emotion": state.get("fused_emotion", state.get("emotion", "neutral")),
        "intensity": state.get("fused_intensity", state.get("intensity", 0.5)),
    }


def get_cached_trend_snapshot(state: MentalHealthState) -> dict:
    """
    Return an immediate trend snapshot without DB work.

    The response path uses this so the planner has a reasonable trend signal
    while the fresh DB trend is recomputed in the background.
    """
    session_id = state.get("session_id", "")
    current_point = _current_trend_point(state)

    # v14.0: positive_feedback is LLM intent — always "improving" regardless of slope
    if state.get("gate_route") == "positive_feedback":
        return {"emotional_trend": "improving", "trend_window": [current_point], "trend_source": "positive_feedback_override"}

    if not session_id:
        return {"emotional_trend": "stable", "trend_window": [current_point]}

    cached = _trend_cache.get(session_id)
    if cached and time.time() - cached.get("timestamp", 0) < _trend_cache_ttl:
        data = cached.get("data", {})
        window = list(data.get("trend_window", []))
        window.append(current_point)
        return {
            "emotional_trend": data.get("emotional_trend", "stable"),
            "trend_window": window[-6:],
            "trend_source": "cache",
        }

    return {
        "emotional_trend": state.get("emotional_trend", "stable"),
        "trend_window": [current_point],
        "trend_source": "default",
    }


async def refresh_emotional_trend_cache(state: MentalHealthState) -> None:
    """Refresh trend cache after the response path has moved on."""
    session_id = state.get("session_id", "")
    if not session_id:
        return

    try:
        result = await analyze_emotional_trends(state)
        _trend_cache[session_id] = {
            "timestamp": time.time(),
            "data": {
                "emotional_trend": result.get("emotional_trend", "stable"),
                "trend_window": result.get("trend_window", []),
            },
        }
        print(f"[NODE: TREND_ANALYZER]  Background cache refreshed: {result.get('emotional_trend', 'stable')}")
    except Exception as e:
        print(f"[NODE: TREND_ANALYZER]  Background cache refresh failed: {str(e)[:80]}")


async def analyze_emotional_trends(state: MentalHealthState) -> dict:
    """
    TREND ANALYZER NODE - Track emotional trajectory.

    Process:
    1. Query last 5 user messages with intensity in this session from DB
    2. Compute linear slope of intensity values
    3. Classify trend: improving / worsening / stable
    4. Return trend + window for downstream decision-making

    No LLM call  pure Python/SQL.
    """

    user_id = state.get("user_id", "")
    session_id = state.get("session_id", "")
    current_emotion = state.get("fused_emotion", state.get("emotion", "neutral"))
    current_intensity = state.get("fused_intensity", state.get("intensity", 0.5))

    print(f"\n[NODE: TREND_ANALYZER]  Analyzing session trend: {session_id[:20] if session_id else 'UNKNOWN'}...")

    # v14.0: positive_feedback is LLM-classified intent — user explicitly said the session
    # helped. Override regression: intensity was capped to ≤0.25 by emotion_fusion, so the
    # slope calculation would produce a misleading "worsening" signal on the next turn.
    if state.get("gate_route") == "positive_feedback":
        print("[NODE: TREND_ANALYZER]  positive_feedback route → overriding trend to 'improving'")
        return {
            "emotional_trend": "improving",
            "trend_window": list(state.get("trend_window") or []),
        }

    if not session_id:
        print("[NODE: TREND_ANALYZER]  No session_id  returning stable")
        return {
            "emotional_trend": "stable",
            "trend_window": [],
        }

    # ============================================
    # STEP 1: QUERY RECENT USER MESSAGES IN THIS SESSION
    # ============================================

    trend_window = []
    try:
        from ..db.client import get_prisma_client
        prisma = await get_prisma_client()

        recent_messages = await prisma.message.find_many(
            where={
                "sessionId": session_id,
                "role": "USER",
                "intensity": {"not": None},
            },
            order={"createdAt": "desc"},
            take=5,
        )

        # Convert to chronological order (oldest first)
        recent_messages.reverse()

        for msg in recent_messages:
            trend_window.append({
                "emotion": str(msg.emotion).lower() if getattr(msg, "emotion", None) else "neutral",
                "intensity": float(msg.intensity) if getattr(msg, "intensity", None) is not None else 0.5,
            })

        print(f"[NODE: TREND_ANALYZER]  Retrieved {len(trend_window)} prior session emotion points")

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
