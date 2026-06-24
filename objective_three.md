# Objective 3 — HIPAA & GDPR Compliance (Detailed Implementation)

**Project**: SentiMind — AI-Powered Personalized Mental Health & Wellness Platform
**Student**: Taha Mehmood
**Status**: Fully implemented
**Core module**: `mental_health_wellness/src/mental_health_wellness/security/compliance.py`

This document explains **how** the compliance layer was built and **how it works at runtime** — not just what it covers.

---

## 1. Design Philosophy

Three principles drove the implementation:

1. **Centralized engine, thin routes.** All compliance logic lives in one module (`security/compliance.py`). API routes never re-implement hashing, consent, or audit logic — they call into it. This means one place to audit for correctness.

2. **Fail-safe, never fail-closed on safety.** Compliance writes (audit, consent logging) are wrapped in `try/except` and return silently on error. A failed audit insert must **never** break the chat response or a crisis alert. Safety > bookkeeping.

3. **Pseudonymize by default.** No raw user identifier, IP, or user-agent is ever written into audit/consent logs. Everything identifying is passed through an HMAC-SHA256 hash first. The logs are useful for forensics but cannot, by themselves, re-identify a person.

A global switch `SENTIMIND_COMPLIANCE_MODE` (default `true`) enables the whole layer; `compliance_mode_enabled()` is checked at the top of every write path.

---

## 2. The Compliance Data Model (Prisma schema)

New tables/enums added for compliance (`prisma/schema.prisma`):

**Enums**
- `DataSensitivity`: `PUBLIC | PERSONAL | SENSITIVE | PHI` — every clinical table is tagged (defaults to `SENSITIVE`/`PHI`).
- `LegalBasis`: `CONSENT | CONTRACT | LEGAL_OBLIGATION | VITAL_INTERESTS | PUBLIC_TASK | LEGITIMATE_INTERESTS | HEALTH_CARE` (GDPR Art. 6 bases).
- `ConsentScope` (8 scopes): `WELLNESS_CHAT, MOOD_ANALYTICS, PERSONALIZATION, CRISIS_SAFETY, CRISIS_LOCATION, EMERGENCY_CONTACT_ALERTS, VOICE_ANALYSIS, RESEARCH_EXPORT`.
- `AuditEventType`: `AUTH_LOGIN, AUTH_SIGNUP, DATA_ACCESS, DATA_EXPORT, DATA_ERASURE, CONSENT_GRANTED, CONSENT_WITHDRAWN, …`.

**Tables**
- `ConsentRecord` — one row per scope per grant/withdraw. Stores `userId`, `userIdHash`, `scope`, `granted`, `legalBasis`, `policyVersion`, `noticeVersion`, `termsVersion`, `locale`, `processingRegion`, `ipHash`, `userAgentHash`, `recordedAt`.
- `AuditEvent` — append-only log. Stores `eventType`, `actorUserIdHash`, `subjectUserIdHash`, `resourceType`, `resourceIdHash`, `action`, `purpose`, `legalBasis`, `status`, `ipHash`, `userAgentHash`, `metadata` (JSON), `createdAt`.
- `DataSubjectRequest` — tracks GDPR rights requests: `type` (ACCESS/ERASURE/…), `status`, `requestedAt`, `completedAt`, `requestMetadata`, `resolutionNotes`.
- `DataRetentionPolicy` — declares retention per data class.
- Per-row retention: `Message`, `MoodLog`, `SessionSummary`, `UserFact`, `CrisisLog`, `ClinicalAssessmentLog` each carry a `retentionUntil` timestamp; `Session` carries a `sensitivity` column.

`ensure_compliance_schema()` runs idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` + `CREATE EXTENSION IF NOT EXISTS pgcrypto` so existing deployments self-migrate on first use.

---

## 3. The Pseudonymization Core (the most important piece)

```python
def _hash_secret() -> bytes:
    secret = (os.getenv("COMPLIANCE_HASH_SECRET")
              or os.getenv("NEXTAUTH_SECRET")
              or os.getenv("JWT_SECRET")
              or "sentimind-dev-only-change-me")
    return secret.encode("utf-8")

