"""
User Tools - User history and session management
"""

from datetime import datetime, timezone, timedelta
from langchain_core.tools import tool
from ..db.prisma_json import prisma_json


def _retention_until(days: int = 365) -> datetime:
    """GAP-04: Compute data retention expiry (GDPR Art. 5(1)(e))."""
    return datetime.now(timezone.utc) + timedelta(days=days)


@tool
async def get_user_history(user_id: str) -> dict:
    """
    Get the user's conversation history and mood patterns.
    Use this for personalization and context.
    
    Args:
        user_id: The user's unique identifier
        
    Returns:
        Dictionary with session count, mood patterns, and recent topics
    """
    try:
        from ..db.client import get_prisma_client
        prisma = await get_prisma_client()
        
        user = await prisma.user.find_unique(
            where={"id": user_id},
            include={
                "statistics": True,
                "moodLogs": {"take": 10, "order_by": {"createdAt": "desc"}}
            }
        )
        
        if not user:
            return {"total_sessions": 0, "mood_patterns": {}, "is_new_user": True}
        
        stats = user.statistics
        moods = user.moodLogs or []
        
        emotion_counts = {}
        for log in moods:
            emotion = str(log.emotion) if log.emotion else "NEUTRAL"
            emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1
        
        most_common = max(emotion_counts, key=emotion_counts.get) if emotion_counts else "NEUTRAL"
        
        return {
            "total_sessions": stats.totalSessions if stats else 0,
            "current_streak": stats.currentCheckInStreak if stats else 0,
            "most_common_emotion": most_common.lower(),
            "mood_patterns": emotion_counts,
            "is_new_user": (stats.totalSessions if stats else 0) < 3
        }
    except Exception as e:
        print(f"[TOOL ERROR] get_user_history: {e}")
        return {"total_sessions": 0, "mood_patterns": {}, "is_new_user": True}


