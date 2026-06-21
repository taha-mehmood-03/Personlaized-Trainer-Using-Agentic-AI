"""Shared utility functions used across API route files."""

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger("sentimind.server")


def latency_seconds(start_time: float) -> float:
    """Return elapsed wall-clock time in seconds."""
    return time.time() - start_time


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _clean_enum(value: Any, default: str | None = None) -> str | None:
    if value is None:
        return default
    text = str(value).split(".")[-1].strip()
    if text.lower() in {"", "0", "none", "null", "undefined", "nan", "n/a", "unknown"}:
        return default
    try:
        float(text)
        return default
    except ValueError:
        pass
    return text


def _emotion_label(emotion: Any, primary_sub_emotion: Any) -> str | None:
    core = _clean_enum(emotion)
    sub = _clean_enum(primary_sub_emotion)
    if not core and not sub:
        return None
    if sub and core and sub.lower() != core.lower():
        return f"{core} / {sub}"
    return core or sub


def _sentiment_label(emotion: Any, sentiment: Any = None) -> str | None:
    explicit = _clean_enum(sentiment)
    if explicit:
        return explicit
    return {
        "JOY": "POSITIVE",
        "SURPRISE": "POSITIVE",
        "ANGER": "NEGATIVE",
        "DISGUST": "NEGATIVE",
        "FEAR": "NEGATIVE",
        "SADNESS": "NEGATIVE",
        "ANXIETY": "NEGATIVE",
        "NEUTRAL": "NEUTRAL",
    }.get((_clean_enum(emotion) or "").upper())


def _emotion_payload_from_result(result: dict) -> dict:
    mood_analysis = result.get("mood_analysis") if isinstance(result.get("mood_analysis"), dict) else {}
    emotion = _clean_enum(
        result.get("fused_emotion") or result.get("emotion") or result.get("mood") or mood_analysis.get("emotion"),
        "neutral",
    )
    primary = _clean_enum(
        result.get("primary_sub_emotion")
        or result.get("primarySubEmotion")
        or mood_analysis.get("primary_sub_emotion")
        or mood_analysis.get("primarySubEmotion")
        or mood_analysis.get("sub_emotion")
    )
    raw_sentiment = _clean_enum(result.get("sentiment") or mood_analysis.get("sentiment"), "neutral")
    sentiment = _sentiment_label(emotion, raw_sentiment)
    if (_clean_enum(emotion) or "").upper() in {"ANGER", "DISGUST", "FEAR", "SADNESS", "ANXIETY"}:
        sentiment = "NEGATIVE"
    return {
        "emotion": emotion,
        "sentiment": sentiment,
        "intensity": result.get("fused_intensity") if result.get("fused_intensity") is not None else result.get("intensity"),
        "confidence": result.get("confidence"),
        "raw_emotion_label": _clean_enum(result.get("raw_emotion_label") or mood_analysis.get("raw_emotion_label")),
        "primary_sub_emotion": primary,
        "secondary_sub_emotions": _as_list(result.get("secondary_sub_emotions") or mood_analysis.get("secondary_sub_emotions")),
        "detected_symptoms": _as_list(result.get("detected_symptoms") or mood_analysis.get("detected_symptoms")),
        "detected_behaviors": _as_list(result.get("detected_behaviors") or mood_analysis.get("detected_behaviors")),
        "detected_contexts": _as_list(result.get("detected_contexts") or mood_analysis.get("detected_contexts")),
        "emotion_scores": result.get("emotion_scores") or mood_analysis.get("emotion_scores") or {},
        "emotion_reasoning": result.get("emotion_reasoning"),
        "emotion_label": _emotion_label(emotion, primary),
    }


def _emotion_payload_from_message(message: Any) -> dict:
    emotion = _clean_enum(getattr(message, "emotion", None))
    primary = _clean_enum(getattr(message, "primarySubEmotion", None))
    return {
        "emotion": emotion,
        "sentiment": _sentiment_label(emotion, getattr(message, "sentiment", None)),
        "primary_sub_emotion": primary,
        "secondary_sub_emotions": _as_list(getattr(message, "secondarySubEmotions", [])),
        "detected_symptoms": _as_list(getattr(message, "detectedSymptoms", [])),
        "detected_behaviors": _as_list(getattr(message, "detectedBehaviors", [])),
        "detected_contexts": _as_list(getattr(message, "detectedContexts", [])),
        "emotion_scores": getattr(message, "emotionScores", None) or {},
        "emotion_label": _emotion_label(emotion, primary),
    }