def stable_hash(value, *, length=16):
    return hmac.new(_hash_secret(), str(value).encode(), hashlib.sha256).hexdigest()[:length]
```

- **HMAC-SHA256 with a server-side secret key.** Same input → same hash (so you can still *correlate* events for one actor), but it is **one-way** — you cannot reverse a hash back to the user id without the secret.
- `pseudonymize_user_id()` → `user:<12-hex>`.
- `redact_text()` strips emails, phone numbers, and token-like secrets from any free-text metadata before it is stored, and truncates to a max length.

**Why it matters (viva point):** This satisfies GDPR Art. 32 (pseudonymization) and HIPAA "minimum necessary" simultaneously — even an attacker who dumps the audit table learns *patterns* but not *identities*.

---

## 4. GDPR — Control-by-Control Implementation

### 4.1 Consent & lawful basis (Art. 6 & 9)
**Endpoint:** `POST /api/user/{user_id}/consent` (`routes/consent.py`).
**Flow at runtime:**
1. `enforce_user_scope()` verifies the caller owns the account.
2. `update_user_privacy_metadata()` stamps the User row with consent date + policy/notice/terms versions + processing region.
3. `record_consent_records()` inserts **one `ConsentRecord` per scope** with the legal basis and hashed IP/UA.
4. `record_audit_event(event_type="CONSENT_GRANTED")` logs the act.

**How consent is enforced elsewhere:** `effective_scoped_consent(prisma, user_id, scope, fallback=...)` is the gate. Example — the crisis handler calls it for `EMERGENCY_CONTACT_ALERTS` before sending *any* WhatsApp alert; location lookup requires `CRISIS_LOCATION`. If consent is absent, that processing path simply does not run. `get_effective_consent_states()` returns `None` for scopes with no record so the system can fall back to legacy `UserPreference` flags (backward compatibility for older accounts).

### 4.2 Right of Access — data export (Art. 15)
**Endpoint:** `GET /api/user/{id}/data` → `fetch_compliance_records()` assembles a structured JSON of all data held: profile, messages, mood logs, technique history, consent records, and prior data-subject requests. Logged as `DATA_EXPORT`.

### 4.3 Right to Erasure (Art. 17)
**Endpoint:** account-deletion handler in `routes/users.py`.
**Flow:** Prisma **cascade deletes** remove all child rows (messages, moods, clinical logs, ratings) when the user is deleted; the **pgvector memory store is purged**; a `DataSubjectRequest` of type ERASURE is created via `create_data_subject_request()` with `completedAt` set; the act is logged as `DATA_ERASURE` with `purpose="data subject erasure request"`.

### 4.4 Records of processing — audit log (Art. 30)
`record_audit_event()` is called from auth, consent, export, and erasure paths. All identities hashed, all metadata redacted (see §3). Append-only; never updated.

### 4.5 Storage limitation — retention (Art. 5(1)(e))
- Each clinical row is written with `retentionUntil` (e.g. 365 days for messages, 7 years for crisis logs).
- `enforce_data_retention()` runs `DELETE ... WHERE retentionUntil < now()` across Message, MoodLog, SessionSummary, UserFact, CrisisLog, ClinicalAssessmentLog, and purges `AuditEvent` older than **2 years** (kept that long for breach detection). Returns `{table: rows_deleted}` for logging.

### 4.6 Data minimization (Art. 5(1)(b)(c))
Minimal schema; `redact_text()` ensures only scrubbed, purpose-limited data reaches logs.

### 4.7 Anonymous Mode (Art. 5)
`anonymousMode` flag skips pgvector writes and session-summary generation — full use without persistent profiling.

---

## 5. HIPAA — Safeguard-by-Safeguard Implementation

### 5.1 Access controls — §164.312(a)(1)
`enforce_user_scope(request, user_id)`: in production (or when `SENTIMIND_REQUIRE_USER_HEADER=true`), the request **must** carry `X-SentiMind-User-Id` matching the route's `user_id`, else **HTTP 403**. Combined with JWT auth and per-user query scoping (every DB query filtered by `userId`), cross-user access is structurally impossible.

### 5.2 Password security — §164.312(d)
bcrypt, work factor 12 (intentionally slow → brute-force resistant).

### 5.3 Encryption — §164.312(a)(2)(iv)
TLS in transit; AES-256 at rest (Supabase); identifiers in logs HMAC-pseudonymized.

### 5.4 Audit controls — §164.312(b)
Same `AuditEvent` engine; clinical tables tagged with `DataSensitivity = PHI/SENSITIVE` so PHI is explicitly marked.

### 5.5 Transmission security — §164.312(e)(1)
`security_headers_for_path()` injects on every response:
`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy: camera=(), microphone=(), geolocation=()`, `X-Robots-Tag: noindex`, plus `Cache-Control: no-store` on `/api/`, and optional HSTS (`SENTIMIND_ENABLE_HSTS`). CORS is whitelisted via `parse_allowed_origins()`; the `*` wildcard is stripped unless explicitly enabled.

### 5.6 Rate limiting — §164.308(a)(3)
slowapi: 120/min default, 60/min chat, 10/min auth.

### 5.7 Breach detection — §164.308(a)(6)
`scan_for_breach_indicators()` runs 4 SQL rules over recent `AuditEvent` rows:

| Rule | Trigger |
|---|---|
| `mass_export` | ≥5 DATA_EXPORT in 60 min (same actor hash) |
| `rapid_access` | ≥50 DATA_ACCESS in 5 min (same actor hash) |
| `brute_force` | ≥15 failed AUTH_LOGIN in 10 min (same IP hash) |
| `bulk_delete` | ≥3 DATA_ERASURE in 30 min (same actor hash) |

Each hit is logged as a `BREACH INDICATOR` warning for review.

---

## 6. Background Automation

`run_compliance_background_jobs(prisma)` is started once at FastAPI lifespan startup. It loops every **6 hours** (`SENTIMIND_COMPLIANCE_JOB_INTERVAL_S`) and runs:
1. `scan_for_breach_indicators()` — anomaly detection
2. `enforce_data_retention()` — expired-row purge

Both are exception-isolated so the loop never dies.

---

## 7. End-to-End Request Flow

```
Incoming API request
  │
  ├─ enforce_user_scope()         → 403 if X-SentiMind-User-Id ≠ route user (prod)
  ├─ rate limit (slowapi)
  ├─ CORS whitelist + security headers injected on response
  │
  ├─ action executes (chat / export / delete / consent / auth)
  │     └─ before any alert/location/voice processing:
  │          effective_scoped_consent(scope) must be granted
  │
  └─ record_audit_event(...)      → AuditEvent row (identities HMAC-hashed, metadata redacted)