@tool
async def save_session(
    user_id: str,
    user_message: str,
    assistant_response: str,
    emotion: str = "neutral",
    sentiment: str | None = None,
    intensity: float | None = None,
    crisis_level: str = "low",
    session_id: str = "",
    technique: dict | None = None,
    primary_sub_emotion: str | None = None,
    secondary_sub_emotions: list[str] | None = None,
    detected_symptoms: list[str] | None = None,
    detected_behaviors: list[str] | None = None,
    detected_contexts: list[str] | None = None,
    emotion_scores: dict | None = None,
    technique_offered_this_turn: bool = False,
    voice_emotion: str | None = None,
    voice_arousal: float | None = None,
    voice_valence: float | None = None,
    voice_confidence: float | None = None,
    voice_distress_proxy: float | None = None,
) -> dict:
    """
    Save the conversation to the database.
    Call this at the end of each conversation turn.
    
    Args:
        user_id: The user's unique identifier
        user_message: What the user said
        assistant_response: What the assistant replied
        emotion: Detected emotion
        crisis_level: Crisis risk level
        session_id: Optional existing session ID to continue
        
    Returns:
        Confirmation with session ID
    """
    try:
        from ..db.client import get_prisma_client
        prisma = await get_prisma_client()
        
        # Map emotion to sentiment for moodSummary
        emotion_to_sentiment = {
            "joy": "POSITIVE",
            "surprise": "POSITIVE",
            "neutral": "NEUTRAL",
            "anger": "NEGATIVE",
            "disgust": "NEGATIVE",
            "fear": "NEGATIVE",
            "sadness": "NEGATIVE",
            "anxiety": "NEGATIVE"
        }
        
        # Ensure emotion is valid before mapping
        emotion_lower = emotion.lower().strip() if emotion else "neutral"
        sentiment_upper = (sentiment or "").upper().strip()
        if sentiment_upper not in {"POSITIVE", "NEGATIVE", "NEUTRAL"}:
            sentiment_upper = emotion_to_sentiment.get(emotion_lower, "NEUTRAL")
        
        print(f"[TOOL] save_session: Emotion='{emotion}'  Lowercase='{emotion_lower}'  Sentiment='{sentiment_upper}'")
        
        # Try to find existing session or create new one
        session = None
        
        # Session ID should now always be a valid database session ID
        if session_id:
            existing_session = await prisma.session.find_unique(
                where={"id": session_id}
            )
            if existing_session:
                if existing_session.userId == user_id:
                    session = existing_session
                    print(f"[TOOL] save_session: Using session {session.id}")
                else:
                    # Claim the session for the authenticated user (migrating from anonymous)
                    session = await prisma.session.update(
                        where={"id": session_id},
                        data={"userId": user_id}
                    )
                    print(f"[TOOL] save_session: Claimed session {session.id} for user {user_id}")
        
        # Fallback: Create new session if none found (shouldn't happen with new logic)
        if not session:
            session = await prisma.session.create(
                data={
                    "userId": user_id,
                    "title": f"Session - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                    "status": "ACTIVE",
                    "moodSummary": sentiment_upper
                }
            )
            print(f"[TOOL] save_session: Created fallback session {session.id}")

        
        # Map emotion string to valid Emotion enum
        valid_emotions = ["ANGER", "DISGUST", "FEAR", "JOY", "NEUTRAL", "SADNESS", "SURPRISE", "ANXIETY"]
        emotion_upper = (emotion or "neutral").upper().strip()
        db_emotion = emotion_upper if emotion_upper in valid_emotions else "NEUTRAL"
        
        # Update session's moodSummary with current sentiment (POSITIVE/NEGATIVE/NEUTRAL)
        await prisma.session.update(
            where={"id": session.id},
            data={"moodSummary": sentiment_upper}  # already POSITIVE/NEGATIVE/NEUTRAL
        )
        print(f"[TOOL] save_session: Updated session moodSummary to {sentiment_upper}")
        
        # GAP-04: Save user message with retentionUntil (GDPR Art. 5(1)(e))
        await prisma.message.create(
            data={
                "sessionId": session.id,
                "role": "USER",
                "content": user_message,
                "emotion": db_emotion,
                "intensity": intensity,
                "sentiment": sentiment_upper,
                "primarySubEmotion": primary_sub_emotion,
                "secondarySubEmotions": secondary_sub_emotions or [],
                "detectedSymptoms": detected_symptoms or [],
                "detectedBehaviors": detected_behaviors or [],
                "detectedContexts": detected_contexts or [],
                "emotionScores": prisma_json(emotion_scores or {}),
                "retentionUntil": _retention_until(365),  # GAP-04
                "voiceEmotion": voice_emotion,
                "voiceArousal": voice_arousal,
                "voiceValence": voice_valence,
                "voiceConfidence": voice_confidence,
                "voiceDistressProxy": voice_distress_proxy,
            }
        )
        
        assistant_message_data = {
            "sessionId": session.id,
            "role": "ASSISTANT",
            "content": assistant_response,
            "retentionUntil": _retention_until(365),  # GAP-04
        }

        # If a structured technique was provided, persist its id as a relation
        if technique and isinstance(technique, dict):
            tech_id = technique.get("id") or technique.get("technique_id") or technique.get("techniqueId")
            if tech_id:
                assistant_message_data["techniqueId"] = tech_id
                assistant_message_data["techniqueOfferedThisTurn"] = bool(technique_offered_this_turn)

        await prisma.message.create(data=assistant_message_data)
        
        if crisis_level in ["medium", "high"]:
            # GAP-04: Crisis logs are PHI — retain for 7 years (HIPAA)
            await prisma.crisislog.create(
                data={
                    "userId": user_id,
                    "riskLevel": crisis_level.upper(),
                    "messageContent": user_message,
                    "actionTaken": "agent_response",
                    "resourcesProvided": True,
                    "retentionUntil": _retention_until(2555),  # GAP-04: ~7 years
                }
            )
        
        # MoodLog creation handled by session_saver_node — do NOT duplicate here
        
        # Update UserStatistics (totalMessages, etc.)
        try:
            await prisma.userstatistics.update(
                where={"userId": user_id},
                data={
                    "totalMessages": {"increment": 2}  # user + assistant
                }
            )
            print(f"[TOOL] save_session: Updated UserStatistics")
        except Exception as stats_err:
            print(f"[TOOL] save_session: UserStatistics update failed (non-critical): {stats_err}")

        try:
            from ..services.cache_state import invalidate_user_cache

            invalidate_user_cache(user_id, session_id=session.id)
        except Exception as cache_err:
            print(f"[TOOL] save_session: Cache invalidation skipped: {cache_err}")
        
        return {"saved": True, "session_id": session.id}
        
    except Exception as e:
        print(f"[TOOL ERROR] save_session: {e}")
        return {"saved": False, "error": str(e)}
