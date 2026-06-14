"""
Compliance-oriented safeguards for SentiMind.

These helpers add technical controls that support HIPAA/GDPR alignment:
audit logging, consent history, data-subject request records, pseudonymous
logging, security headers, retention metadata, and strict CORS configuration.
They do not by themselves certify legal compliance.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from fastapi import HTTPException, Request


DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

DEFAULT_CONSENT_VERSION = "2026-05-24"
DEFAULT_PRIVACY_NOTICE_VERSION = "2026-05-24"
DEFAULT_TERMS_VERSION = "2026-05-24"

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")
TOKEN_RE = re.compile(r"\b(?:sk|sk-or-v1|ghp|xoxb|xoxp|AIza)[A-Za-z0-9_\-]{12,}\b")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_secret() -> bytes:
    secret = (
        os.getenv("COMPLIANCE_HASH_SECRET")
        or os.getenv("NEXTAUTH_SECRET")
        or os.getenv("JWT_SECRET")
        or "sentimind-dev-only-change-me"
    )
    return secret.encode("utf-8")


def stable_hash(value: str | None, *, length: int = 16) -> str | None:
    """Return a stable HMAC pseudonym for identifiers/log metadata."""
    if not value:
        return None
    digest = hmac.new(_hash_secret(), str(value).encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:length]


def pseudonymize_user_id(user_id: str | None) -> str:
    digest = stable_hash(user_id, length=12)
    return f"user:{digest}" if digest else "user:unknown"


def redact_text(value: Any, *, max_len: int = 180) -> str:
    """Redact common direct identifiers and secrets from logs/audit metadata."""
    text = "" if value is None else str(value)
    text = EMAIL_RE.sub("[email]", text)
    text = PHONE_RE.sub("[phone]", text)
    text = TOKEN_RE.sub("[secret]", text)
    if len(text) > max_len:
        text = text[:max_len] + "..."
    return text


def parse_allowed_origins() -> list[str]:
    configured = os.getenv("ALLOWED_ORIGINS") or os.getenv("CORS_ALLOWED_ORIGINS")
    if configured:
        origins = [origin.strip() for origin in configured.split(",") if origin.strip()]
    else:
        origins = DEFAULT_ALLOWED_ORIGINS.copy()

    if "*" in origins and os.getenv("SENTIMIND_ALLOW_WILDCARD_CORS", "false").lower() != "true":
        origins = [origin for origin in origins if origin != "*"] or DEFAULT_ALLOWED_ORIGINS.copy()
    return origins


def compliance_mode_enabled() -> bool:
    return os.getenv("SENTIMIND_COMPLIANCE_MODE", "true").lower() in {"1", "true", "yes", "on"}


def enforce_user_scope(request: Request | None, user_id: str | None) -> None:
    """
    Optional hard authorization boundary.

    Enable SENTIMIND_REQUIRE_USER_HEADER=true behind a trusted frontend/proxy.
    The frontend/proxy must send X-SentiMind-User-Id matching the route user_id.
    """
    configured = os.getenv("SENTIMIND_REQUIRE_USER_HEADER")
    if configured is None:
        require_header = (
            os.getenv("SENTIMIND_ENV", "").lower() == "production"
            or os.getenv("ENV", "").lower() == "production"
            or os.getenv("NODE_ENV", "").lower() == "production"
        )
    else:
        require_header = configured.lower() in {"1", "true", "yes", "on"}

    if not require_header:
        return
    if not request or not user_id:
        raise HTTPException(status_code=403, detail="User scope verification required")
    presented = request.headers.get("x-sentimind-user-id")
    if not presented or presented != user_id:
        raise HTTPException(status_code=403, detail="User scope verification failed")


def security_headers_for_path(path: str) -> dict[str, str]:
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "X-Robots-Tag": "noindex, nofollow",
    }
    if path.startswith("/api/"):
        headers["Cache-Control"] = "no-store"
        headers["Pragma"] = "no-cache"
    if os.getenv("SENTIMIND_ENABLE_HSTS", "false").lower() in {"1", "true", "yes", "on"}:
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return headers


def _quote(value: Any) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _nullable(value: Any) -> str:
    return "NULL" if value is None else _quote(value)


def _json(value: dict[str, Any] | list[Any] | None) -> str:
    return _quote(json.dumps(value or {}, ensure_ascii=False, default=str))


async def _execute(prisma, sql: str):
    return await prisma.execute_raw(sql)


async def _query(prisma, sql: str):
    return await prisma.query_raw(sql)


_compliance_schema_ready = False


async def ensure_compliance_schema(prisma) -> None:
    """Create supplemental compliance tables for existing deployments."""
    global _compliance_schema_ready

    if _compliance_schema_ready:
        return

    try:
        await _execute(prisma, "CREATE EXTENSION IF NOT EXISTS pgcrypto")
    except Exception:
        pass

    for sql in [
        'ALTER TABLE "User" ADD COLUMN IF NOT EXISTS "consentVersion" TEXT',
        'ALTER TABLE "User" ADD COLUMN IF NOT EXISTS "privacyNoticeVersion" TEXT',
        'ALTER TABLE "User" ADD COLUMN IF NOT EXISTS "termsVersion" TEXT',
        'ALTER TABLE "User" ADD COLUMN IF NOT EXISTS "processingRegion" TEXT',
        'ALTER TABLE "User" ADD COLUMN IF NOT EXISTS "dataRetentionDays" INTEGER NOT NULL DEFAULT 365',
        'ALTER TABLE "User" ADD COLUMN IF NOT EXISTS "deletedAt" TIMESTAMPTZ',
        'ALTER TABLE "Session" ADD COLUMN IF NOT EXISTS sensitivity TEXT NOT NULL DEFAULT \'SENSITIVE\'',
        'ALTER TABLE "Session" ADD COLUMN IF NOT EXISTS "retentionUntil" TIMESTAMPTZ',
        'ALTER TABLE "Message" ADD COLUMN IF NOT EXISTS sensitivity TEXT NOT NULL DEFAULT \'SENSITIVE\'',
        'ALTER TABLE "Message" ADD COLUMN IF NOT EXISTS "retentionUntil" TIMESTAMPTZ',
        'ALTER TABLE "Message" ADD COLUMN IF NOT EXISTS "piiRedacted" BOOLEAN NOT NULL DEFAULT FALSE',
        'ALTER TABLE "MoodLog" ADD COLUMN IF NOT EXISTS sensitivity TEXT NOT NULL DEFAULT \'SENSITIVE\'',
        'ALTER TABLE "MoodLog" ADD COLUMN IF NOT EXISTS "retentionUntil" TIMESTAMPTZ',
        'ALTER TABLE "CrisisLog" ADD COLUMN IF NOT EXISTS sensitivity TEXT NOT NULL DEFAULT \'PHI\'',
        'ALTER TABLE "CrisisLog" ADD COLUMN IF NOT EXISTS "retentionUntil" TIMESTAMPTZ',
        'ALTER TABLE "SessionSummary" ADD COLUMN IF NOT EXISTS sensitivity TEXT NOT NULL DEFAULT \'SENSITIVE\'',
        'ALTER TABLE "SessionSummary" ADD COLUMN IF NOT EXISTS "retentionUntil" TIMESTAMPTZ',
        'ALTER TABLE "UserFact" ADD COLUMN IF NOT EXISTS sensitivity TEXT NOT NULL DEFAULT \'SENSITIVE\'',
        'ALTER TABLE "UserFact" ADD COLUMN IF NOT EXISTS "legalBasis" TEXT NOT NULL DEFAULT \'CONSENT\'',
        'ALTER TABLE "UserFact" ADD COLUMN IF NOT EXISTS "retentionUntil" TIMESTAMPTZ',
        'ALTER TABLE "ClinicalAssessmentLog" ADD COLUMN IF NOT EXISTS sensitivity TEXT NOT NULL DEFAULT \'PHI\'',
        'ALTER TABLE "ClinicalAssessmentLog" ADD COLUMN IF NOT EXISTS "retentionUntil" TIMESTAMPTZ',
    ]:
        try:
            await _execute(prisma, sql)
        except Exception:
            # Some deployments may not have every optional table yet.
            continue

    await _execute(
        prisma,
        """
        CREATE TABLE IF NOT EXISTS "AuditEvent" (
            id TEXT PRIMARY KEY,
            "eventType" TEXT NOT NULL,
            "actorUserIdHash" TEXT,
            "subjectUserIdHash" TEXT,
            "resourceType" TEXT,
            "resourceIdHash" TEXT,
            action TEXT NOT NULL,
            purpose TEXT,
            "legalBasis" TEXT,
            status TEXT NOT NULL DEFAULT 'SUCCESS',
            "ipHash" TEXT,
            "userAgentHash" TEXT,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            "createdAt" TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
    )
    await _execute(
        prisma,
        """
        CREATE INDEX IF NOT EXISTS "AuditEvent_subject_idx"
        ON "AuditEvent" ("subjectUserIdHash", "createdAt")
        """,
    )
    await _execute(
        prisma,
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'ConsentScope') THEN
                ALTER TYPE "ConsentScope" ADD VALUE IF NOT EXISTS 'CRISIS_LOCATION';
                ALTER TYPE "ConsentScope" ADD VALUE IF NOT EXISTS 'EMERGENCY_CONTACT_ALERTS';
                ALTER TYPE "ConsentScope" ADD VALUE IF NOT EXISTS 'VOICE_ANALYSIS';
            END IF;
        END $$;
        """,
    )
    await _execute(
        prisma,
        """
        CREATE TABLE IF NOT EXISTS "ConsentRecord" (
            id TEXT PRIMARY KEY,
            "userId" TEXT NOT NULL,
            "userIdHash" TEXT NOT NULL,
            scope TEXT NOT NULL,
            granted BOOLEAN NOT NULL,
            "legalBasis" TEXT NOT NULL DEFAULT 'CONSENT',
            "policyVersion" TEXT NOT NULL,
            "noticeVersion" TEXT NOT NULL,
            "termsVersion" TEXT NOT NULL,
            locale TEXT,
            "processingRegion" TEXT,
            "ipHash" TEXT,
            "userAgentHash" TEXT,
            "recordedAt" TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
    )
    await _execute(
        prisma,
        """
        CREATE INDEX IF NOT EXISTS "ConsentRecord_user_idx"
        ON "ConsentRecord" ("userId", "recordedAt")
        """,
    )
    await _execute(
        prisma,
        """
        CREATE TABLE IF NOT EXISTS "DataSubjectRequest" (
            id TEXT PRIMARY KEY,
            "userId" TEXT NOT NULL,
            "userIdHash" TEXT NOT NULL,
            type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'RECEIVED',
            "requestedAt" TIMESTAMPTZ NOT NULL DEFAULT now(),
            "completedAt" TIMESTAMPTZ,
            "requestMetadata" JSONB NOT NULL DEFAULT '{}'::jsonb,
            "resolutionNotes" TEXT
        )
        """,
    )
    await _execute(
        prisma,
        """
        CREATE INDEX IF NOT EXISTS "DataSubjectRequest_user_idx"
        ON "DataSubjectRequest" ("userId", "requestedAt")
        """,
    )
    await _execute(
        prisma,
        """
        CREATE TABLE IF NOT EXISTS "DataRetentionPolicy" (
            id TEXT PRIMARY KEY,
            "dataClass" TEXT NOT NULL,
            "resourceType" TEXT NOT NULL,
            "retentionDays" INTEGER NOT NULL,
            "legalBasis" TEXT NOT NULL,
            description TEXT NOT NULL,
            "isActive" BOOLEAN NOT NULL DEFAULT TRUE,
            "createdAt" TIMESTAMPTZ NOT NULL DEFAULT now(),
            "updatedAt" TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
    )
    await _execute(
        prisma,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS "DataRetentionPolicy_class_resource_unique"
        ON "DataRetentionPolicy" ("dataClass", "resourceType")
        """,
    )
    await _execute(
        prisma,
        """
        INSERT INTO "DataRetentionPolicy"
            (id, "dataClass", "resourceType", "retentionDays", "legalBasis", description, "createdAt", "updatedAt")
        VALUES
            ('retention-message-sensitive', 'SENSITIVE', 'Message', 365, 'CONSENT', 'User and assistant chat messages retained for continuity, then eligible for deletion.', now(), now()),
            ('retention-mood-sensitive', 'SENSITIVE', 'MoodLog', 365, 'CONSENT', 'Mood analytics retained for trend analysis, then eligible for deletion.', now(), now()),
            ('retention-memory-sensitive', 'SENSITIVE', 'UserFact', 365, 'CONSENT', 'Explicit memory facts retained for personalization, then eligible for deletion.', now(), now()),
            ('retention-crisis-phi', 'PHI', 'CrisisLog', 2555, 'VITAL_INTERESTS', 'Crisis safety logs retained for safety documentation.', now(), now()),
            ('retention-clinical-phi', 'PHI', 'ClinicalAssessmentLog', 2555, 'HEALTH_CARE', 'Clinical severity assessments retained as PHI safety records.', now(), now())
        ON CONFLICT ("dataClass", "resourceType")
        DO NOTHING
        """,
    )
    _compliance_schema_ready = True