Every 6 hours (background):
  scan_for_breach_indicators()    → warn on suspicious patterns
  enforce_data_retention()        → DELETE rows past retentionUntil
```

---

## 8. What to Demonstrate in the Viva

1. **Pseudonymization** — show a `ConsentRecord`/`AuditEvent` row: `userIdHash`, `ipHash` are hashes, not raw values. Explain HMAC-SHA256 one-way + secret key.
2. **Consent gate** — toggle `EMERGENCY_CONTACT_ALERTS` off and show the crisis handler refuses to send an alert.
3. **Erasure** — delete an account, show cascade removal + the `DataSubjectRequest` ERASURE row.
4. **Access** — call `GET /api/user/{id}/data` and show the full JSON export.
5. **Scope enforcement** — call a scoped endpoint with a mismatched `X-SentiMind-User-Id` → 403.
6. **Retention/breach jobs** — show the 6-hour background loop and the 4 breach rules.

---

## 9. File Map

| Concern | File |
|---|---|
| Compliance engine (all functions) | `security/compliance.py` |
| Consent + access + erasure endpoints | `api/routes/consent.py`, `api/routes/users.py` |
| Auth audit events | `api/routes/auth.py` |
| Consent scope mappings | `api/helpers.py` |
| Schema (ConsentRecord, AuditEvent, DataSubjectRequest, DataRetentionPolicy, enums, retention columns) | `prisma/schema.prisma` |
| Consent-aware crisis alerts / location | `nodes/crisis_handler.py`, `api/crisis_routes.py` |
