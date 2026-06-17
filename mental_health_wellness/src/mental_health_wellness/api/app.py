"""
FastAPI Server for Mental Health Wellness 
Predefined deterministic graph pipeline 
"""

# ── Force UTF-8 stdout/stderr on Windows so emoji print statements don't crash ──
import sys
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import os
import time
import logging
import asyncio
from datetime import datetime
from typing import Any, Optional, List, Dict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("sentimind.server")
logging.getLogger("sentimind.context").setLevel(logging.INFO)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("transformers").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)


def latency_seconds(start_time: float) -> float:
    """Return elapsed wall-clock time in seconds for latency logs."""
    return time.time() - start_time


def _as_list(value: Any) -> list:
    """Return API-safe list values from Prisma JSON/list fields."""
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _clean_enum(value: Any, default: str | None = None) -> str | None:
    """Normalize Prisma enum strings like Emotion.SADNESS into SADNESS."""
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
    emotion_label = (_clean_enum(emotion) or "").upper()
    return {
        "JOY": "POSITIVE",
        "SURPRISE": "POSITIVE",
        "ANGER": "NEGATIVE",
        "DISGUST": "NEGATIVE",
        "FEAR": "NEGATIVE",
        "SADNESS": "NEGATIVE",
        "ANXIETY": "NEGATIVE",
        "NEUTRAL": "NEUTRAL",
    }.get(emotion_label)


def _normalize_phone(value: Any) -> str | None:
    """Keep crisis contacts in E.164-ish format for Twilio sends."""
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


def _emotion_payload_from_result(result: dict) -> dict:
    """Expose full emotion metadata consistently across chat endpoints."""
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
    """Expose saved DB message emotion metadata in the same shape as live chat."""
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


def schedule_audit_event(prisma=None, **kwargs: Any) -> None:
    """Record read audits without holding up latency-sensitive responses."""
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

# Import the new agent
from src.mental_health_wellness.agent import chat_with_agent, get_agent, check_agent_health
from src.mental_health_wellness.agent.graph import clear_session_context
from src.mental_health_wellness.db.client import get_prisma_client, close_prisma_client
from src.mental_health_wellness.db.performance import ensure_performance_indexes
from src.mental_health_wellness.security.compliance import (
    DEFAULT_CONSENT_VERSION,
    DEFAULT_PRIVACY_NOTICE_VERSION,
    DEFAULT_TERMS_VERSION,
    create_data_subject_request,
    enforce_user_scope,
    ensure_compliance_schema,
    fetch_compliance_records,
    get_effective_consent_states,
    parse_allowed_origins,
    pseudonymize_user_id,
    record_audit_event,
    record_consent_records,
    redact_text,
    security_headers_for_path,
    update_user_privacy_metadata,
)
from src.mental_health_wellness.services.cache_state import (
    invalidate_session_cache,
    invalidate_user_cache,
    session_cache_version,
    user_cache_version,
)

_USER_SESSIONS_CACHE: dict[tuple[str, int, bool, int], dict[str, Any]] = {}
_SESSION_MESSAGES_CACHE: dict[tuple[str, int], dict[str, Any]] = {}
_USER_PROFILE_CACHE: dict[tuple[str, int], dict[str, Any]] = {}
_TECHNIQUES_CACHE_VERSION = 0
_TECHNIQUES_CACHE: dict[tuple[str | None, str | None, int], dict[str, Any]] = {}

_PROFILE_SETTINGS_SCHEMA_READY = False
_PROFILE_CONSENT_SCOPES = {
    "shareLocationInCrisis": "CRISIS_LOCATION",
    "emergencyContactConsent": "EMERGENCY_CONTACT_ALERTS",
    "voiceAnalysisConsent": "VOICE_ANALYSIS",
}


def _sql_quote(value: Any) -> str:
    return "'" + str(value).replace("'", "''") + "'"


async def _ensure_profile_settings_schema(prisma) -> None:
    """Add profile-only settings columns used by the UI on older databases."""
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
    defaults = {
        "sessionAutoSave": True,
        "anonymousMode": False,
        "voiceAnalysisConsent": False,
    }
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


async def _update_profile_setting_overrides(
    prisma,
    user_id: str,
    settings: dict,
) -> list[str]:
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


async def _record_settings_consent_changes(
    prisma,
    *,
    user_id: str,
    settings: dict,
    request: Request,
) -> list[str]:
    requested = {
        field: scope
        for field, scope in _PROFILE_CONSENT_SCOPES.items()
        if field in settings
    }
    if not requested:
        return []

    latest_states = await get_effective_consent_states(
        prisma,
        user_id=user_id,
        scopes=requested.values(),
    )
    changed_fields: list[str] = []
    for field, scope in requested.items():
        next_granted = bool(settings[field])
        current_granted = latest_states.get(scope)
        if current_granted is None and not next_granted:
            continue
        if current_granted is not None and bool(current_granted) == next_granted:
            continue
        await record_consent_records(
            prisma,
            user_id=user_id,
            scopes=[scope],
            granted=next_granted,
            legal_basis="CONSENT",
            policy_version=DEFAULT_CONSENT_VERSION,
            notice_version=DEFAULT_PRIVACY_NOTICE_VERSION,
            terms_version=DEFAULT_TERMS_VERSION,
            locale=None,
            processing_region=None,
            request=request,
        )
        changed_fields.append(field)
    return changed_fields


def invalidate_techniques_cache() -> None:
    global _TECHNIQUES_CACHE_VERSION

    _TECHNIQUES_CACHE_VERSION += 1
    _TECHNIQUES_CACHE.clear()

# Import API crisis routes
api_crisis_router = None
try:
    from src.mental_health_wellness.api.crisis_routes import router as api_crisis_router
    logger.info("Crisis routes imported")
except Exception as e:
    logger.warning("Failed to import crisis routes: %s", e)

api_dashboard_router = None
try:
    from src.mental_health_wellness.api.dashboard_routes import router as api_dashboard_router
    logger.info("Dashboard routes imported")
except Exception as e:
    logger.warning("Failed to import dashboard routes: %s", e)


# ============================================
# PYDANTIC MODELS
# ============================================

class ChatRequest(BaseModel):
    user_id: str
    message: str
    session_id: Optional[str] = None
    audio_data: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    session_id: Optional[str] = None
    emotion: Optional[str] = None
    sentiment: Optional[str] = None
    intensity: Optional[float] = None
    confidence: Optional[float] = None
    raw_emotion_label: Optional[str] = None
    primary_sub_emotion: Optional[str] = None
    secondary_sub_emotions: List[str] = []
    detected_symptoms: List[str] = []
    detected_behaviors: List[str] = []
    detected_contexts: List[str] = []
    emotion_scores: Dict[str, Any] = {}
    emotion_reasoning: Optional[str] = None
    emotion_label: Optional[str] = None
    crisis_detected: bool = False
    tools_used: List[str] = []
    node_trace: List[str] = []
    latency_trace: List[Dict[str, Any]] = []
    latency_summary: Dict[str, Any] = {}
    technique_reasoning: Optional[str] = None
    recommended_techniques_by_category: Dict[str, dict] = {}
    alternative_techniques: List[dict] = []
    timestamp: str


class PipelineRequest(BaseModel):
    user_id: Optional[str] = None
    message: str
    session_id: Optional[str] = None


class UserCreateRequest(BaseModel):
    email: str
    name: str


class UserCreateResponse(BaseModel):
    user_id: str
    email: str
    name: str
    created: bool


class UserLoginRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _validate_auth_payload(email: str, password: str, *, signup: bool = False) -> None:
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="A valid email address is required")
    if not password:
        raise HTTPException(status_code=400, detail="Password is required")
    if signup:
        has_upper = any(char.isupper() for char in password)
        has_digit = any(char.isdigit() for char in password)
        if len(password) < 8 or not has_upper or not has_digit:
            raise HTTPException(
                status_code=400,
                detail="Password must be at least 8 characters and include an uppercase letter and a number",
            )


class AuthResponse(BaseModel):
    status: str
    user_id: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    message: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    agent_ready: bool
    database_connected: bool
    timestamp: str


class WellnessTip(BaseModel):
    id: str
    title: str
    description: str
    category: str


class TechniqueRatingRequest(BaseModel):
    user_id: str
    technique_id: str
    rating: Optional[int] = None  # Make optional
    feedback: Optional[str] = None
    completed: bool = False
    session_id: Optional[str] = None


class TechniqueRatingResponse(BaseModel):
    status: str
    message: str
    technique_id: str


async def _update_personalized_technique_preferences(
    prisma,
    user_id: str,
    technique_id: str,
    rating: Optional[int],
    completed: bool,
) -> None:
    """
    Keep UserPreference.preferredCategories aligned with explicit technique
    feedback. High ratings/completion add the category; low ratings remove it.
    The selector also reads raw UserTechniqueRating, so this is a lightweight
    category-level preference signal rather than the only personalization layer.
    """
    try:
        technique = await prisma.technique.find_unique(
            where={"id": technique_id},
            include={"category": True},
        )
        category_name = technique.category.name if technique and technique.category else None
        if not category_name:
            return

        pref = await prisma.userpreference.find_unique(where={"userId": user_id})
        existing = list(getattr(pref, "preferredCategories", []) or []) if pref else []
        updated = list(existing)

        if rating is not None and rating <= 2:
            updated = [name for name in updated if name != category_name]
        elif (rating is not None and rating >= 4) or completed:
            if category_name not in updated:
                updated.append(category_name)
        else:
            return

        if updated == existing:
            return

        if pref:
            await prisma.userpreference.update(
                where={"userId": user_id},
                data={"preferredCategories": updated},
            )
        else:
            await prisma.userpreference.create(
                data={"userId": user_id, "preferredCategories": updated},
            )

        print(f"[API] Personalized category preferences updated: {updated}")
    except Exception as e:
        print(f"[API] Preference update skipped: {str(e)[:80]}")


class SessionRenameRequest(BaseModel):
    title: str


class ConsentRequest(BaseModel):
    scopes: List[str] = ["WELLNESS_CHAT", "MOOD_ANALYTICS", "PERSONALIZATION", "CRISIS_SAFETY"]
    legal_basis: str = "CONSENT"
    policy_version: str = DEFAULT_CONSENT_VERSION
    notice_version: str = DEFAULT_PRIVACY_NOTICE_VERSION
    terms_version: str = DEFAULT_TERMS_VERSION
    locale: Optional[str] = "en-US"
    processing_region: Optional[str] = None


class ConsentWithdrawRequest(BaseModel):
    scopes: Optional[List[str]] = None
    reason: Optional[str] = None

