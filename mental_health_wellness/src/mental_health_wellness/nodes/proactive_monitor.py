"""
Proactive Mental Health Monitor (Node 7 / Background Service) - SentiMind v3.0

ARCHITECTURE NODE 7 (Background / Scheduled):
Purpose: Analyze historical MoodLog data to detect proactive warning signs.
         Runs as a scheduled background task or can be called per-request in intake.
         NOT part of the live message pipeline  runs asynchronously.
         No LLM call  pure analytics on historical data.

DETECTION RULES:
  1. gradual_mood_decline:     Intensity rising > 0.15 over last 7 mood logs
  2. repeated_anxiety_spikes:  3+ high-intensity (>=0.65) logs in last 5 entries
  3. disengagement_risk:       No mood log or session in 3+ days
  4. persistent_negative_mood: 80%+ of last 10 logs are negative sentiment
  5. crisis_escalation_pattern: 2+ crisis-level intensities in last 7 days

INTEGRATION:
  - Call check_and_notify(user_id) from the Intake node after loading context
  - Places ProactiveNotification record in DB if triggered
  - Intake node reads pending notifications  passes hint to LLM payload
"""

from datetime import datetime, timezone, timedelta
from ..db.client import get_prisma_client


# ============================================
# ALERT DEFINITIONS
# ============================================

ALERT_MESSAGES = {
    "gradual_mood_decline": {
        "hint": "The user's mood has been gradually declining over recent sessions. Open gently by checking how they have been since last time.",
        "severity": "medium",
    },
    "repeated_anxiety_spikes": {
        "hint": "The user has had repeated high-anxiety episodes recently. Proactively validate that this pattern can be exhausting and reassure them.",
        "severity": "medium",
    },
    "disengagement_risk": {
        "hint": "The user hasn't checked in for several days. Warmly welcome them back without pressure. Ask how they have been.",
        "severity": "low",
    },
    "persistent_negative_mood": {
        "hint": "The user has shown a persistent negative mood pattern. Express that you've noticed they've been going through a hard time and you care.",
        "severity": "medium",
    },
    "crisis_escalation_pattern": {
        "hint": "The user has had multiple crisis-level episodes recently. Gently check in and mention professional support options.",
        "severity": "high",
    },
}


# ============================================
# ALERT DETECTION LOGIC
# ============================================

async def check_and_notify(user_id: str) -> str | None:
    """
    Check a user's historical data and create a ProactiveNotification if needed.
    Returns the alert hint string if an alert was triggered, else None.

    Call this from the Intake node (non-blocking, fire-and-forget style).
    """
    try:
        db = await get_prisma_client()

        # Fetch last 10 mood logs
        mood_logs = await db.moodlog.find_many(
            where={"userId": user_id},
            order={"createdAt": "desc"},
            take=10,
        )

        if not mood_logs:
            return None

        alerts = _detect_alerts(mood_logs)
        if not alerts:
            return None

        # Pick highest severity alert
        priority_order = ["high", "medium", "low"]
        chosen_alert = None
        for severity in priority_order:
            for alert_type in alerts:
                if ALERT_MESSAGES[alert_type]["severity"] == severity:
                    chosen_alert = alert_type
                    break
            if chosen_alert:
                break

        if not chosen_alert:
            return None

        hint = ALERT_MESSAGES[chosen_alert]["hint"]

        # Check if this alert was already sent in last 48 hours (avoid spam)
        recent = await db.proactivenotification.find_first(
            where={
                "userId": user_id,
                "alertType": chosen_alert,
                "createdAt": {"gte": datetime.now(timezone.utc) - timedelta(hours=48)},
            }
        )
        if recent:
            print(f"[PROACTIVE]   Alert '{chosen_alert}' already sent within 48h  skipping")
            return None

        # Save notification
        await db.proactivenotification.create(
            data={
                "userId":    user_id,
                "alertType": chosen_alert,
                "payload":   hint,
                "isRead":    False,
            }
        )

        print(f"[PROACTIVE]  Alert triggered: {chosen_alert} | Severity: {ALERT_MESSAGES[chosen_alert]['severity']}")
        return hint

    except Exception as e:
        # Fail silently  proactive monitoring is optional
        print(f"[PROACTIVE]   Monitor error (non-fatal): {str(e)[:80]}")
        return None


def _detect_alerts(mood_logs: list) -> list[str]:
    """Run all detection rules and return list of triggered alert types."""
    alerts = []
    now = datetime.now(timezone.utc)

    intensities = [log.intensity for log in mood_logs]
    sentiments = [log.sentiment for log in mood_logs]
    most_recent_at = mood_logs[0].createdAt if mood_logs else None

    # Rule 1: Gradual Decline  compare oldest vs newest in last 7 logs
    if len(intensities) >= 7:
        drift = intensities[0] - intensities[6]  # newest - oldest (desc order)
        if drift > 0.15:  # intensity worsened by > 15% over 7 logs
            alerts.append("gradual_mood_decline")

    # Rule 2: Repeated Anxiety Spikes  3+ high-intensity in last 5 entries
    recent_5 = intensities[:5]
    high_intensity_count = sum(1 for i in recent_5 if i >= 0.65)
    if high_intensity_count >= 3:
        alerts.append("repeated_anxiety_spikes")

    # Rule 3: Disengagement  no log in 3+ days
    if most_recent_at:
        # Handle timezone-naive datetimes
        if most_recent_at.tzinfo is None:
            most_recent_at = most_recent_at.replace(tzinfo=timezone.utc)
        days_since = (now - most_recent_at).days
        if days_since >= 3:
            alerts.append("disengagement_risk")

    # Rule 4: Persistent Negative Mood  80%+ negative in last 10
    if sentiments:
        negative_ratio = sum(1 for s in sentiments if str(s).upper() == "NEGATIVE") / len(sentiments)
        if negative_ratio >= 0.8:
            alerts.append("persistent_negative_mood")

    # Rule 5: Crisis Escalation  2+ intensity >= 0.8 in last 7 logs
    crisis_count = sum(1 for i in intensities[:7] if i >= 0.8)
    if crisis_count >= 2:
        alerts.append("crisis_escalation_pattern")

    return alerts


# ============================================
# STANDALONE BACKGROUND RUNNER
# ============================================

async def run_proactive_monitor_for_all_users():
    """
    Batch runner  call this from a scheduled job (e.g., nightly cron).
    Checks all active users and creates notifications as needed.
    """
    try:
        db = await get_prisma_client()
        users = await db.user.find_many(take=500)
        triggered = 0
        for user in users:
            result = await check_and_notify(user.id)
            if result:
                triggered += 1
        print(f"[PROACTIVE BATCH]  Checked {len(users)} users | {triggered} alerts triggered")
    except Exception as e:
        print(f"[PROACTIVE BATCH]  Error: {e}")