def _request_hashes(request: Request | None) -> tuple[str | None, str | None]:
    if not request:
        return None, None
    client_host = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return stable_hash(client_host), stable_hash(user_agent)


async def record_audit_event(
    prisma,
    *,
    event_type: str,
    action: str,
    subject_user_id: str | None = None,
    actor_user_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    purpose: str | None = None,
    legal_basis: str | None = None,
    status: str = "SUCCESS",
    metadata: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    if not compliance_mode_enabled():
        return
    try:
        await ensure_compliance_schema(prisma)
        ip_hash, ua_hash = _request_hashes(request)
        safe_metadata = {
            str(k): redact_text(v, max_len=300)
            for k, v in (metadata or {}).items()
        }
        await _execute(
            prisma,
            f"""
            INSERT INTO "AuditEvent"
                (id, "eventType", "actorUserIdHash", "subjectUserIdHash", "resourceType",
                 "resourceIdHash", action, purpose, "legalBasis", status,
                 "ipHash", "userAgentHash", metadata)
            VALUES (
                {_quote(str(uuid.uuid4()))},
                {_quote(event_type)},
                {_nullable(stable_hash(actor_user_id))},
                {_nullable(stable_hash(subject_user_id))},
                {_nullable(resource_type)},
                {_nullable(stable_hash(resource_id))},
                {_quote(action)},
                {_nullable(purpose)},
                {_nullable(legal_basis)},
                {_quote(status)},
                {_nullable(ip_hash)},
                {_nullable(ua_hash)},
                {_json(safe_metadata)}::jsonb
            )
            """,
        )
    except Exception:
        # Audit writes must not break safety/chat response paths.
        return


async def record_consent_records(
    prisma,
    *,
    user_id: str,
    scopes: Iterable[str],
    granted: bool,
    legal_basis: str,
    policy_version: str,
    notice_version: str,
    terms_version: str,
    locale: str | None,
    processing_region: str | None,
    request: Request | None = None,
) -> None:
    await ensure_compliance_schema(prisma)
    ip_hash, ua_hash = _request_hashes(request)
    for scope in scopes:
        await _execute(
            prisma,
            f"""
            INSERT INTO "ConsentRecord"
                (id, "userId", "userIdHash", scope, granted, "legalBasis", "policyVersion",
                 "noticeVersion", "termsVersion", locale, "processingRegion",
                 "ipHash", "userAgentHash")
            VALUES (
                {_quote(str(uuid.uuid4()))},
                {_quote(user_id)},
                {_quote(stable_hash(user_id))},
                {_quote(scope)},
                {'TRUE' if granted else 'FALSE'},
                {_quote(legal_basis)},
                {_quote(policy_version)},
                {_quote(notice_version)},
                {_quote(terms_version)},
                {_nullable(locale)},
                {_nullable(processing_region)},
                {_nullable(ip_hash)},
                {_nullable(ua_hash)}
            )
            """,
        )


async def get_effective_consent_states(
    prisma,
    *,
    user_id: str,
    scopes: Iterable[str],
) -> dict[str, bool | None]:
    """
    Return the latest explicit consent state for each requested scope.

    The result uses None when no ConsentRecord exists for a scope so callers can
    safely fall back to legacy UserPreference flags for existing deployments.
    """
    normalized_scopes: list[str] = []
    for scope in scopes:
        normalized = str(scope or "").strip().upper()
        if normalized and normalized not in normalized_scopes:
            normalized_scopes.append(normalized)

    if not user_id or not normalized_scopes:
        return {}

    states: dict[str, bool | None] = {scope: None for scope in normalized_scopes}
    try:
        await ensure_compliance_schema(prisma)
        quoted_scopes = ", ".join(_quote(scope) for scope in normalized_scopes)
        rows = await _query(
            prisma,
            f"""
            SELECT DISTINCT ON (scope) scope, granted, "recordedAt"
            FROM "ConsentRecord"
            WHERE "userId" = {_quote(user_id)}
              AND scope IN ({quoted_scopes})
            ORDER BY scope, "recordedAt" DESC
            """,
        )
        for row in rows or []:
            data = dict(row)
            scope = str(data.get("scope") or "").upper()
            if scope in states:
                states[scope] = bool(data.get("granted"))
    except Exception:
        return states

    return states


async def effective_scoped_consent(
    prisma,
    *,
    user_id: str,
    scope: str,
    fallback: bool = False,
) -> bool:
    """Return latest ConsentRecord state, falling back to a legacy flag."""
    states = await get_effective_consent_states(prisma, user_id=user_id, scopes=[scope])
    latest = states.get(str(scope or "").strip().upper())
    return fallback if latest is None else bool(latest)


async def update_user_privacy_metadata(
    prisma,
    *,
    user_id: str,
    consent_given: bool | None = None,
    consent_date: datetime | None = None,
    consent_version: str | None = None,
    privacy_notice_version: str | None = None,
    terms_version: str | None = None,
    processing_region: str | None = None,
) -> None:
    """Update User privacy fields through SQL for compatibility before Prisma regeneration."""
    await ensure_compliance_schema(prisma)
    assignments = []
    if consent_given is not None:
        assignments.append(f'"consentGiven" = {"TRUE" if consent_given else "FALSE"}')
    if consent_date is not None:
        assignments.append(f'"consentDate" = {_quote(consent_date.isoformat())}::timestamptz')
    if consent_version is not None:
        assignments.append(f'"consentVersion" = {_quote(consent_version)}')
    if privacy_notice_version is not None:
        assignments.append(f'"privacyNoticeVersion" = {_quote(privacy_notice_version)}')
    if terms_version is not None:
        assignments.append(f'"termsVersion" = {_quote(terms_version)}')
    if processing_region is not None:
        assignments.append(f'"processingRegion" = {_quote(processing_region)}')
    if not assignments:
        return
    assignments.append('"updatedAt" = now()')
    await _execute(
        prisma,
        f"""
        UPDATE "User"
        SET {", ".join(assignments)}
        WHERE id = {_quote(user_id)}
        """,
    )


async def create_data_subject_request(
    prisma,
    *,
    user_id: str,
    request_type: str,
    status: str,
    metadata: dict[str, Any] | None = None,
    resolution_notes: str | None = None,
) -> None:
    await ensure_compliance_schema(prisma)
    completed = "now()" if status.upper() in {"COMPLETED", "REJECTED"} else "NULL"
    await _execute(
        prisma,
        f"""
        INSERT INTO "DataSubjectRequest"
            (id, "userId", "userIdHash", type, status, "completedAt", "requestMetadata", "resolutionNotes")
        VALUES (
            {_quote(str(uuid.uuid4()))},
            {_quote(user_id)},
            {_quote(stable_hash(user_id))},
            {_quote(request_type)},
            {_quote(status)},
            {completed},
            {_json(metadata or {})}::jsonb,
            {_nullable(resolution_notes)}
        )
        """,
    )


async def fetch_compliance_records(prisma, *, user_id: str) -> dict[str, Any]:
    """Fetch supplemental consent/request records for GDPR access export."""
    try:
        await ensure_compliance_schema(prisma)
        user_hash = stable_hash(user_id)
        consent_rows = await _query(
            prisma,
            f"""
            SELECT scope, granted, "legalBasis", "policyVersion", "noticeVersion",
                   "termsVersion", locale, "processingRegion", "recordedAt"
            FROM "ConsentRecord"
            WHERE "userId" = {_quote(user_id)}
            ORDER BY "recordedAt" DESC
            """,
        )
        dsr_rows = await _query(
            prisma,
            f"""
            SELECT type, status, "requestedAt", "completedAt", "requestMetadata", "resolutionNotes"
            FROM "DataSubjectRequest"
            WHERE "userId" = {_quote(user_id)}
            ORDER BY "requestedAt" DESC
            """,
        )
        audit_rows = await _query(
            prisma,
            f"""
            SELECT "eventType", "resourceType", action, purpose, "legalBasis", status, "createdAt"
            FROM "AuditEvent"
            WHERE "subjectUserIdHash" = {_quote(user_hash)}
            ORDER BY "createdAt" DESC
            LIMIT 200
            """,
        )
        return {
            "consent_history": [dict(row) for row in consent_rows or []],
            "data_subject_requests": [dict(row) for row in dsr_rows or []],
            "audit_events": [dict(row) for row in audit_rows or []],
        }
    except Exception:
        return {
            "consent_history": [],
            "data_subject_requests": [],
            "audit_events": [],
        }
