'use server'

import { api, userScopeHeader } from '@/lib/api'
import { OnboardingData } from '@/types'

export async function saveOnboarding(userId: string, data: OnboardingData): Promise<boolean> {
    const res = await api.post(
        '/user/onboarding',
        {
            user_id: userId,
            initial_mood: data.mood,
            goals: data.goals,
            notifications_enabled: data.notificationsEnabled,
            crisis_location_consent: data.crisisLocationConsent,
            emergency_contact_consent: data.emergencyContactConsent,
            emergency_contacts: data.emergencyContacts,
            // GAP-07: Pass voice analysis consent so backend writes VOICE_ANALYSIS ConsentRecord
            voice_analysis_consent: data.voiceAnalysisConsent,
        },
        { headers: userScopeHeader(userId) }
    )
    return res.ok
}
