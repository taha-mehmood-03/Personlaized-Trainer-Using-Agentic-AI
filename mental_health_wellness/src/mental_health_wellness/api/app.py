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
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from src.mental_health_wellness.api.rate_limit import limiter

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
    return time.time() - start_time


from src.mental_health_wellness.agent import get_agent
from src.mental_health_wellness.db.client import get_prisma_client, close_prisma_client
from src.mental_health_wellness.db.performance import ensure_performance_indexes
from src.mental_health_wellness.security.compliance import (
    ensure_compliance_schema,
    parse_allowed_origins,
    run_compliance_background_jobs,
    security_headers_for_path,
)


# ── Lifespan ─────────────────────────────────────────────────────────────────

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
        await run_compliance_background_jobs(prisma)
        logger.info("Startup OK   | Compliance background jobs scheduled (breach detection + retention)")
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
        logger.info("Startup      | Seeding technique embeddings into pgvector")
        from src.mental_health_wellness.db.client import get_prisma_client as _get_prisma
        from src.mental_health_wellness.memory import store_technique_embedding

        prisma = await _get_prisma()
        _batch_size = 10
        all_techniques = await prisma.technique.find_many(where={"isActive": True})
        seeded = 0
        for i in range(0, len(all_techniques), _batch_size):
            batch = all_techniques[i:i + _batch_size]
            batch_results = await asyncio.gather(
                *[store_technique_embedding(t) for t in batch],
                return_exceptions=True,
            )
            seeded += sum(1 for r in batch_results if r is True)
        logger.info(
            "Startup OK   | Technique embeddings seeded | total=%d seeded=%d",
            len(all_techniques), seeded,
        )
    except Exception as e:
        logger.warning("Startup WARN | Technique embedding seed failed (non-fatal): %s", e)

    try:
        logger.info("Startup      | Backfilling UserFact + SessionSummary embeddings")
        from src.mental_health_wellness.db.client import get_prisma_client as _get_prisma
        from src.mental_health_wellness.memory import store_fact_embedding, store_session_summary_embedding

        _prisma = await _get_prisma()
        _batch_size = 10

        all_facts = await _prisma.userfact.find_many(take=200)
        if all_facts:
            fact_seeded = 0
            for i in range(0, len(all_facts), _batch_size):
                batch = all_facts[i:i + _batch_size]
                batch_results = await asyncio.gather(
                    *[store_fact_embedding(f.userId, f.id, f.fact, f.category) for f in batch],
                    return_exceptions=True,
                )
                fact_seeded += sum(1 for r in batch_results if r is True)
            logger.info("Startup OK   | UserFact embeddings backfilled | total=%d seeded=%d", len(all_facts), fact_seeded)

        all_summaries = await _prisma.sessionsummary.find_many(take=200)
        if all_summaries:
            summary_seeded = 0
            for i in range(0, len(all_summaries), _batch_size):
                batch = all_summaries[i:i + _batch_size]
                batch_results = await asyncio.gather(
                    *[store_session_summary_embedding(s.userId, s.sessionId, s.id, s.title, s.summary, s.emotion) for s in batch],
                    return_exceptions=True,
                )
                summary_seeded += sum(1 for r in batch_results if r is True)
            logger.info("Startup OK   | SessionSummary embeddings backfilled | total=%d seeded=%d", len(all_summaries), summary_seeded)
    except Exception as e:
        logger.warning("Startup WARN | Embedding backfill failed (non-fatal): %s", e)

    try:
        logger.info("Startup      | Checking Gemini voice analysis")
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


# ── App init ──────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Mental Health Wellness API",
    description="AI mental health support using LangGraph ReAct Agent",
    version="3.0.0",
    lifespan=organized_lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

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


# ── Routers ───────────────────────────────────────────────────────────────────

from src.mental_health_wellness.api.routes import (
    auth,
    chat,
    consent,
    dashboard,
    health,
    sessions,
    users,
    wellness,
)

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(sessions.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(consent.router)
app.include_router(dashboard.router)
app.include_router(wellness.router)

try:
    from src.mental_health_wellness.api.crisis_routes import router as crisis_router
    app.include_router(crisis_router)
    logger.info("Crisis routes registered")
except Exception as e:
    logger.warning("Crisis routes not registered: %s", e)