# ============================================
# LIFESPAN MANAGEMENT
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown events"""
    logger.info("=" * 72)
    logger.info("SentiMind Mental Health API starting")
    logger.info("=" * 72)

    # ── Database ──────────────────────────────────────────────────────────
    try:
        prisma = await get_prisma_client()
        await ensure_compliance_schema(prisma)
        await ensure_performance_indexes(prisma)
        logger.info("Startup OK   | Prisma/Supabase database connected")
        logger.info("Startup OK   | Compliance audit/consent tables ready")
        logger.info("Startup OK   | Performance indexes ready")
    except Exception as e:
        logger.exception("Startup FAIL | Prisma/Supabase database connection failed: %s", e)
        import traceback
        traceback.print_exc()

    # ── LLM Provider (OpenRouter) ─────────────────────────────────────────
    try:
        logger.info("Startup      | Initializing LLM provider")
        from src.mental_health_wellness.llm.groq_llm import get_llm_manager
        llm_manager = get_llm_manager()
        llm_manager.get_llm()
        llm_status = llm_manager.get_status()
        logger.info(
            "Startup OK   | LLM ready | provider=%s model=%s openrouter=%s",
            llm_status.get("provider"),
            llm_status.get("openrouter_model"),
            llm_status.get("openrouter_key_set"),
        )
    except Exception as e:
        logger.exception("Startup FAIL | LLM provider initialization failed: %s", e)
        import traceback
        traceback.print_exc()

    # ── Agentic Pipeline ──────────────────────────────────────────────────
    try:
        get_agent()
        logger.info("Startup OK   | Deterministic agent graph initialized")
    except Exception as e:
        logger.exception("Startup FAIL | Agent graph initialization failed: %s", e)
        import traceback
        traceback.print_exc()

    # ── Gemini Voice Analysis ─────────────────────────────────────────────
    try:
        print("[SERVER] Checking Gemini voice analysis configuration...")
        import asyncio
        from src.mental_health_wellness.voice import preload_all_voice_models

        loop = asyncio.get_event_loop()
        voice_status = await loop.run_in_executor(None, preload_all_voice_models)
        print(f"[SERVER] Gemini voice analysis status: {voice_status}")
        if not voice_status.get("gemini_key_set"):
            print("[SERVER] WARNING: Gemini voice analysis has no API key configured")
    except Exception as e:
        print(f"[SERVER] WARNING: Gemini voice analysis check failed (non-fatal): {e}")

    print("="*60)
    print("[SERVER] 🎯 All systems ready — listening for requests")
    print("="*60 + "\n")

    yield

    print("\n" + "="*60)
    print("[SERVER] 🛑 Shutting down gracefully...")
    await close_prisma_client()
    print("[SERVER] ✅ Database connection closed")
    print("[SERVER] 👋 Shutdown complete")
    print("="*60)


# ============================================
@asynccontextmanager
async def organized_lifespan(app: FastAPI):
    """Structured startup/shutdown with model preloading."""
    logger.info("=" * 72)
    logger.info("SentiMind Mental Health API starting")
    logger.info("=" * 72)

    try:
        prisma = await get_prisma_client()
        await ensure_compliance_schema(prisma)
        await ensure_performance_indexes(prisma)
        logger.info("Startup OK   | Prisma/Supabase database connected")
        logger.info("Startup OK   | Compliance schema and performance indexes ready")
    except Exception as e:
        logger.exception("Startup FAIL | Prisma/Supabase database connection failed: %s", e)

    try:
        logger.info("Startup      | Initializing LLM provider")
        from src.mental_health_wellness.llm.groq_llm import get_llm_manager

        llm_manager = get_llm_manager()
        llm_manager.get_llm()
        status = llm_manager.get_status()
        logger.info(
            "Startup OK   | LLM ready | provider=%s model=%s openrouter=%s",
            status.get("provider"),
            status.get("openrouter_model"),
            status.get("openrouter_key_set"),
        )
    except Exception as e:
        logger.exception("Startup FAIL | LLM provider initialization failed: %s", e)

    try:
        get_agent()
        logger.info("Startup OK   | Deterministic agent graph initialized")
    except Exception as e:
        logger.exception("Startup FAIL | Agent graph initialization failed: %s", e)

    try:
        logger.info("Startup      | Preloading memory embedding model")
        import asyncio
        from src.mental_health_wellness.memory import check_memory_health, preload_embeddings
        from src.mental_health_wellness.memory.pgvector_store import ensure_pgvector_schema

        loop = asyncio.get_event_loop()
        await ensure_pgvector_schema()
        await loop.run_in_executor(None, preload_embeddings)
        memory_health = check_memory_health()
        if memory_health.get("status") == "healthy":
            logger.info(
                "Startup OK   | Memory recall ready | model=%s dim=%s",
                memory_health.get("embedding_model"),
                memory_health.get("embedding_dim"),
            )
        else:
            logger.warning("Startup WARN | Semantic memory unhealthy: %s", memory_health.get("error"))
    except Exception as e:
        logger.warning("Startup WARN | Semantic memory preload failed (non-fatal): %s", e)

    try:
        logger.info("Startup      | Checking Gemini voice analysis")
        import asyncio
        from src.mental_health_wellness.voice import preload_all_voice_models

        loop = asyncio.get_event_loop()
        voice_status = await loop.run_in_executor(None, preload_all_voice_models)
        logger.info("Startup OK   | Gemini voice analysis status: %s", voice_status)
        if not voice_status.get("gemini_key_set"):
            logger.warning("Startup WARN | Gemini voice analysis has no API key configured")
    except Exception as e:
        logger.warning("Startup WARN | Gemini voice analysis check failed (non-fatal): %s", e)

    logger.info("=" * 72)
    logger.info("SentiMind ready - listening for requests")
    logger.info("=" * 72)

    yield

    logger.info("=" * 72)
    logger.info("SentiMind shutting down")
    await close_prisma_client()
    logger.info("Shutdown OK  | Database connection closed")
    logger.info("Shutdown complete")
    logger.info("=" * 72)


# FASTAPI APP
# ============================================

app = FastAPI(
    title="Mental Health Wellness API",
    description="AI mental health support using LangGraph ReAct Agent",
    version="3.0.0",
    lifespan=organized_lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-SentiMind-User-Id"],
)


@app.middleware("http")
async def log_request_latency(request: Request, call_next):
    """Log total HTTP request handling latency in seconds."""
    start_time = time.time()
    path = request.url.path
    method = request.method
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "Latency FAIL | %s %s | %.3fs",
            method,
            path,
            latency_seconds(start_time),
        )
        raise

    logger.info(
        "Latency HTTP | %s %s | status=%s | %.3fs",
        method,
        path,
        response.status_code,
        latency_seconds(start_time),
    )
    for header, value in security_headers_for_path(path).items():
        response.headers.setdefault(header, value)
    return response

# Include crisis routes
if api_crisis_router is not None:
    app.include_router(api_crisis_router)
    logger.info("Crisis routes registered")
else:
    logger.warning("Crisis routes not registered")

if api_dashboard_router is not None:
    app.include_router(api_dashboard_router)
    logger.info("Dashboard routes registered")
else:
    logger.warning("Dashboard routes not registered")


# ============================================
# ENDPOINTS
# ============================================

@app.get("/api/dashboard/user/{user_id}", response_model=dict)
async def dashboard_user_direct(user_id: str, request: Request, days: int = 30):
    """
    Advanced dashboard endpoint.

    This direct route mirrors src.mental_health_wellness.api.dashboard_routes
    and keeps the dashboard available even if optional router imports fail
    during server startup.
    """
    try:
        enforce_user_scope(request, user_id)
        from src.mental_health_wellness.services.dashboard_analytics import build_user_dashboard

        prisma = await get_prisma_client()
        dashboard = await build_user_dashboard(user_id=user_id, days=days)
        schedule_audit_event(
            prisma,
            event_type="DATA_ACCESS",
            action="dashboard.read",
            subject_user_id=user_id,
            resource_type="dashboard",
            purpose="user wellness analytics",
            legal_basis="CONSENT",
            request=request,
            metadata={"days": days},
        )
        return dashboard
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.exception("Dashboard analytics failed for user=%s", pseudonymize_user_id(user_id))
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/dashboard/user/{user_id}", response_model=dict)
async def dashboard_user_direct_no_api_prefix(user_id: str, request: Request, days: int = 30):
    """
    Compatibility alias for clients configured without the /api base prefix.
    """
    return await dashboard_user_direct(user_id=user_id, request=request, days=days)

@app.get("/", response_model=dict)
async def root():
    """Health check endpoint"""
    return {
        "message": "Mental Health Wellness API - Agent Version",
        "status": "healthy",
        "version": "3.0.0"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Detailed health check"""
    db_connected = False
    agent_ready = False
    
    try:
        prisma = await get_prisma_client()
        await prisma.user.count()
        db_connected = True
    except Exception as e:
        print(f"[HEALTH] DB check failed: {e}")
    
    try:
        health = check_agent_health()
        agent_ready = health.get("agent_ready", False)
    except Exception as e:
        print(f"[HEALTH] Agent check failed: {e}")
    
    return HealthResponse(
        status="healthy" if db_connected and agent_ready else "degraded",
        version="3.0.0",
        agent_ready=agent_ready,
        database_connected=db_connected,
        timestamp=datetime.now().isoformat()
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, http_request: Request):
    """
    Main chat endpoint using the deterministic graph pipeline.
    """
    request_start = time.time()
    safe_user = pseudonymize_user_id(request.user_id)
    enforce_user_scope(http_request, request.user_id)
    logger.info(
        "Latency CHAT | start | user=%s session=%s audio_data=%s audio_chars=%d",
        safe_user,
        redact_text(request.session_id or "new", max_len=32),
        bool(request.audio_data),
        len(request.audio_data or ""),
    )
    audio_temp_path = None
    try:
        import tempfile
        import base64
        import os

        if request.audio_data:
            try:
                # Strip data URI prefix if present
                b64_str = request.audio_data
                if "," in b64_str:
                    b64_str = b64_str.split(",")[1]
                    
                audio_bytes = base64.b64decode(b64_str)
                
                # Save to temp file
                suffix = _audio_upload_suffix(request.audio_data, audio_bytes)
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
                    tf.write(audio_bytes)
                    audio_temp_path = tf.name
                    print(f"[CHAT] 🎤 Saved audio buffer to {audio_temp_path}")
            except Exception as e:
                print(f"[CHAT] ❌ Failed to decode audio_data: {e}")

        # Run Gemini audio preprocessing ONCE here (in the API layer) to
        # get both the transcription and full acoustic voice features.
        final_message = request.message
        prefetched_voice_features: Optional[dict] = None

        if audio_temp_path:
            from src.mental_health_wellness.nodes.voice_preprocessing import preprocess_voice_input
            voice_start = time.time()

            voice_state = {
                "audio_file_path": audio_temp_path,
                "message": request.message,
            }

            voice_result = await preprocess_voice_input(voice_state)
            voice_elapsed = latency_seconds(voice_start)
            logger.info(
                "Latency CHAT | voice_preprocessing | user=%s | %.3fs",
                safe_user,
                voice_elapsed,
            )

            gemini_transcription = voice_result.get("transcription", "").strip()
            if gemini_transcription:
                final_message = gemini_transcription
                print(f"[CHAT] 🎤 Gemini transcription used as message: '{gemini_transcription[:80]}'")
            elif not final_message:
                final_message = voice_result.get("final_message", request.message) or request.message

            # Forward voice features so emotion_fusion_node uses CASE 0 (authoritative override).
            # Use extraction_method check: voice_processed may be False for low-confidence neutral audio
            # even when Gemini successfully analyzed it. We forward features whenever Gemini returned
            # a real result (extraction_method='gemini_audio'), not just on voice_processed=True.
            vf_candidate = voice_result.get("voice_features")
            is_authoritative = (
                isinstance(vf_candidate, dict)
                and str(vf_candidate.get("extraction_method", "")).lower().strip() == "gemini_audio"
            )
            if is_authoritative:
                prefetched_voice_features = vf_candidate
                vf = prefetched_voice_features
                print(
                    f"[CHAT] 🎙️ Voice features extracted and forwarded to graph:\n"
                    f"  Emotion: {vf.get('emotion')} (confidence={vf.get('confidence', 0.0):.0%})\n"
                    f"  Intensity: {vf.get('intensity', 0.5):.0%} | distress_index={vf.get('distress_index', 0.0):.2f}\n"
                    f"  Sub-emotion: {vf.get('primary_sub_emotion')} | arousal={vf.get('arousal', 0.5):.0%}\n"
                    f"  Handoff: voice_features injected -> parallel_intake will skip text mood analysis"
                )
            else:
                print("[CHAT] ⚠️ Voice preprocessing ran but extraction failed — falling back to text-only path")

        result = await chat_with_agent(
            user_id=request.user_id,
            message=final_message,
            session_id=request.session_id,
            audio_file_path=audio_temp_path if not prefetched_voice_features else None,
            voice_features=prefetched_voice_features,
        )
        invalidate_user_cache(
            request.user_id,
            session_id=result.get("session_id") or request.session_id,
        )
        logger.info(
            "Latency CHAT | agent_complete | user=%s session=%s | %.3fs | trace=%s | bottleneck=%s",
            safe_user,
            redact_text(result.get("session_id") or request.session_id or "new", max_len=32),
            latency_seconds(request_start),
            " -> ".join(result.get("node_trace", [])),
            result.get("latency_summary", {}).get("bottleneck"),
        )

        emotion_payload = _emotion_payload_from_result(result)

        return ChatResponse(
            response=result.get("response", "I'm here to listen."),
            session_id=result.get("session_id"),
            **emotion_payload,
            crisis_detected=result.get("crisis_detected", False),
            tools_used=result.get("tools_used", []),
            node_trace=result.get("node_trace", []),
            latency_trace=result.get("latency_trace", []),
            latency_summary=result.get("latency_summary", {}),
            technique_reasoning=result.get("technique_reasoning"),
            recommended_techniques_by_category=result.get("recommended_techniques_by_category", {}),
            alternative_techniques=result.get("alternative_techniques", []),
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.exception(
            "Latency CHAT | failed | user=%s session=%s | %.3fs | error=%s",
            safe_user,
            redact_text(request.session_id or "new", max_len=32),
            latency_seconds(request_start),
            redact_text(e),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Chat processing failed: {str(e)}"
        )
    finally:
        if audio_temp_path:
            try:
                if os.path.exists(audio_temp_path):
                    os.remove(audio_temp_path)
            except Exception as e:
                print(f"[CHAT] ⚠️ Could not cleanup temp audio file {audio_temp_path}: {e}")


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest, http_request: Request):
    """
    True Token Streaming chat endpoint — SSE (Server-Sent Events) with LLM streaming.
    """
    from fastapi.responses import StreamingResponse
    from typing import Optional
    import json

    request_start = time.time()
    safe_user = pseudonymize_user_id(request.user_id)
    enforce_user_scope(http_request, request.user_id)
    logger.info(
        "Latency STREAM | start | user=%s session=%s audio_data=%s audio_chars=%d",
        safe_user,
        redact_text(request.session_id or "new", max_len=32),
        bool(request.audio_data),
        len(request.audio_data or ""),
    )

    async def event_generator():
        audio_temp_path = None
        first_token_logged = False
        try:
            from src.mental_health_wellness.agent.graph import chat_with_agent_streaming
            import tempfile
            import base64
            import os
            
            if request.audio_data:
                try:
                    # Strip data URI prefix if present
                    b64_str = request.audio_data
                    if "," in b64_str:
                        b64_str = b64_str.split(",")[1]
                        
                    audio_bytes = base64.b64decode(b64_str)
                    
                    # Save to temp file
                    suffix = _audio_upload_suffix(request.audio_data, audio_bytes)
                    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
                        tf.write(audio_bytes)
                        audio_temp_path = tf.name
                        print(f"[STREAM] 🎤 Saved audio buffer to {audio_temp_path}")
                except Exception as e:
                    print(f"[STREAM] ❌ Failed to decode audio_data: {e}")
            
            # Run Gemini audio preprocessing ONCE here (in the API layer) to
            # get both the transcription and full acoustic voice features.
            # Features are forwarded directly into chat_with_agent_streaming so
            # parallel_intake does NOT re-run preprocessing on the same file.
            final_message = request.message
            prefetched_voice_features: Optional[dict] = None

            if audio_temp_path:
                from src.mental_health_wellness.nodes.voice_preprocessing import preprocess_voice_input
                voice_start = time.time()

                voice_state = {
                    "audio_file_path": audio_temp_path,
                    "message": request.message,
                }

                voice_result = await preprocess_voice_input(voice_state)
                voice_elapsed = latency_seconds(voice_start)
                logger.info(
                    "Latency STREAM | voice_preprocessing | user=%s | %.3fs",
                    safe_user,
                    voice_elapsed,
                )

                gemini_transcription = voice_result.get("transcription", "").strip()
                if gemini_transcription:
                    final_message = gemini_transcription
                    print(f"[STREAM] 🎤 Gemini transcription used as message: '{gemini_transcription[:80]}'")
                elif not final_message:
                    final_message = voice_result.get("final_message", request.message) or request.message

                # Forward voice features so emotion_fusion_node uses CASE 0 (authoritative override).
                # Pass audio_file_path=None so the graph does NOT attempt double-preprocessing.
                # Use extraction_method check: voice_processed may be False for low-confidence neutral audio
                # even when Gemini successfully analyzed it. We forward features whenever Gemini returned
                # a real result (extraction_method='gemini_audio'), not just on voice_processed=True.
                vf_candidate = voice_result.get("voice_features")
                is_authoritative = (
                    isinstance(vf_candidate, dict)
                    and str(vf_candidate.get("extraction_method", "")).lower().strip() == "gemini_audio"
                )
                if is_authoritative:
                    prefetched_voice_features = vf_candidate
                    vf = prefetched_voice_features
                    print(
                        f"[STREAM] 🎙️ Voice features extracted and forwarded to graph:\n"
                        f"  Emotion: {vf.get('emotion')} (confidence={vf.get('confidence', 0.0):.0%})\n"
                        f"  Intensity: {vf.get('intensity', 0.5):.0%} | distress_index={vf.get('distress_index', 0.0):.2f}\n"
                        f"  Sub-emotion: {vf.get('primary_sub_emotion')} | arousal={vf.get('arousal', 0.5):.0%}\n"
                        f"  Handoff: voice_features injected -> parallel_intake will skip text mood analysis"
                    )
                else:
                    print("[STREAM] ⚠️ Voice preprocessing ran but extraction failed — falling back to text-only path")

            # chat_with_agent_streaming yields tokens and a final metadata event.
            # When prefetched_voice_features is set, audio_file_path is omitted so
            # the graph does not attempt to re-process the (already deleted) temp file.
            stream = chat_with_agent_streaming(
                user_id=request.user_id,
                message=final_message,
                session_id=request.session_id,
                audio_file_path=audio_temp_path if not prefetched_voice_features else None,
                voice_features=prefetched_voice_features,
            )

            async for chunk_data in stream:
                if chunk_data["type"] == "token":
                    if not first_token_logged:
                        first_token_logged = True
                        logger.info(
                            "Latency STREAM | first_token | user=%s session=%s | %.3fs",
                            safe_user,
                            redact_text(request.session_id or "new", max_len=32),
                            latency_seconds(request_start),
                        )
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk_data['content']})}\n\n"
                elif chunk_data["type"] == "done":
                    # Send metadata as final event
                    metadata = chunk_data["metadata"]
                    metadata["type"] = "done"  # Ensure type is explicitly set
                    invalidate_user_cache(
                        request.user_id,
                        session_id=metadata.get("session_id") or request.session_id,
                    )
                    yield f"data: {json.dumps(metadata)}\n\n"
                    logger.info(
                        "Latency STREAM | complete | user=%s session=%s | %.3fs | bottleneck=%s",
                        safe_user,
                        redact_text(metadata.get("session_id") or request.session_id or "new", max_len=32),
                        latency_seconds(request_start),
                        metadata.get("latency_summary", {}).get("bottleneck"),
                    )
                    print(f"[STREAM] ✅ Stream complete | Metadata sent")

        except Exception as e:
            print(f"[STREAM] ❌ Stream error: {e}")
            logger.exception(
                "Latency STREAM | failed | user=%s session=%s | %.3fs | error=%s",
                safe_user,
                redact_text(request.session_id or "new", max_len=32),
                latency_seconds(request_start),
                redact_text(e),
            )
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'content': 'Something went wrong. Please try again.'})}\n\n"
        finally:
            if audio_temp_path:
                import os
                try:
                    if os.path.exists(audio_temp_path):
                        os.remove(audio_temp_path)
                except Exception as e:
                    print(f"[STREAM] ⚠️ Could not cleanup temp audio file {audio_temp_path}: {e}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )

@app.post("/api/pipeline/complete")
async def pipeline_complete(request: PipelineRequest, http_request: Request):
    """
    Complete pipeline endpoint (frontend compatibility).
    Uses the same agent as /chat but with frontend-expected response format.
    """
    start_time = time.time()
    
    try:
        user_id = request.user_id
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")
        enforce_user_scope(http_request, user_id)
        
        result = await chat_with_agent(
            user_id=user_id,
            message=request.message,
            session_id=request.session_id
        )
        invalidate_user_cache(
            user_id,
            session_id=result.get("session_id") or request.session_id,
        )
        
        end_time = time.time()
        total_ms = int((end_time - start_time) * 1000)
        total_s = end_time - start_time
        logger.info(
            "Latency PIPELINE | complete | user=%s session=%s | %.3fs",
            user_id,
            result.get("session_id") or request.session_id or "new",
            total_s,
        )
        
        emotion_payload = _emotion_payload_from_result(result)

        return {
            "status": "success",
            "mood_analysis": {
                "sentiment": emotion_payload.get("sentiment", "neutral"),
                "emotion": emotion_payload.get("emotion", "neutral"),
                "intensity": emotion_payload.get("intensity", 0.5),
                "confidence": emotion_payload.get("confidence", 0.8),
                "raw_emotion_label": emotion_payload.get("raw_emotion_label"),
                "primary_sub_emotion": emotion_payload.get("primary_sub_emotion"),
                "secondary_sub_emotions": emotion_payload.get("secondary_sub_emotions", []),
                "detected_symptoms": emotion_payload.get("detected_symptoms", []),
                "detected_behaviors": emotion_payload.get("detected_behaviors", []),
                "detected_contexts": emotion_payload.get("detected_contexts", []),
                "emotion_scores": emotion_payload.get("emotion_scores", {}),
                "emotion_label": emotion_payload.get("emotion_label"),
            },
            "response": result.get("response", "I'm here to listen."),
            "crisis_detected": result.get("crisis_detected", False),
            "session_id": result.get("session_id"),
            "tools_used": result.get("tools_used", []),
            "node_trace": result.get("node_trace", []),
            "techniques": result.get("techniques", []),
            "performance": {
                "total_ms": total_ms,
                "total_seconds": round(total_s, 3),
                "latency_summary": result.get("latency_summary", {}),
                "latency_trace": result.get("latency_trace", []),
            }
        }
        
    except Exception as e:
        logger.exception(
            "Latency PIPELINE | failed | user=%s session=%s | %.3fs | error=%s",
            request.user_id or "missing",
            request.session_id or "new",
            latency_seconds(start_time),
            e,
        )
        import traceback
        traceback.print_exc()
        
        return {
            "status": "success",
            "mood_analysis": {
                "sentiment": "neutral",
                "emotion": "neutral",
                "intensity": 0.5,
                "confidence": 0.5
            },
            "response": "I appreciate you sharing. How are you feeling right now?",
            "crisis_detected": False,
            "tools_used": [],
            "performance": {"total_ms": 0}
        }


@app.post("/api/user/create", response_model=UserCreateResponse)
async def create_user(request: UserCreateRequest):
    """Create a new user"""
    try:
        prisma = await get_prisma_client()
        
        existing = await prisma.user.find_unique(where={"email": request.email})
        if existing:
            return UserCreateResponse(
                user_id=existing.id,
                email=existing.email,
                name=existing.name,
                created=False
            )
        
        user = await prisma.user.create(
            data={"email": request.email, "name": request.name}
        )
        
        await prisma.userpreference.create(data={"userId": user.id})
        await prisma.userstatistics.create(data={"userId": user.id})
        
        return UserCreateResponse(
            user_id=user.id,
            email=user.email,
            name=user.name,
            created=True
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/signup")
async def auth_signup(request: UserLoginRequest, http_request: Request):
    """Sign up a new user with an email and password"""
    import bcrypt
    try:
        prisma = await get_prisma_client()
        email = _normalize_email(request.email)
        _validate_auth_payload(email, request.password, signup=True)

        existing = await prisma.user.find_unique(where={"email": email})
        if existing:
            if existing.passwordHash:
                raise HTTPException(status_code=400, detail="Email already strictly configured with a password.")
            else:
                # Update anonymous user with real password
                salt = bcrypt.gensalt()
                hashed = bcrypt.hashpw(request.password.encode('utf-8'), salt)
                
                updated_user = await prisma.user.update(
                    where={"id": existing.id},
                    data={"passwordHash": hashed.decode('utf-8')}
                )
                await update_user_privacy_metadata(
                    prisma,
                    user_id=updated_user.id,
                    privacy_notice_version=DEFAULT_PRIVACY_NOTICE_VERSION,
                    terms_version=DEFAULT_TERMS_VERSION,
                )
                await record_audit_event(
                    prisma,
                    event_type="AUTH_SIGNUP",
                    action="auth.signup.attach_password",
                    subject_user_id=updated_user.id,
                    resource_type="user",
                    resource_id=updated_user.id,
                    purpose="account security",
                    legal_basis="CONTRACT",
                    request=http_request,
                )
                
                return AuthResponse(
                    status="success",
                    user_id=updated_user.id,
                    email=updated_user.email,
                    name=updated_user.name
                )
        
        # Completely new user
        name = (request.name or email.split('@')[0]).strip()[:80]
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(request.password.encode('utf-8'), salt)
        
        user = await prisma.user.create(
            data={
                "email": email,
                "name": name,
                "passwordHash": hashed.decode('utf-8'),
            }
        )
        await update_user_privacy_metadata(
            prisma,
            user_id=user.id,
            privacy_notice_version=DEFAULT_PRIVACY_NOTICE_VERSION,
            terms_version=DEFAULT_TERMS_VERSION,
        )
        
        await prisma.userpreference.create(data={"userId": user.id})
        await prisma.userstatistics.create(data={"userId": user.id})
        await record_audit_event(
            prisma,
            event_type="AUTH_SIGNUP",
            action="auth.signup",
            subject_user_id=user.id,
            resource_type="user",
            resource_id=user.id,
            purpose="account creation",
            legal_basis="CONTRACT",
            request=http_request,
        )
        
        return AuthResponse(
            status="success",
            user_id=user.id,
            email=user.email,
            name=user.name
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[AUTH ERROR] Signup failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/auth/login")
async def auth_login(request: UserLoginRequest, http_request: Request):
    """Log in an existing user using email and password"""
    import bcrypt
    try:
        prisma = await get_prisma_client()
        email = _normalize_email(request.email)
        _validate_auth_payload(email, request.password)

        user = await prisma.user.find_unique(where={"email": email})
        if not user or not user.passwordHash:
            raise HTTPException(status_code=401, detail="Invalid email or password")
            
        if not bcrypt.checkpw(request.password.encode('utf-8'), user.passwordHash.encode('utf-8')):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        await record_audit_event(
            prisma,
            event_type="AUTH_LOGIN",
            action="auth.login",
            subject_user_id=user.id,
            resource_type="user",
            resource_id=user.id,
            purpose="account authentication",
            legal_basis="CONTRACT",
            request=http_request,
        )
            
        return AuthResponse(
            status="success",
            user_id=user.id,
            email=user.email,
            name=user.name
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[AUTH ERROR] Login failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/user/ensure")
async def ensure_user(request: ChatRequest):
    """Ensure user exists in database, creating anonymous user if needed"""
    try:
        prisma = await get_prisma_client()
        user_id = request.user_id or "anonymous"
        
        # Try to find existing user by ID
        existing_user = await prisma.user.find_unique(where={"id": user_id})
        
        if existing_user:
            return {
                "status": "success",
                "user_id": existing_user.id,
                "email": existing_user.email,
                "name": existing_user.name,
                "created": False
            }
        
        # Create new anonymous user with placeholder email
        email = f"{user_id}@sentimind.local"
        user = await prisma.user.create(
            data={
                "id": user_id,
                "email": email,
                "name": "Anonymous User" if user_id == "anonymous" else user_id
            }
        )
        
        # Create associated records
        await prisma.userpreference.create(data={"userId": user.id})
        await prisma.userstatistics.create(data={"userId": user.id})
        
        return {
            "status": "success",
            "user_id": user.id,
            "email": user.email,
            "name": user.name,
            "created": True
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/wellness/tips", response_model=List[WellnessTip])
async def get_wellness_tips():
    """Get wellness tips"""
    return [
        WellnessTip(id="1", title="Practice Gratitude", description="Note three things you're grateful for each day.", category="mindfulness"),
        WellnessTip(id="2", title="Deep Breathing", description="Try 4-7-8 breathing when stressed.", category="breathing"),
        WellnessTip(id="3", title="Stay Connected", description="Reach out to someone today.", category="social"),
        WellnessTip(id="4", title="Move Your Body", description="Even a 10-minute walk helps.", category="physical"),
        WellnessTip(id="5", title="Limit News", description="Set specific times for news/social media.", category="boundaries")
    ]


@app.get("/api/user/{user_id}/sessions")
async def get_user_sessions(user_id: str, request: Request, limit: int = 10, include_messages: bool = False):
    """Get user's recent session summaries, optionally including messages."""
    try:
        enforce_user_scope(request, user_id)
        limit = max(1, min(limit, 100))
        cache_key = (user_id, limit, include_messages, user_cache_version(user_id))
        cached = _USER_SESSIONS_CACHE.get(cache_key)
        if cached:
            schedule_audit_event(
                event_type="DATA_ACCESS",
                action="sessions.read",
                subject_user_id=user_id,
                resource_type="session",
                purpose="user chat history",
                legal_basis="CONSENT",
                request=request,
                metadata={"limit": limit, "include_messages": include_messages, "cache": "hit"},
            )
            return cached

        prisma = await get_prisma_client()

        query = {
            "where": {"userId": user_id},
            "order": {"startedAt": "desc"},
            "take": limit,
        }
        if include_messages:
            query["include"] = {"messages": {"include": {"technique": True}}}

        sessions = await prisma.session.find_many(**query)

        user_ratings_map = {}
        if include_messages:
            ratings = await prisma.usertechniquerating.find_many(
                where={"userId": user_id}
            )
            for r in sorted(ratings, key=lambda x: 0 if x.sessionId is None else 1):
                user_ratings_map[(r.sessionId, r.techniqueId)] = r
                if not r.sessionId:
                    user_ratings_map[(None, r.techniqueId)] = r

        schedule_audit_event(
            prisma,
            event_type="DATA_ACCESS",
            action="sessions.read",
            subject_user_id=user_id,
            resource_type="session",
            purpose="user chat history",
            legal_basis="CONSENT",
            request=request,
            metadata={"limit": limit, "include_messages": include_messages},
        )
        
        result_sessions = []
        for s in sessions:
            # Sort messages by createdAt in application code
            session_messages = getattr(s, "messages", []) or []
            sorted_messages = sorted(session_messages, key=lambda m: m.createdAt) if include_messages else []
            
            result_sessions.append({
                "id": s.id,
                "title": s.title,
                "status": str(s.status),
                "mood_summary": str(s.moodSummary) if s.moodSummary else None,
                "started_at": s.startedAt.isoformat() if s.startedAt else None,
                "ended_at": s.endedAt.isoformat() if s.endedAt else None,
                "preview": sorted_messages[0].content[:100] if sorted_messages else None,
                "message_count": len(sorted_messages),
                "messages": [
                    {
                        "id": m.id,
                        "role": _clean_enum(m.role),
                        "content": m.content,
                        **_emotion_payload_from_message(m),
                        "createdAt": m.createdAt.isoformat() if m.createdAt else None,
                        "technique": ({
                            "id": m.technique.id,
                            "name": m.technique.name,
                            "brief": m.technique.brief,
                            "description": m.technique.description,
                            "steps": m.technique.steps,
                            "duration_minutes": m.technique.durationMinutes,
                            "difficulty": str(m.technique.difficulty),
                            "category": m.technique.category.name if m.technique.category else "General",
                            "why_it_works": m.technique.whyItWorks,
                            "avg_rating": m.technique.avgRating,
                            "effectiveness": m.technique.effectiveness,
                            "user_rating": (
                                user_ratings_map.get((s.id, m.technique.id)) or 
                                user_ratings_map.get((None, m.technique.id))
                            ).rating if (
                                (s.id, m.technique.id) in user_ratings_map or 
                                (None, m.technique.id) in user_ratings_map
                            ) else None,
                            "user_completed": (
                                user_ratings_map.get((s.id, m.technique.id)) or 
                                user_ratings_map.get((None, m.technique.id))
                            ).completed if (
                                (s.id, m.technique.id) in user_ratings_map or 
                                (None, m.technique.id) in user_ratings_map
                            ) else False
                        } if getattr(m, 'technique', None) else None)
                    }
                    for m in sorted_messages
                ] if include_messages else []
            })
        
        response = {
            "status": "success",
            "sessions": result_sessions
        }
        for stale_key in [key for key in _USER_SESSIONS_CACHE if key[0] == user_id and key != cache_key]:
            _USER_SESSIONS_CACHE.pop(stale_key, None)
        _USER_SESSIONS_CACHE[cache_key] = response
        return response
        
    except Exception as e:
        print(f"[API] Error fetching user sessions: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/session/{session_id}/messages")
async def get_session_messages(session_id: str, request: Request):
    """Get all messages from a specific session"""
    try:
        cache_key = (session_id, session_cache_version(session_id))
        cached = _SESSION_MESSAGES_CACHE.get(cache_key)
        if cached:
            enforce_user_scope(request, cached["user_id"])
            schedule_audit_event(
                event_type="DATA_ACCESS",
                action="session.messages.read",
                subject_user_id=cached["user_id"],
                resource_type="session",
                resource_id=session_id,
                purpose="user chat history",
                legal_basis="CONSENT",
                request=request,
            )
            return cached["response"]

        prisma = await get_prisma_client()
        session = await prisma.session.find_unique(where={"id": session_id})
        if session:
            enforce_user_scope(request, session.userId)
        
        messages = await prisma.message.find_many(
            where={"sessionId": session_id},
            order={"createdAt": "asc"},
            include={"technique": True}
        )

        user_ratings_map = {}
        if session:
            ratings = await prisma.usertechniquerating.find_many(
                where={
                    "userId": session.userId,
                    "OR": [
                        {"sessionId": session_id},
                        {"sessionId": None}
                    ]
                }
            )
            for r in sorted(ratings, key=lambda x: 0 if x.sessionId is None else 1):
                user_ratings_map[r.techniqueId] = r

        if session:
            schedule_audit_event(
                prisma,
                event_type="DATA_ACCESS",
                action="session.messages.read",
                subject_user_id=session.userId,
                resource_type="session",
                resource_id=session_id,
                purpose="user chat history",
                legal_basis="CONSENT",
                request=request,
            )
        
        response = {
            "status": "success",
            "session_id": session_id,
            "messages": [
                {
                    "id": m.id,
                    "role": _clean_enum(m.role),
                    "content": m.content,
                    **_emotion_payload_from_message(m),
                    "createdAt": m.createdAt.isoformat() if m.createdAt else None,
                    "technique": ({
                        "id": m.technique.id,
                        "name": m.technique.name,
                        "brief": m.technique.brief,
                        "description": m.technique.description,
                        "steps": m.technique.steps,
                        "duration_minutes": m.technique.durationMinutes,
                        "difficulty": str(m.technique.difficulty),
                        "category": m.technique.category.name if m.technique and m.technique.category else "General",
                        "why_it_works": m.technique.whyItWorks,
                        "avg_rating": m.technique.avgRating,
                        "effectiveness": m.technique.effectiveness,
                        "user_rating": user_ratings_map.get(m.technique.id).rating if m.technique.id in user_ratings_map else None,
                        "user_completed": user_ratings_map.get(m.technique.id).completed if m.technique.id in user_ratings_map else False
                    } if getattr(m, 'technique', None) else None)
                }
                for m in messages
            ]
        }
        if session:
            for stale_key in [key for key in _SESSION_MESSAGES_CACHE if key[0] == session_id and key != cache_key]:
                _SESSION_MESSAGES_CACHE.pop(stale_key, None)
            _SESSION_MESSAGES_CACHE[cache_key] = {
                "user_id": session.userId,
                "response": response,
            }
        return response
        
    except Exception as e:
        print(f"[API] Error fetching session messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/session/{session_id}/rename")
async def rename_session(session_id: str, request: SessionRenameRequest, http_request: Request):
    """Rename a chat session"""
    try:
        prisma = await get_prisma_client()
        
        # Check if session exists
        session = await prisma.session.find_unique(where={"id": session_id})
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        enforce_user_scope(http_request, session.userId)
        
        title = request.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="Session title cannot be empty")
        title = title[:80]

        # Update the title
        updated_session = await prisma.session.update(
            where={"id": session_id},
            data={"title": title}
        )
        await record_audit_event(
            prisma,
            event_type="DATA_ACCESS",
            action="session.rename",
            subject_user_id=session.userId,
            resource_type="session",
            resource_id=session_id,
            purpose="user session management",
            legal_basis="CONSENT",
            request=http_request,
        )
        invalidate_user_cache(session.userId, session_id=session_id)
        
        return {
            "status": "success",
            "session_id": session_id,
            "title": updated_session.title
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SESSION] ❌ Error renaming session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str, request: Request):
    """
    Delete a chat session and all its messages.
    Cascade-deletes: messages → session.
    """
    try:
        print(f"[SESSION-DELETE] 🗑️  Deleting session: {session_id}")
        prisma = await get_prisma_client()

        # Verify session exists
        session = await prisma.session.find_unique(where={"id": session_id})
        if not session:
            print(f"[SESSION-DELETE] ⚠️  Session not found: {session_id}")
            raise HTTPException(status_code=404, detail="Session not found")
        enforce_user_scope(request, session.userId)

        # Keep local memory aligned with the source-of-truth DB.
        # Non-fatal: deletion should still succeed even if memory cleanup fails.
        try:
            from src.mental_health_wellness.memory import delete_session_memories

            cleanup = await delete_session_memories(session.userId, session_id)
            print(f"[SESSION-DELETE] Semantic memory cleanup: {cleanup}")
        except Exception as mem_err:
            print(f"[SESSION-DELETE] Semantic memory cleanup failed (non-fatal): {str(mem_err)[:100]}")

        # Delete all messages first (FK constraint)
        deleted_msgs = await prisma.message.delete_many(where={"sessionId": session_id})
        print(f"[SESSION-DELETE] 🧹 Deleted {deleted_msgs} messages")

        # Delete the session itself
        await prisma.session.delete(where={"id": session_id})
        await record_audit_event(
            prisma,
            event_type="SESSION_DELETE",
            action="session.delete",
            subject_user_id=session.userId,
            resource_type="session",
            resource_id=session_id,
            purpose="user initiated deletion",
            legal_basis="CONSENT",
            request=request,
            metadata={"deleted_messages": deleted_msgs},
        )
        invalidate_user_cache(session.userId, session_id=session_id)
        invalidate_session_cache(session_id)
        # Clear in-memory pipeline state so a recycled session_id cannot re-use
        # stale emotional anchors, thread context, or message history.
        clear_session_context(session_id)
        print(f"[SESSION-DELETE] Session {session_id} deleted successfully")

        return {
            "status": "success",
            "session_id": session_id,
            "message": "Session and all messages permanently deleted"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[SESSION-DELETE] ❌ Error deleting session {session_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/session/new")
async def create_new_chat_session(request: Request):
    """
    Create a fresh chat session with a guaranteed clean in-memory context.

    The frontend should call this endpoint when the user clicks "New Chat" so
    that the pipeline starts with zero emotional anchors, no stale thread
    context, and an empty message history.  Without this call the in-memory
    state store may retain context from the user's last session until the
    server naturally evicts it.

    Returns: {session_id, status}
    """
    try:
        body = await request.json()
        user_id = body.get("user_id") or body.get("userId")
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")

        from src.mental_health_wellness.db.client import create_new_session as _db_create_session

        new_session = await _db_create_session(user_id)
        session_id = new_session["id"]

        # Guarantee a clean in-memory slate — just in case this id was somehow
        # already in the store (e.g. server restart did not clear previous run).
        clear_session_context(session_id)

        invalidate_user_cache(user_id)
        print(f"[SESSION-NEW] Fresh session created: {session_id[:20]}... for user {user_id[:16]}...")

        return {
            "status": "ok",
            "session_id": session_id,
            "message": "New session created with clean context",
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[SESSION-NEW] Error creating session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/user/{user_id}/stats")
async def get_user_stats_legacy(user_id: str):
    """Get user statistics (legacy endpoint)"""
    try:
        prisma = await get_prisma_client()
        stats = await prisma.userstatistics.find_unique(where={"userId": user_id})
        if not stats:
            return {"message": "No statistics found"}
        return {
            "total_sessions": stats.totalSessions,
            "total_messages": stats.totalMessages,
            "current_streak": stats.currentCheckInStreak,
            "longest_streak": stats.longestCheckInStreak,
            "average_mood": stats.averageMoodRating,
            "techniques_used": stats.totalTechniquesUsed
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── New comprehensive dashboard endpoint ─────────────────────────────────────

class UserSettingsRequest(BaseModel):
    user_id: str
    settings: dict

class EmergencyContactRequest(BaseModel):
    name: str
    phone: str
    relation: Optional[str] = None
    channel: Optional[str] = "sms"

class OnboardingRequest(BaseModel):
    user_id: Optional[str] = None
    initial_mood: Optional[str] = None
    goals: List[str] = []
    notifications_enabled: bool = True
    crisis_location_consent: bool = False
    emergency_contact_consent: bool = False
    voice_analysis_consent: bool = False
    emergency_contacts: List[EmergencyContactRequest] = []


@app.get("/api/dashboard/stats")
async def get_dashboard_stats(user_id: str):
    """
    Legacy dashboard stats endpoint.

    Reuses the cached advanced dashboard service so dashboard reads have one
    query path instead of two separate implementations.
    """
    try:
        from src.mental_health_wellness.services.dashboard_analytics import build_user_dashboard

        dashboard = await build_user_dashboard(user_id=user_id, days=30)
        profile = dashboard.get("personalization", {}).get("profile", {})
        mood = dashboard.get("mood", {})
        overview = dashboard.get("overview", {})
        techniques = dashboard.get("techniques", {})
        sessions = dashboard.get("sessions", {})
        trend_label = (mood.get("trend") or {}).get("label")
        mood_trend = "up" if trend_label == "improving" else "down" if trend_label == "declining" else "stable"
        anxiety_value = float(profile.get("anxiety_baseline", 0.5) or 0.5)
        resilience_value = float(profile.get("resilience_score", 0.5) or 0.5)

        # sessions_this_week — count from recent sessions that started within 7 days
        from datetime import timedelta
        one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        sessions_this_week = sum(
            1 for s in (sessions.get("recent") or [])
            if s.get("started_at") and datetime.fromisoformat(
                str(s["started_at"]).replace("Z", "+00:00")
            ) >= one_week_ago
        )

        # top_techniques — prefer composite-ranked list from build_user_dashboard
        ranked = techniques.get("ranked") or []
        if ranked:
            top_techniques = [
                {
                    "name": item.get("name") or "Unnamed technique",
                    "category": item.get("category") or "general",
                    "usage_count": item.get("usageCount", 0),
                    "mean_effectiveness": item.get("meanEffectiveness"),
                    "composite_score": item.get("compositeScore"),
                }
                for item in ranked[:5]
            ]
        else:
            # Fallback to raw ratings when ranked list is empty
            top_techniques = [
                {
                    "name": item.get("technique", {}).get("name") or item.get("technique_id") or "Unnamed technique",
                    "category": item.get("technique", {}).get("category") or "general",
                    "usage_count": 1,
                }
                for item in (techniques.get("ratings") or [])[:5]
            ]

        # ai_insight — generate from profile context (mirrors dashboard.ts buildInsight logic)
        symptoms = profile.get("top_symptoms") or []
        secondary = profile.get("top_secondary_emotions") or []
        triggers = profile.get("emotional_triggers") or []
        distortions = profile.get("top_distortions") or []
        if symptoms and secondary:
            ai_insight = (
                f"Recent patterns connect {' and '.join(secondary[:2])} with "
                f"{symptoms[0].replace('_', ' ')}. "
                f"Track both the feeling and cognitive signal before deciding which support helps."
            )
        elif triggers and distortions:
            ai_insight = (
                f"Recent patterns connect {' and '.join(triggers[:2])} with {distortions[0]}. "
                f"Keep support focused on that trigger before choosing an exercise."
            )
        elif symptoms:
            ai_insight = (
                f"The clearest current signal is {symptoms[0].replace('_', ' ')}. "
                f"Improvement should be judged by whether that symptom eases."
            )
        elif triggers:
            ai_insight = (
                f"The clearest current trigger is {triggers[0]}. "
                f"Keep tracking what changes before and after that situation."
            )
        else:
            ai_insight = "More check-ins will make the profile sharper. Current analytics are ready, but personalization improves with repeated mood and technique feedback."

        return {
            "total_sessions": overview.get("total_sessions", 0),
            "sessions_this_week": sessions_this_week,
            "avg_mood": round(float(mood.get("average_score", 5.0) or 5.0) * 10),
            "streak": overview.get("current_checkin_streak", 0),
            "top_emotion": str(overview.get("most_common_emotion", "neutral")).lower(),
            "mood_trend": mood_trend,
            "techniques_tried": techniques.get("total_used", 0),
            "mood_timeline": mood.get("timeline", []),
            "emotion_distribution": [
                {"emotion": str(name).lower(), "count": count, "percentage": 0}
                for name, count in (mood.get("distribution") or {}).items()
            ],
            "top_techniques": top_techniques,
            "recent_sessions": sessions.get("recent", []),
            "psychological_profile": {
                "coping_style": profile.get("coping_style", "mixed"),
                "resilience": round(resilience_value * 100),
                "anxiety_baseline": "High" if anxiety_value >= 0.65 else "Low" if anxiety_value <= 0.35 else "Moderate",
                "ai_insight": ai_insight,
                "top_distortions": distortions,
                "emotional_triggers": triggers,
                "top_symptoms": symptoms,
                "top_behaviors": profile.get("top_behaviors") or [],
                "top_contexts": profile.get("top_contexts") or [],
            },
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        print(f"[DASHBOARD] ❌ Error computing dashboard stats for {user_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/user/{user_id}/profile")
async def get_user_profile(user_id: str, request: Request):
    """Return user profile: name, email, plan, createdAt, and preferences."""
    try:
        enforce_user_scope(request, user_id)
        cache_key = (user_id, user_cache_version(user_id))
        cached = _USER_PROFILE_CACHE.get(cache_key)
        if cached:
            cached_settings = cached.get("settings") if isinstance(cached, dict) else {}
            required_settings = {"emergencyContactConsent", "voiceAnalysisConsent"}
            if required_settings.issubset(set((cached_settings or {}).keys())):
                schedule_audit_event(
                    event_type="DATA_ACCESS",
                    action="user.profile.read",
                    subject_user_id=user_id,
                    resource_type="user",
                    resource_id=user_id,
                    purpose="profile settings display",
                    legal_basis="CONSENT",
                    request=request,
                )
                return cached

        prisma = await get_prisma_client()
        user = await prisma.user.find_unique(
            where={"id": user_id},
            include={"preference": True, "statistics": True},
        )
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        profile_overrides = await _read_profile_setting_overrides(prisma, user_id)
        consent_states = await get_effective_consent_states(
            prisma,
            user_id=user_id,
            scopes=["CRISIS_LOCATION", "EMERGENCY_CONTACT_ALERTS", "VOICE_ANALYSIS"],
        )
        legacy_location_consent = bool(user.preference.crisisLocationConsent) if user.preference else False
        legacy_contact_consent = bool(user.preference.emergencyContactConsent) if user.preference else False
        location_consent = (
            legacy_location_consent
            if consent_states.get("CRISIS_LOCATION") is None
            else bool(consent_states.get("CRISIS_LOCATION"))
        )
        emergency_contact_consent = (
            legacy_contact_consent
            if consent_states.get("EMERGENCY_CONTACT_ALERTS") is None
            else bool(consent_states.get("EMERGENCY_CONTACT_ALERTS"))
        )
        voice_analysis_consent = (
            bool(profile_overrides["voiceAnalysisConsent"])
            if consent_states.get("VOICE_ANALYSIS") is None
            else bool(consent_states.get("VOICE_ANALYSIS"))
        )
        schedule_audit_event(
            prisma,
            event_type="DATA_ACCESS",
            action="user.profile.read",
            subject_user_id=user_id,
            resource_type="user",
            resource_id=user_id,
            purpose="profile settings display",
            legal_basis="CONSENT",
            request=request,
        )
        response = {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "created_at": user.createdAt.isoformat() if user.createdAt else None,
            "settings": {
                "dailyReminderEnabled": user.preference.dailyCheckInEnabled if user.preference else True,
                "weeklyEmailEnabled": user.preference.moodRemindersEnabled if user.preference else True,
                "sessionAutoSave": profile_overrides["sessionAutoSave"],
                "anonymousMode": profile_overrides["anonymousMode"],
                "shareLocationInCrisis": location_consent,
                "emergencyContactConsent": emergency_contact_consent,
                "voiceAnalysisConsent": voice_analysis_consent,
                "theme": user.preference.theme if user.preference else "light",
            },
        }
        for stale_key in [key for key in _USER_PROFILE_CACHE if key[0] == user_id and key != cache_key]:
            _USER_PROFILE_CACHE.pop(stale_key, None)
        _USER_PROFILE_CACHE[cache_key] = response
        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/user/settings")
async def save_user_settings(request: UserSettingsRequest, http_request: Request):
    """Save user preferences / settings."""
    try:
        enforce_user_scope(http_request, request.user_id)
        prisma = await get_prisma_client()
        user = await prisma.user.find_unique(where={"id": request.user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        settings = request.settings
        pref = await prisma.userpreference.find_unique(where={"userId": request.user_id})
        update_data: dict = {}
        if "dailyReminderEnabled" in settings:
            update_data["dailyCheckInEnabled"] = bool(settings["dailyReminderEnabled"])
        if "weeklyEmailEnabled" in settings:
            update_data["moodRemindersEnabled"] = bool(settings["weeklyEmailEnabled"])
        if "theme" in settings:
            update_data["theme"] = str(settings["theme"])
        if "shareLocationInCrisis" in settings:
            update_data["crisisLocationConsent"] = bool(settings["shareLocationInCrisis"])
        if "emergencyContactConsent" in settings:
            update_data["emergencyContactConsent"] = bool(settings["emergencyContactConsent"])

        has_profile_overrides = any(
            key in settings
            for key in ["sessionAutoSave", "anonymousMode", "voiceAnalysisConsent"]
        )
        if update_data or has_profile_overrides:
            if pref:
                if update_data:
                    await prisma.userpreference.update(
                        where={"userId": request.user_id}, data=update_data
                    )
            else:
                await prisma.userpreference.create(data={"userId": request.user_id, **update_data})

        profile_override_fields = await _update_profile_setting_overrides(
            prisma,
            request.user_id,
            settings,
        )
        consent_fields = await _record_settings_consent_changes(
            prisma,
            user_id=request.user_id,
            settings=settings,
            request=http_request,
        )
        changed_fields = sorted(
            set(update_data.keys())
            | set(profile_override_fields)
            | set(consent_fields)
        )
        if changed_fields:
            await record_audit_event(
                prisma,
                event_type="DATA_ACCESS",
                action="user.settings.update",
                subject_user_id=request.user_id,
                resource_type="user_settings",
                resource_id=request.user_id,
                purpose="profile preference management",
                legal_basis="CONSENT",
                request=http_request,
                metadata={"fields": ",".join(changed_fields)},
            )
            invalidate_user_cache(request.user_id)

        return {"status": "success", "message": "Settings saved"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/user/onboarding")
async def save_onboarding(request: OnboardingRequest, http_request: Request):
    """
    Persist onboarding selections: initial mood → MoodLog,
    goals → UserFact, notifications → UserPreference.
    """
    try:
        prisma = await get_prisma_client()
        user_id = request.user_id or "anonymous"
        if user_id != "anonymous":
            enforce_user_scope(http_request, user_id)

        user = await prisma.user.find_unique(where={"id": user_id})
        if not user:
            return {"status": "skipped", "message": "User not found — onboarding data not saved"}

        MOOD_TO_EMOTION = {
            "great": "JOY",
            "good": "JOY",
            "okay": "NEUTRAL",
            "low": "SADNESS",
            "awful": "SADNESS",
        }
        MOOD_TO_INTENSITY = {
            "great": 0.9,
            "good": 0.75,
            "okay": 0.5,
            "low": 0.3,
            "awful": 0.1,
        }

        # Save initial mood as MoodLog
        if request.initial_mood:
            emotion = MOOD_TO_EMOTION.get(request.initial_mood, "NEUTRAL")
            intensity = MOOD_TO_INTENSITY.get(request.initial_mood, 0.5)
            await prisma.moodlog.create(
                data={
                    "userId": user_id,
                    "emotion": emotion,
                    "intensity": intensity,
                    "sentiment": "POSITIVE" if intensity >= 0.6 else "NEGATIVE" if intensity <= 0.35 else "NEUTRAL",
                    "context": "onboarding_initial_mood",
                    "method": "self_report",
                }
            )

        # Save goals as UserFacts
        for goal in request.goals:
            await prisma.userfact.create(
                data={
                    "userId": user_id,
                    "fact": f"User wellness goal: {goal}",
                    "category": "goal",
                }
            )

        contact_payloads = []
        if request.emergency_contact_consent:
            seen_numbers = set()
            for contact in request.emergency_contacts or []:
                phone = _normalize_phone(contact.phone)
                name = str(contact.name or "").strip()
                if not phone or not name or phone in seen_numbers:
                    continue
                seen_numbers.add(phone)
                channel = str(contact.channel or "sms").lower()
                contact_payloads.append({
                    "userId": user_id,
                    "name": name[:120],
                    "phone": phone,
                    "relation": str(contact.relation or "").strip()[:80] or None,
                    "channel": "whatsapp" if channel == "whatsapp" else "sms",
                    "active": True,
                })

        await prisma.emergencycontact.delete_many(where={"userId": user_id})
        for payload in contact_payloads:
            await prisma.emergencycontact.create(data=payload)

        # Update notification and crisis consent preferences
        pref = await prisma.userpreference.find_unique(where={"userId": user_id})
        preference_data = {
            "dailyCheckInEnabled": request.notifications_enabled,
            "crisisLocationConsent": bool(request.crisis_location_consent),
            "emergencyContactConsent": bool(request.emergency_contact_consent and contact_payloads),
        }
        if pref:
            await prisma.userpreference.update(
                where={"userId": user_id},
                data=preference_data,
            )
        else:
            await prisma.userpreference.create(
                data={"userId": user_id, **preference_data}
            )
        await _update_profile_setting_overrides(
            prisma,
            user_id,
            {"voiceAnalysisConsent": bool(request.voice_analysis_consent)},
        )

        consent_grants = {
            "CRISIS_LOCATION": bool(request.crisis_location_consent),
            "EMERGENCY_CONTACT_ALERTS": bool(request.emergency_contact_consent and contact_payloads),
            "VOICE_ANALYSIS": bool(request.voice_analysis_consent),
        }
        for scope, granted in consent_grants.items():
            if not granted:
                continue
            await record_consent_records(
                prisma,
                user_id=user_id,
                scopes=[scope],
                granted=True,
                legal_basis="CONSENT",
                policy_version=DEFAULT_CONSENT_VERSION,
                notice_version=DEFAULT_PRIVACY_NOTICE_VERSION,
                terms_version=DEFAULT_TERMS_VERSION,
                locale=None,
                processing_region=None,
                request=http_request,
            )

        await record_audit_event(
            prisma,
            event_type="DATA_ACCESS",
            action="user.onboarding.save",
            subject_user_id=user_id,
            resource_type="onboarding",
            resource_id=user_id,
            purpose="initial personalization",
            legal_basis="CONSENT",
            request=http_request,
            metadata={
                "goals_count": len(request.goals or []),
                "has_initial_mood": bool(request.initial_mood),
                "emergency_contacts": len(contact_payloads),
                "crisis_location_consent": bool(request.crisis_location_consent),
                "voice_analysis_consent": bool(request.voice_analysis_consent),
            },
        )
        invalidate_user_cache(user_id)

        return {"status": "success", "message": "Onboarding data saved"}
    except Exception as e:
        print(f"[ONBOARDING] Error: {e}")
        # Non-critical — don't crash the user flow
        return {"status": "error", "message": str(e)}


@app.delete("/api/user/{user_id}")
async def delete_user_account(user_id: str, request: Request):
    """Delete user account and all associated data (GDPR erasure)."""
    try:
        enforce_user_scope(request, user_id)
        prisma = await get_prisma_client()
        user = await prisma.user.find_unique(where={"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        await create_data_subject_request(
            prisma,
            user_id=user_id,
            request_type="ERASURE",
            status="COMPLETED",
            metadata={"endpoint": "/api/user/{user_id}"},
            resolution_notes="Account and application data deleted via cascade; audit record retained pseudonymously.",
        )
        try:
            from src.mental_health_wellness.memory import delete_user_memories

            cleanup = await delete_user_memories(user_id)
            print(f"[USER-DELETE] Semantic memory cleanup: {cleanup}")
        except Exception as mem_err:
            print(f"[USER-DELETE] Semantic memory cleanup failed (non-fatal): {str(mem_err)[:100]}")
        await prisma.user.delete(where={"id": user_id})
        await record_audit_event(
            prisma,
            event_type="DATA_ERASURE",
            action="user.delete",
            subject_user_id=user_id,
            resource_type="user",
            resource_id=user_id,
            purpose="data subject erasure request",
            legal_basis="CONSENT",
            request=request,
        )
        invalidate_user_cache(user_id)
        return {"status": "success", "message": "Account permanently deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/techniques")
async def get_techniques(emotion: Optional[str] = None, category: Optional[str] = None):
    """Get available techniques"""
    try:
        cache_key = (
            emotion.strip().lower() if emotion else None,
            category.strip().lower() if category else None,
            _TECHNIQUES_CACHE_VERSION,
        )
        cached = _TECHNIQUES_CACHE.get(cache_key)
        if cached:
            return cached

        prisma = await get_prisma_client()
        
        where_conditions = {"isActive": True}
        
        # For array filtering in Prisma, we need to use 'hasSome' instead of 'has'
        if emotion:
            emotion_upper = emotion.upper()
            # Map common emotion names to schema enums
            emotion_map = {
                "fear": "ANXIETY", 
                "anxiety": "ANXIETY",
                "sadness": "SADNESS", 
                "anger": "ANGER",
                "joy": "JOY", 
                "neutral": "NEUTRAL",
                "disgust": "ANGER",
                "surprise": "JOY"
            }
            target_emotion = emotion_map.get(emotion.lower(), emotion.upper())
            where_conditions["targetEmotions"] = {"hasSome": [target_emotion]}
        
        techniques = await prisma.technique.find_many(
            where=where_conditions,
            include={"category": True},
            order={"avgRating": "desc"}
        )
        
        normalized_category = category.strip().lower() if category else None
        response = {
            "status": "success",
            "techniques": [
                {
                    "id": t.id,
                    "name": t.name,
                    "brief": t.brief,
                    "description": t.description,
                    "category": t.category.name if t.category else "General",
                    "duration_minutes": t.durationMinutes,
                    "difficulty": str(t.difficulty),
                    "steps": t.steps,
                    "why_it_works": t.whyItWorks,
                    "avg_rating": t.avgRating,
                    "total_ratings": t.totalRatings,
                    "effectiveness": t.effectiveness
                }
                for t in techniques
                if not normalized_category
                or (t.category and t.category.name.lower() == normalized_category)
            ]
        }
        _TECHNIQUES_CACHE[cache_key] = response
        return response
        
    except Exception as e:
        print(f"[API] Error fetching techniques: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching techniques: {str(e)}")


@app.post("/api/technique/rate", response_model=TechniqueRatingResponse)
async def rate_technique(request: TechniqueRatingRequest, http_request: Request):
    """Submit rating and feedback for a technique"""
    try:
        # Validate rating is between 1-5 if provided
        if request.rating is not None and not (1 <= request.rating <= 5):
            raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")
        enforce_user_scope(http_request, request.user_id)
        
        prisma = await get_prisma_client()
        
        # Check if a rating already exists for this user, technique, and session
        existing = await prisma.usertechniquerating.find_first(
            where={
                "userId": request.user_id,
                "techniqueId": request.technique_id,
                "sessionId": request.session_id,
            }
        )
        
        if existing:
            # Update the existing record
            update_data = {
                "completed": request.completed or getattr(existing, "completed", False)
            }
            if request.rating is not None:
                update_data["rating"] = request.rating
            if request.feedback is not None:
                update_data["feedback"] = request.feedback
                
            await prisma.usertechniquerating.update(
                where={"id": existing.id},
                data=update_data
            )
        else:
            # Create a new record
            await prisma.usertechniquerating.create(
                data={
                    "userId": request.user_id,
                    "techniqueId": request.technique_id,
                    "rating": request.rating,
                    "feedback": request.feedback,
                    "completed": request.completed,
                    "sessionId": request.session_id
                }
            )
        
        # Update technique aggregates if a rating is supplied.
        technique = await prisma.technique.find_unique(
            where={"id": request.technique_id}
        )
        
        if technique and request.rating is not None:
            old_total = int(getattr(technique, "totalRatings", 0) or 0)
            old_avg = float(getattr(technique, "avgRating", 0.0) or 0.0)
            
            if existing and getattr(existing, "rating", None) is not None:
                # Modifying an existing rating value
                existing_rating = int(existing.rating)
                if old_total > 0:
                    new_avg = round(((old_avg * old_total) - existing_rating + request.rating) / old_total, 2)
                    new_total = old_total
                else:
                    new_avg = float(request.rating)
                    new_total = 1
            else:
                # First time adding a rating for this record
                new_total = old_total + 1
                new_avg = round(((old_avg * old_total) + request.rating) / new_total, 2)

            await prisma.technique.update(
                where={"id": request.technique_id},
                data={
                    "avgRating": new_avg,
                    "totalRatings": new_total
                }
            )

        await _update_personalized_technique_preferences(
            prisma=prisma,
            user_id=request.user_id,
            technique_id=request.technique_id,
            rating=request.rating,
            completed=request.completed,
        )
        invalidate_user_cache(request.user_id)
        invalidate_techniques_cache()
        
        return {
            "status": "success",
            "message": "Thank you for your feedback!",
            "technique_id": request.technique_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] Error rating technique: {e}")
        raise HTTPException(status_code=500, detail=f"Error saving rating: {str(e)}")


# ============================================
# CONSENT & GDPR ENDPOINTS
# ============================================

@app.post("/api/user/{user_id}/consent")
async def record_consent(user_id: str, consent: ConsentRequest, request: Request):
    """Record scoped consent / processing notice acknowledgement."""
    try:
        enforce_user_scope(request, user_id)
        prisma = await get_prisma_client()
        
        user = await prisma.user.find_unique(where={"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        normalized_scopes = [scope.upper() for scope in consent.scopes]
        
        consent_date = datetime.now()
        await update_user_privacy_metadata(
            prisma,
            user_id=user_id,
            consent_given=True,
            consent_date=consent_date,
            consent_version=consent.policy_version,
            privacy_notice_version=consent.notice_version,
            terms_version=consent.terms_version,
            processing_region=consent.processing_region,
        )
        await record_consent_records(
            prisma,
            user_id=user_id,
            scopes=normalized_scopes,
            granted=True,
            legal_basis=consent.legal_basis.upper(),
            policy_version=consent.policy_version,
            notice_version=consent.notice_version,
            terms_version=consent.terms_version,
            locale=consent.locale,
            processing_region=consent.processing_region,
            request=request,
        )
        await record_audit_event(
            prisma,
            event_type="CONSENT_GRANTED",
            action="consent.grant",
            subject_user_id=user_id,
            resource_type="consent",
            resource_id=user_id,
            purpose="privacy governance",
            legal_basis=consent.legal_basis.upper(),
            request=request,
            metadata={"scopes": ",".join(normalized_scopes), "policy_version": consent.policy_version},
        )
        invalidate_user_cache(user_id)
        
        return {
            "status": "success",
            "consent_given": True,
            "consent_date": consent_date.isoformat(),
            "scopes": normalized_scopes,
            "policy_version": consent.policy_version,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/user/{user_id}/consent/withdraw")
async def withdraw_consent(user_id: str, withdrawal: ConsentWithdrawRequest, request: Request):
    """Record consent withdrawal without silently deleting historical audit data."""
    try:
        enforce_user_scope(request, user_id)
        prisma = await get_prisma_client()

        user = await prisma.user.find_unique(where={"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        scopes = [scope.upper() for scope in (withdrawal.scopes or [
            "WELLNESS_CHAT",
            "MOOD_ANALYTICS",
            "PERSONALIZATION",
            "CRISIS_SAFETY",
        ])]

        await update_user_privacy_metadata(
            prisma,
            user_id=user_id,
            consent_given=False,
        )
        await record_consent_records(
            prisma,
            user_id=user_id,
            scopes=scopes,
            granted=False,
            legal_basis="CONSENT",
            policy_version=DEFAULT_CONSENT_VERSION,
            notice_version=DEFAULT_PRIVACY_NOTICE_VERSION,
            terms_version=DEFAULT_TERMS_VERSION,
            locale=None,
            processing_region=None,
            request=request,
        )
        scope_set = set(scopes)
        preference_updates: dict[str, bool] = {}
        if "CRISIS_LOCATION" in scope_set:
            preference_updates["crisisLocationConsent"] = False
        if "EMERGENCY_CONTACT_ALERTS" in scope_set:
            preference_updates["emergencyContactConsent"] = False
        if preference_updates:
            pref = await prisma.userpreference.find_unique(where={"userId": user_id})
            if pref:
                await prisma.userpreference.update(
                    where={"userId": user_id},
                    data=preference_updates,
                )
            else:
                await prisma.userpreference.create(
                    data={"userId": user_id, **preference_updates}
                )
        if "VOICE_ANALYSIS" in scope_set:
            pref = await prisma.userpreference.find_unique(where={"userId": user_id})
            if not pref:
                await prisma.userpreference.create(data={"userId": user_id})
            await _update_profile_setting_overrides(
                prisma,
                user_id,
                {"voiceAnalysisConsent": False},
            )
        await create_data_subject_request(
            prisma,
            user_id=user_id,
            request_type="CONSENT_WITHDRAWAL",
            status="COMPLETED",
            metadata={"scopes": scopes, "reason": withdrawal.reason or ""},
            resolution_notes="Consent marked withdrawn. Existing erasure requires /api/user/{user_id}/data.",
        )
        await record_audit_event(
            prisma,
            event_type="CONSENT_WITHDRAWN",
            action="consent.withdraw",
            subject_user_id=user_id,
            resource_type="consent",
            resource_id=user_id,
            purpose="privacy governance",
            legal_basis="CONSENT",
            request=request,
            metadata={"scopes": ",".join(scopes), "reason": withdrawal.reason or ""},
        )
        invalidate_user_cache(user_id)

        return {"status": "success", "consent_given": False, "scopes": scopes}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/user/{user_id}/data-export")
async def export_user_data(user_id: str, request: Request):
    """Export all user data (GDPR Article 15 - Right of Access)"""
    try:
        enforce_user_scope(request, user_id)
        prisma = await get_prisma_client()
        
        user = await prisma.user.find_unique(
            where={"id": user_id},
            include={
                "sessions": {
                    "include": {
                        "messages": True,
                        "summaries": True,
                        "techniqueOutcomes": True,
                        "clinicalAssessments": True,
                        "emotionSnapshots": True,
                    }
                },
                "moodLogs": True,
                "emergencyContacts": True,
                "techniqueRatings": True,
                "crisisLogs": True,
                "preference": True,
                "statistics": True,
                "facts": True,
                "sessionSummaries": True,
                "psychProfile": True,
            }
        )
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        await create_data_subject_request(
            prisma,
            user_id=user_id,
            request_type="ACCESS",
            status="COMPLETED",
            metadata={"endpoint": "/api/user/{user_id}/data-export"},
            resolution_notes="Self-service export generated.",
        )
        await record_audit_event(
            prisma,
            event_type="DATA_EXPORT",
            action="user.data_export",
            subject_user_id=user_id,
            resource_type="user",
            resource_id=user_id,
            purpose="data subject access request",
            legal_basis="CONSENT",
            request=request,
        )
        compliance_records = await fetch_compliance_records(prisma, user_id=user_id)

        export = {
            "user": {
                "name": user.name,
                "email": user.email,
                "created_at": user.createdAt.isoformat() if user.createdAt else None,
                "consent_given": user.consentGiven,
                "consent_date": user.consentDate.isoformat() if user.consentDate else None,
            },
            "sessions": [
                {
                    "title": s.title,
                    "started_at": s.startedAt.isoformat() if s.startedAt else None,
                    "ended_at": s.endedAt.isoformat() if s.endedAt else None,
                    "status": str(s.status),
                    "phase": str(s.phase) if s.phase else None,
                    "messages": [
                        {
                            "role": str(m.role),
                            "content": m.content,
                            "emotion": str(m.emotion) if m.emotion else None,
                            "primary_sub_emotion": getattr(m, "primarySubEmotion", None),
                            "secondary_sub_emotions": _as_list(getattr(m, "secondarySubEmotions", [])),
                            "detected_symptoms": _as_list(getattr(m, "detectedSymptoms", [])),
                            "detected_behaviors": _as_list(getattr(m, "detectedBehaviors", [])),
                            "detected_contexts": _as_list(getattr(m, "detectedContexts", [])),
                            "emotion_scores": getattr(m, "emotionScores", None) or {},
                            "intensity": m.intensity,
                            "sentiment": str(m.sentiment) if m.sentiment else None,
                            "created_at": m.createdAt.isoformat() if m.createdAt else None,
                        }
                        for m in (s.messages or [])
                    ],
                    "summaries": [
                        {
                            "title": summary.title,
                            "summary": summary.summary,
                            "emotion": summary.emotion,
                            "techniques": summary.techniques,
                            "outcome": summary.outcome,
                            "created_at": summary.createdAt.isoformat() if summary.createdAt else None,
                        }
                        for summary in (getattr(s, "summaries", []) or [])
                    ],
                    "technique_outcomes": [
                        {
                            "technique_id": outcome.techniqueId,
                            "emotion_before": str(outcome.emotionBefore),
                            "emotion_after": str(outcome.emotionAfter) if outcome.emotionAfter else None,
                            "sub_emotion_before": getattr(outcome, "subEmotionBefore", None),
                            "sub_emotion_after": getattr(outcome, "subEmotionAfter", None),
                            "symptoms_before": _as_list(getattr(outcome, "symptomsBefore", [])),
                            "symptoms_after": _as_list(getattr(outcome, "symptomsAfter", [])),
                            "behaviors_before": _as_list(getattr(outcome, "behaviorsBefore", [])),
                            "behaviors_after": _as_list(getattr(outcome, "behaviorsAfter", [])),
                            "intensity_before": outcome.intensityBefore,
                            "intensity_after": outcome.intensityAfter,
                            "effectiveness": outcome.effectiveness,
                            "created_at": outcome.createdAt.isoformat() if outcome.createdAt else None,
                        }
                        for outcome in (getattr(s, "techniqueOutcomes", []) or [])
                    ],
                    "clinical_assessments": [
                        {
                            "severity": str(assessment.severity),
                            "phq9_score": assessment.phq9Score,
                            "gad7_score": assessment.gad7Score,
                            "indicators": assessment.indicators,
                            "confidence": assessment.confidence,
                            "assessed_at": assessment.assessedAt.isoformat() if assessment.assessedAt else None,
                        }
                        for assessment in (getattr(s, "clinicalAssessments", []) or [])
                    ],
                    "emotion_snapshots": [
                        {
                            "turn": snapshot.turn,
                            "emotion": str(snapshot.emotion),
                            "primary_sub_emotion": getattr(snapshot, "primarySubEmotion", None),
                            "secondary_sub_emotions": _as_list(getattr(snapshot, "secondarySubEmotions", [])),
                            "detected_symptoms": _as_list(getattr(snapshot, "detectedSymptoms", [])),
                            "detected_behaviors": _as_list(getattr(snapshot, "detectedBehaviors", [])),
                            "detected_contexts": _as_list(getattr(snapshot, "detectedContexts", [])),
                            "intensity": snapshot.intensity,
                            "sentiment": str(snapshot.sentiment),
                            "phase": str(snapshot.phase) if snapshot.phase else None,
                            "created_at": snapshot.createdAt.isoformat() if snapshot.createdAt else None,
                        }
                        for snapshot in (getattr(s, "emotionSnapshots", []) or [])
                    ],
                }
                for s in (user.sessions or [])
            ],
            "mood_logs": [
                {
                    "emotion": str(ml.emotion) if ml.emotion else None,
                    "primary_sub_emotion": getattr(ml, "primarySubEmotion", None),
                    "secondary_sub_emotions": _as_list(getattr(ml, "secondarySubEmotions", [])),
                    "detected_symptoms": _as_list(getattr(ml, "detectedSymptoms", [])),
                    "detected_behaviors": _as_list(getattr(ml, "detectedBehaviors", [])),
                    "detected_contexts": _as_list(getattr(ml, "detectedContexts", [])),
                    "emotion_scores": getattr(ml, "emotionScores", None) or {},
                    "intensity": ml.intensity,
                    "sentiment": str(ml.sentiment) if ml.sentiment else None,
                    "context": ml.context,
                    "notes": ml.notes,
                    "method": ml.method,
                    "logged_at": ml.createdAt.isoformat() if ml.createdAt else None,
                }
                for ml in (user.moodLogs or [])
            ],
            "technique_ratings": [
                {"rating": tr.rating, "feedback": tr.feedback, "completed": tr.completed}
                for tr in (user.techniqueRatings or [])
            ],
            "emergency_contacts": [
                {
                    "name": contact.name,
                    "phone": contact.phone,
                    "relation": contact.relation,
                    "channel": contact.channel,
                    "active": contact.active,
                    "created_at": contact.createdAt.isoformat() if contact.createdAt else None,
                }
                for contact in (getattr(user, "emergencyContacts", []) or [])
            ],
            "crisis_logs": [
                {
                    "risk_level": str(log.riskLevel),
                    "triggered_keywords": log.triggeredKeywords,
                    "action_taken": log.actionTaken,
                    "resources_provided": log.resourcesProvided,
                    "human_handoff_requested": log.humanHandoffRequested,
                    "created_at": log.createdAt.isoformat() if log.createdAt else None,
                }
                for log in (user.crisisLogs or [])
            ],
            "memory_facts": [
                {
                    "fact": fact.fact,
                    "category": fact.category,
                    "created_at": fact.createdAt.isoformat() if fact.createdAt else None,
                    "updated_at": fact.updatedAt.isoformat() if fact.updatedAt else None,
                }
                for fact in (getattr(user, "facts", []) or [])
            ],
            "psychological_profile": ({
                "coping_style": user.psychProfile.copingStyle,
                "technique_acceptance_rate": user.psychProfile.techniqueAccRate,
                "reflection_depth": user.psychProfile.reflectionDepth,
                "anxiety_baseline": user.psychProfile.anxietyBaseline,
                "resilience_score": user.psychProfile.resilienceScore,
                "dominant_emotion": user.psychProfile.dominantEmotion,
                "emotional_triggers": user.psychProfile.emotionalTriggers,
                "motivation_type": user.psychProfile.motivationType,
                "social_dependency": user.psychProfile.socialDependency,
                "top_distortions": user.psychProfile.topDistortions,
                "distortion_count": user.psychProfile.distortionCount,
            } if getattr(user, "psychProfile", None) else None),
            "statistics": ({
                "total_sessions": user.statistics.totalSessions,
                "total_messages": user.statistics.totalMessages,
                "total_checkins": user.statistics.totalCheckIns,
                "average_mood_rating": user.statistics.averageMoodRating,
                "most_common_emotion": str(user.statistics.mostCommonEmotion),
            } if user.statistics else None),
            "preferences": {
                "communication_style": user.preference.communicationStyle if user.preference else None,
                "detail_level": user.preference.detailLevel if user.preference else None,
                "tone": user.preference.tone if user.preference else None,
                "language": user.preference.language if user.preference else None,
                "timezone": user.preference.timezone if user.preference else None,
                "preferred_categories": user.preference.preferredCategories if user.preference else [],
                "crisis_location_consent": user.preference.crisisLocationConsent if user.preference else False,
                "emergency_contact_consent": user.preference.emergencyContactConsent if user.preference else False,
            } if user.preference else None,
            "compliance": compliance_records,
            "exported_at": datetime.now().isoformat()
        }
        
        return {"status": "success", "data": export}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/user/{user_id}/data")
async def delete_user_data(user_id: str, request: Request):
    """Delete all user data (GDPR Article 17 - Right to Erasure)"""
    try:
        enforce_user_scope(request, user_id)
        prisma = await get_prisma_client()
        
        user = await prisma.user.find_unique(where={"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        await create_data_subject_request(
            prisma,
            user_id=user_id,
            request_type="ERASURE",
            status="COMPLETED",
            metadata={"endpoint": "/api/user/{user_id}/data"},
            resolution_notes="User data deleted via cascade; semantic embeddings requested for deletion.",
        )

        try:
            from src.mental_health_wellness.memory import delete_user_memories

            cleanup = await delete_user_memories(user_id)
            print(f"[USER-DATA-DELETE] Semantic memory cleanup: {cleanup}")
        except Exception as mem_err:
            print(f"[USER-DATA-DELETE] Semantic memory cleanup failed (non-fatal): {str(mem_err)[:100]}")
        
        # Cascade delete handles related records (sessions, messages, etc.)
        await prisma.user.delete(where={"id": user_id})
        await record_audit_event(
            prisma,
            event_type="DATA_ERASURE",
            action="user.data_delete",
            subject_user_id=user_id,
            resource_type="user",
            resource_id=user_id,
            purpose="data subject erasure request",
            legal_basis="CONSENT",
            request=request,
        )
        invalidate_user_cache(user_id)
        
        return {
            "status": "success",
            "message": "All user data has been permanently deleted",
            "user_id": user_id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# VOICE CHAT ENDPOINT
# ============================================


# ============================================
# VOICE PROCESSING HELPER
# ============================================

def try_decode_webm_to_wav(webm_bytes: bytes, output_path: str) -> bool:
    """
    Compatibility hook retained for older callers.

    Gemini audio analysis accepts WebM, WAV, MP3, OGG, and MP4 bytes directly,
    so the voice endpoint no longer decodes audio through local libraries.
    """
    return False


@app.post("/api/chat/voice")
async def chat_voice(
    http_request: Request,
    audio: UploadFile = File(...),
    user_id: str = Form("anonymous"),
    message: str = Form(""),
    session_id: Optional[str] = Form(None)
):
    """
    Voice-enabled chat endpoint. Uses the transcript for smart-gate routing.
    
    ARCHITECTURE FLOW:
    1. Save audio blob to a temporary file
    2. Run Gemini audio preprocessing for transcript plus optional voice features
    3. Run the main pipeline with the transcript as the user message
    4. Let emotion fusion use voice features only for therapeutic/crisis routes
    5. Return transcript and any voice analysis that was linked by the pipeline
    
    Audio format: WAV, MP3, WebM, or other common audio formats (16kHz+ recommended)
    """
    import tempfile
    import os as _os
    request_start = time.time()
    
    try:
        enforce_user_scope(http_request, user_id)
        print(f"\n[API: VOICE] 🎤 Voice endpoint called - user: {user_id}, session: {session_id}")
        
        # ============================================
        # RECEIVE AND SAVE AUDIO
        # ============================================
        logger.info(
            "Latency VOICE | start | user=%s session=%s",
            user_id,
            session_id or "new",
        )
        
        stage_start = time.time()
        audio_bytes = await audio.read()
        logger.info(
            "Latency VOICE | read_upload | user=%s | %.3fs",
            user_id,
            latency_seconds(stage_start),
        )
        print(f"[API: VOICE] 📥 Received {len(audio_bytes)} bytes of audio")
        
        # Detect audio format
        audio_format = _detect_audio_format(audio_bytes)
        print(f"[API: VOICE] 🔍 Detected audio format: {audio_format}")
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as tmp:
            tmp.write(audio_bytes)
            temp_audio_path = tmp.name
        
        print(f"[API: VOICE] 💾 Saved audio to: {temp_audio_path}")
        
        # ============================================
        # ROUTE TO VOICE PRE-PROCESSING NODE
        # ============================================
        
        from src.mental_health_wellness.nodes.voice_preprocessing import preprocess_voice_input
        
        # Create state for voice preprocessing
        voice_state = {
            "audio_file_path": temp_audio_path,
            "message": message
        }
        
        # Run voice preprocessing
        stage_start = time.time()
        voice_result = await preprocess_voice_input(voice_state)
        logger.info(
            "Latency VOICE | preprocessing | user=%s | %.3fs",
            user_id,
            latency_seconds(stage_start),
        )
        
        transcription = voice_result.get("transcription", "")
        final_message = voice_result.get("final_message", message)
        temp_audio_path = voice_result.get("temp_audio_path")  # Update in case it changed
        prefetched_voice_features: Optional[dict] = None
        
        # Debug: Log what we got from voice preprocessing
        print(f"[API: VOICE] 🔍 DEBUG - voice_result keys: {list(voice_result.keys())}")
        print(f"[API: VOICE] 🔍 DEBUG - transcription from result: '{transcription}'")
        print(f"[API: VOICE] 🔍 DEBUG - final_message from result: '{final_message}'")
        print(f"[API: VOICE] 🔍 DEBUG - original message param: '{message}'")
        
        print(
            "[API: VOICE] ✅ Voice preprocessing complete: "
            f"voice_transcribed={voice_result.get('voice_transcribed', False)}"
        )
        
        if voice_result.get("voice_processed") and voice_result.get("voice_features"):
            prefetched_voice_features = voice_result["voice_features"]
            vf = prefetched_voice_features
            print(
                "[API: VOICE] Voice features extracted and forwarded to graph:\n"
                f"  Emotion: {vf.get('emotion')} (confidence={vf.get('confidence', 0.0):.0%})\n"
                f"  Intensity: {vf.get('intensity', 0.5):.0%} | distress_index={vf.get('distress_index', 0.0):.2f}\n"
                f"  Sub-emotion: {vf.get('primary_sub_emotion')} | arousal={vf.get('arousal', 0.5):.0%}\n"
                "  Handoff: transcript routes the graph; fusion links voice features only on supported routes"
            )
        else:
            print("[API: VOICE] Voice features unavailable; graph may retry audio preprocessing")

        # ============================================
        # RUN THROUGH MAIN PIPELINE
        # ============================================
        
        print(f"[API: VOICE] ✅ Final message: '{final_message[:100]}...'")
        print(f"[API: VOICE] 🚀 Routing to chat_with_agent...")
        
        stage_start = time.time()
        result = await chat_with_agent(
            user_id=user_id,
            message=final_message,
            session_id=session_id,
            audio_file_path=temp_audio_path if not prefetched_voice_features else None,
            voice_features=prefetched_voice_features,
        )
        logger.info(
            "Latency VOICE | agent_complete | user=%s session=%s | %.3fs",
            user_id,
            result.get("session_id") or session_id or "new",
            latency_seconds(stage_start),
        )

        voice_features = result.get("voice_features") or {}
        voice_processed = bool(result.get("voice_processed") and voice_features)
        voice_confidence = voice_features.get("confidence", 0.0) if voice_features else 0.0
        voice_emotion = voice_features.get("emotion", "neutral") if voice_features else "neutral"
        transcription = result.get("transcription") or transcription
        
        # ============================================
        # CLEANUP TEMP AUDIO FILE
        # ============================================
        
        if temp_audio_path and _os.path.exists(temp_audio_path):
            try:
                _os.unlink(temp_audio_path)
                print(f"[API: VOICE] 🧹 Cleaned up temp audio file")
            except Exception as e:
                print(f"[API: VOICE] ⚠️ Could not delete temp file: {e}")
        
        # ============================================
        # RETURN RESPONSE WITH VOICE DATA
        # ============================================
        logger.info(
            "Latency VOICE | complete | user=%s session=%s | %.3fs",
            user_id,
            result.get("session_id") or session_id or "new",
            latency_seconds(request_start),
        )
        
        emotion_payload = _emotion_payload_from_result(result)

        return {
            "response": result.get("response", "I'm here to listen."),
            "session_id": result.get("session_id"),
            **emotion_payload,
            "voice_emotion": voice_emotion if voice_processed else None,
            "voice_confidence": voice_confidence if voice_processed else 0.0,
            "voice_primary_sub_emotion": voice_features.get("primary_sub_emotion") if voice_features else None,
            "voice_secondary_sub_emotions": voice_features.get("secondary_sub_emotions", []) if voice_features else [],
            "voice_detected_symptoms": voice_features.get("detected_symptoms", []) if voice_features else [],
            "voice_detected_behaviors": voice_features.get("detected_behaviors", []) if voice_features else [],
            "voice_detected_contexts": voice_features.get("detected_contexts", []) if voice_features else [],
            "transcription": transcription or None,
            "acoustic_features": voice_features.get("acoustic_features", {}) if voice_features else {},
            "crisis_detected": result.get("crisis_detected", False),
            "tools_used": result.get("tools_used", []),
            "has_voice": True,
            "recommended_technique": result.get("recommended_technique"),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"[API: VOICE] ❌ Voice chat failed: {e}")
        import traceback
        traceback.print_exc()
        logger.exception(
            "Latency VOICE | failed | user=%s session=%s | %.3fs | error=%s",
            user_id,
            session_id or "new",
            latency_seconds(request_start),
            e,
        )
        raise HTTPException(status_code=500, detail=f"Voice processing failed: {str(e)}")

def _audio_upload_suffix(audio_data: str | None, audio_bytes: bytes) -> str:
    """Choose a temp-file suffix that matches a browser audio data URL."""
    header = ""
    if audio_data and "," in audio_data:
        header = audio_data.split(",", 1)[0].lower()

    if "audio/wav" in header or "audio/x-wav" in header:
        return ".wav"
    if "audio/webm" in header:
        return ".webm"
    if "audio/ogg" in header:
        return ".ogg"
    if "audio/mpeg" in header or "audio/mp3" in header:
        return ".mp3"
    if "audio/mp4" in header or "audio/m4a" in header:
        return ".mp4"

    return f".{_detect_audio_format(audio_bytes)}"


def _detect_audio_format(audio_bytes: bytes) -> str:
    """
    Detect audio format from file signature (magic bytes).
    """
    if len(audio_bytes) < 4:
        return "wav"  # default
    
    if audio_bytes[:4] == b'RIFF':
        return "wav"
    elif audio_bytes[:4] == b'\xff\xfb' or audio_bytes[:2] == b'\xff\xfa':
        return "mp3"
    elif audio_bytes[4:8] == b'ftyp':
        return "mp4"
    elif audio_bytes[:4] == b'OggS':
        return "ogg"
    elif b'\x1a\x45\xdf\xa3' in audio_bytes[:100]:
        return "webm"
    else:
        return "webm"  # default


# ============================================
# MAIN
# ============================================

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    
    # Run without reload=True to avoid potential subprocess/Prisma conflicts on Windows
    # The "All connection attempts failed" error is caused by uvicorn's reloader interfering with Prisma binaries
    uvicorn.run(
        "src.mental_health_wellness.api.app:app",
        host="0.0.0.0",
        port=port,
        reload=False  # CHANGED: Disabled reload to fix DB connection reliability
    )