def _normalize_phone(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.startswith("whatsapp:"):
        text = text.replace("whatsapp:", "", 1).strip()
    compact = "".join(ch for ch in text if ch.isdigit() or ch == "+")
    if compact.startswith("00"):
        compact = "+" + compact[2:]
    if compact and not compact.startswith("+"):
        compact = "+" + compact
    digits = compact[1:] if compact.startswith("+") else compact
    if not digits.isdigit() or len(digits) < 8:
        return None
    return compact


_PROFILE_SETTINGS_SCHEMA_READY = False

_PROFILE_CONSENT_SCOPES = {
    "shareLocationInCrisis": "CRISIS_LOCATION",
    "emergencyContactConsent": "EMERGENCY_CONTACT_ALERTS",
    "voiceAnalysisConsent": "VOICE_ANALYSIS",
}


def _sql_quote(value: Any) -> str:
    return "'" + str(value).replace("'", "''") + "'"


async def _ensure_profile_settings_schema(prisma) -> None:
    global _PROFILE_SETTINGS_SCHEMA_READY
    if _PROFILE_SETTINGS_SCHEMA_READY:
        return
    for sql in [
        'ALTER TABLE "UserPreference" ADD COLUMN IF NOT EXISTS "sessionAutoSave" BOOLEAN NOT NULL DEFAULT TRUE',
        'ALTER TABLE "UserPreference" ADD COLUMN IF NOT EXISTS "anonymousMode" BOOLEAN NOT NULL DEFAULT FALSE',
        'ALTER TABLE "UserPreference" ADD COLUMN IF NOT EXISTS "voiceAnalysisConsent" BOOLEAN NOT NULL DEFAULT FALSE',
    ]:
        try:
            await prisma.execute_raw(sql)
        except Exception as exc:
            logger.debug("Profile settings schema sync skipped: %s", exc)
            return
    _PROFILE_SETTINGS_SCHEMA_READY = True


async def _read_profile_setting_overrides(prisma, user_id: str) -> dict[str, bool]:
    defaults = {"sessionAutoSave": True, "anonymousMode": False, "voiceAnalysisConsent": False}
    try:
        await _ensure_profile_settings_schema(prisma)
        rows = await prisma.query_raw(
            f"""
            SELECT "sessionAutoSave", "anonymousMode", "voiceAnalysisConsent"
            FROM "UserPreference"
            WHERE "userId" = {_sql_quote(user_id)}
            LIMIT 1
            """
        )
        if not rows:
            return defaults
        data = dict(rows[0])
        return {
            "sessionAutoSave": bool(data.get("sessionAutoSave", defaults["sessionAutoSave"])),
            "anonymousMode": bool(data.get("anonymousMode", defaults["anonymousMode"])),
            "voiceAnalysisConsent": bool(data.get("voiceAnalysisConsent", defaults["voiceAnalysisConsent"])),
        }
    except Exception as exc:
        logger.debug("Profile setting overrides unavailable: %s", exc)
        return defaults


async def _update_profile_setting_overrides(prisma, user_id: str, settings: dict) -> list[str]:
    field_values: dict[str, bool] = {}
    for field in ["sessionAutoSave", "anonymousMode", "voiceAnalysisConsent"]:
        if field in settings:
            field_values[field] = bool(settings[field])
    if not field_values:
        return []
    try:
        await _ensure_profile_settings_schema(prisma)
        assignments = ", ".join(
            f'"{field}" = {"TRUE" if value else "FALSE"}'
            for field, value in field_values.items()
        )
        await prisma.execute_raw(
            f"""
            UPDATE "UserPreference"
            SET {assignments}, "updatedAt" = now()
            WHERE "userId" = {_sql_quote(user_id)}
            """
        )
        return list(field_values.keys())
    except Exception as exc:
        logger.debug("Profile setting override update skipped: %s", exc)
        return []


def schedule_audit_event(prisma=None, **kwargs: Any) -> None:
    """Fire-and-forget audit event — does not block the response path."""
    from src.mental_health_wellness.db.client import get_prisma_client
    from src.mental_health_wellness.security.compliance import record_audit_event

    async def _record() -> None:
        try:
            client = prisma or await get_prisma_client()
            await record_audit_event(client, **kwargs)
        except Exception as audit_err:
            logger.debug("Background audit skipped: %s", audit_err)

    try:
        asyncio.get_running_loop().create_task(_record())
    except RuntimeError:
        pass
