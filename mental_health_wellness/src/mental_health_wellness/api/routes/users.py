"""User profile, settings, onboarding, deletion, and stats endpoints."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from src.mental_health_wellness.api.helpers import (
    _normalize_phone,
    _read_profile_setting_overrides,
    _update_profile_setting_overrides,
    _PROFILE_CONSENT_SCOPES,
    schedule_audit_event,
)
from src.mental_health_wellness.api.models import (
    EmergencyContactRequest,
    OnboardingRequest,
    UserSettingsRequest,
)
from src.mental_health_wellness.db.client import get_prisma_client
from src.mental_health_wellness.security.compliance import (
    DEFAULT_CONSENT_VERSION,
    DEFAULT_PRIVACY_NOTICE_VERSION,
    DEFAULT_TERMS_VERSION,
    create_data_subject_request,
    enforce_user_scope,
    get_effective_consent_states,
    record_audit_event,
    record_consent_records,
)
from src.mental_health_wellness.services.cache_state import invalidate_user_cache, user_cache_version

import logging

logger = logging.getLogger("sentimind.server")

router = APIRouter()

_USER_PROFILE_CACHE: dict[tuple[str, int], dict[str, Any]] = {}


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
        scopes=list(requested.values()),
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


@router.get("/api/user/{user_id}/profile")
async def get_user_profile(user_id: str, request: Request):
    """Return user profile: name, email, plan, createdAt, and preferences."""
    try:
        enforce_user_scope(request, user_id)
        cache_key = (user_id, user_cache_version(user_id))
        cached = _USER_PROFILE_CACHE.get(cache_key)
        if cached:
            cached_settings = cached.get("settings") if isinstance(cached, dict) else {}
            if {"emergencyContactConsent", "voiceAnalysisConsent"}.issubset(set((cached_settings or {}).keys())):
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
        for stale in [k for k in _USER_PROFILE_CACHE if k[0] == user_id and k != cache_key]:
            _USER_PROFILE_CACHE.pop(stale, None)
        _USER_PROFILE_CACHE[cache_key] = response
        return response

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/user/settings")
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
            key in settings for key in ["sessionAutoSave", "anonymousMode", "voiceAnalysisConsent"]
        )
        if update_data or has_profile_overrides:
            if pref:
                if update_data:
                    await prisma.userpreference.update(
                        where={"userId": request.user_id}, data=update_data
                    )
            else:
                await prisma.userpreference.create(data={"userId": request.user_id, **update_data})

        profile_override_fields = await _update_profile_setting_overrides(prisma, request.user_id, settings)
        consent_fields = await _record_settings_consent_changes(
            prisma, user_id=request.user_id, settings=settings, request=http_request
        )
        changed_fields = sorted(set(update_data.keys()) | set(profile_override_fields) | set(consent_fields))
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


@router.post("/api/user/onboarding")
async def save_onboarding(request: OnboardingRequest, http_request: Request):
    """Persist onboarding selections: initial mood, goals, notifications, emergency contacts."""
    try:
        prisma = await get_prisma_client()
        user_id = request.user_id or "anonymous"
        if user_id != "anonymous":
            enforce_user_scope(http_request, user_id)

        user = await prisma.user.find_unique(where={"id": user_id})
        if not user:
            return {"status": "skipped", "message": "User not found — onboarding data not saved"}

        MOOD_TO_EMOTION = {"great": "JOY", "good": "JOY", "okay": "NEUTRAL", "low": "SADNESS", "awful": "SADNESS"}
        MOOD_TO_INTENSITY = {"great": 0.9, "good": 0.75, "okay": 0.5, "low": 0.3, "awful": 0.1}

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

        for goal in request.goals:
            await prisma.userfact.create(data={"userId": user_id, "fact": f"User wellness goal: {goal}", "category": "goal"})

        contact_payloads = []
        if request.emergency_contact_consent:
            seen_numbers: set[str] = set()
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

        pref = await prisma.userpreference.find_unique(where={"userId": user_id})
        preference_data = {
            "dailyCheckInEnabled": request.notifications_enabled,
            "crisisLocationConsent": bool(request.crisis_location_consent),
            "emergencyContactConsent": bool(request.emergency_contact_consent and contact_payloads),
        }
        if pref:
            await prisma.userpreference.update(where={"userId": user_id}, data=preference_data)
        else:
            await prisma.userpreference.create(data={"userId": user_id, **preference_data})

        await _update_profile_setting_overrides(
            prisma, user_id, {"voiceAnalysisConsent": bool(request.voice_analysis_consent)}
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
        return {"status": "error", "message": str(e)}


@router.delete("/api/user/{user_id}")
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


@router.get("/api/user/{user_id}/stats")
async def get_user_stats(user_id: str):
    """Get user statistics."""
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
            "techniques_used": stats.totalTechniquesUsed,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
