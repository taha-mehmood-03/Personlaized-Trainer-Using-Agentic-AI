"""Consent management and GDPR data-subject endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from src.mental_health_wellness.api.helpers import (
    _as_list,
    _update_profile_setting_overrides,
)
from src.mental_health_wellness.api.models import ConsentRequest, ConsentWithdrawRequest
from src.mental_health_wellness.db.client import get_prisma_client
from src.mental_health_wellness.security.compliance import (
    DEFAULT_CONSENT_VERSION,
    DEFAULT_PRIVACY_NOTICE_VERSION,
    DEFAULT_TERMS_VERSION,
    create_data_subject_request,
    enforce_user_scope,
    fetch_compliance_records,
    get_effective_consent_states,
    record_audit_event,
    record_consent_records,
    update_user_privacy_metadata,
)
from src.mental_health_wellness.services.cache_state import invalidate_user_cache

router = APIRouter()


@router.post("/api/user/{user_id}/consent")
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


@router.post("/api/user/{user_id}/consent/withdraw")
async def withdraw_consent(user_id: str, withdrawal: ConsentWithdrawRequest, request: Request):
    """Record consent withdrawal without deleting historical audit data."""
    try:
        enforce_user_scope(request, user_id)
        prisma = await get_prisma_client()

        user = await prisma.user.find_unique(where={"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        scopes = [scope.upper() for scope in (withdrawal.scopes or [
            "WELLNESS_CHAT", "MOOD_ANALYTICS", "PERSONALIZATION", "CRISIS_SAFETY",
        ])]

        await update_user_privacy_metadata(prisma, user_id=user_id, consent_given=False)
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
                await prisma.userpreference.update(where={"userId": user_id}, data=preference_updates)
            else:
                await prisma.userpreference.create(data={"userId": user_id, **preference_updates})
        if "VOICE_ANALYSIS" in scope_set:
            pref = await prisma.userpreference.find_unique(where={"userId": user_id})
            if not pref:
                await prisma.userpreference.create(data={"userId": user_id})
            await _update_profile_setting_overrides(prisma, user_id, {"voiceAnalysisConsent": False})

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


@router.get("/api/user/{user_id}/data-export")
async def export_user_data(user_id: str, request: Request):
    """Export all user data (GDPR Article 15 — Right of Access)."""
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
            },
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

        export: dict[str, Any] = {
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
            "psychological_profile": (
                {
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
                }
                if getattr(user, "psychProfile", None)
                else None
            ),
            "statistics": (
                {
                    "total_sessions": user.statistics.totalSessions,
                    "total_messages": user.statistics.totalMessages,
                    "total_checkins": user.statistics.totalCheckIns,
                    "average_mood_rating": user.statistics.averageMoodRating,
                    "most_common_emotion": str(user.statistics.mostCommonEmotion),
                }
                if user.statistics
                else None
            ),
            "preferences": (
                {
                    "communication_style": user.preference.communicationStyle if user.preference else None,
                    "detail_level": user.preference.detailLevel if user.preference else None,
                    "tone": user.preference.tone if user.preference else None,
                    "language": user.preference.language if user.preference else None,
                    "timezone": user.preference.timezone if user.preference else None,
                    "preferred_categories": user.preference.preferredCategories if user.preference else [],
                    "crisis_location_consent": user.preference.crisisLocationConsent if user.preference else False,
                    "emergency_contact_consent": user.preference.emergencyContactConsent if user.preference else False,
                }
                if user.preference
                else None
            ),
            "compliance": compliance_records,
            "exported_at": datetime.now().isoformat(),
        }
        return {"status": "success", "data": export}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/user/{user_id}/data")
async def delete_user_data(user_id: str, request: Request):
    """Delete all user data (GDPR Article 17 — Right to Erasure)."""
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
        return {"status": "success", "message": "All user data has been permanently deleted", "user_id": user_id}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
