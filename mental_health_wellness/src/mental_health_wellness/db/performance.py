"""
Database performance helpers.

These supplemental indexes match the filter + sort patterns used by the
FastAPI read endpoints and analytics nodes. They are created idempotently at
startup so existing local/Supabase databases get the same query shape benefits
without requiring a manual migration first.
"""

from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger("sentimind.db.performance")
_performance_indexes_ready = False


async def ensure_performance_indexes(prisma: Any) -> None:
    """Create read-path indexes used by dashboard, chat history, and exports."""
    global _performance_indexes_ready

    if _performance_indexes_ready:
        return

    indexes = [
        'CREATE INDEX IF NOT EXISTS "Session_user_started_idx" ON "Session" ("userId", "startedAt" DESC)',
        'CREATE INDEX IF NOT EXISTS "Message_session_created_idx" ON "Message" ("sessionId", "createdAt" ASC)',
        'CREATE INDEX IF NOT EXISTS "MoodLog_user_created_idx" ON "MoodLog" ("userId", "createdAt" DESC)',
        'CREATE INDEX IF NOT EXISTS "EmotionSnapshot_user_created_idx" ON "EmotionSnapshot" ("userId", "createdAt" DESC)',
        'CREATE INDEX IF NOT EXISTS "EmotionSnapshot_session_created_idx" ON "EmotionSnapshot" ("sessionId", "createdAt" DESC)',
        'CREATE INDEX IF NOT EXISTS "SessionSummary_user_created_idx" ON "SessionSummary" ("userId", "createdAt" DESC)',
        'CREATE INDEX IF NOT EXISTS "UserFact_user_created_idx" ON "UserFact" ("userId", "createdAt" DESC)',
        'CREATE INDEX IF NOT EXISTS "UserTechniqueRating_user_used_idx" ON "UserTechniqueRating" ("userId", "usedAt" DESC)',
        'CREATE INDEX IF NOT EXISTS "TechniqueOutcome_session_created_idx" ON "TechniqueOutcome" ("sessionId", "createdAt" DESC)',
        'CREATE INDEX IF NOT EXISTS "EmergencyContact_user_active_idx" ON "EmergencyContact" ("userId", "active")',
        'CREATE INDEX IF NOT EXISTS "CrisisLog_user_created_idx" ON "CrisisLog" ("userId", "createdAt" DESC)',
        'CREATE INDEX IF NOT EXISTS "ClinicalAssessmentLog_user_assessed_idx" ON "ClinicalAssessmentLog" ("userId", "assessedAt" DESC)',
        'CREATE INDEX IF NOT EXISTS "ConsentRecord_user_recorded_idx" ON "ConsentRecord" ("userId", "recordedAt" DESC)',
        'CREATE INDEX IF NOT EXISTS "AuditEvent_subject_created_idx" ON "AuditEvent" ("subjectUserIdHash", "createdAt" DESC)',
        'CREATE INDEX IF NOT EXISTS "Technique_active_rating_idx" ON "Technique" ("isActive", "avgRating" DESC)',
        'CREATE INDEX IF NOT EXISTS "Technique_target_emotions_gin_idx" ON "Technique" USING GIN ("targetEmotions")',
    ]

    created = 0
    for sql in indexes:
        try:
            await prisma.execute_raw(sql)
            created += 1
        except Exception as err:
            logger.debug("Performance index skipped: %s", err)

    _performance_indexes_ready = True
    logger.info("Performance indexes ready | checked=%s", created)
