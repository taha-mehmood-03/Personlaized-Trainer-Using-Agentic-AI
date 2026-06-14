'use server'

import { api, CrisisResource, CrisisResourcesResponse, userScopeHeader } from '@/lib/api'
import { DEFAULT_CRISIS_COUNTRY, PAKISTAN_CRISIS_RESOURCES } from '@/lib/crisisResources'

export interface CrisisInitialData {
    countryCode: string
    resources: CrisisResource
    error: string | null
}

const FALLBACK_RESOURCES: CrisisResource = PAKISTAN_CRISIS_RESOURCES

export async function getCrisisInitialData(userId: string): Promise<CrisisInitialData> {
    try {
        const detected = await api.post<{ country_code?: string }>(
            '/crisis/detect-country',
            { user_data: {} },
            { headers: userScopeHeader(userId) }
        )
        const countryCode = detected.data?.country_code || DEFAULT_CRISIS_COUNTRY

        const resources = await api.post<CrisisResourcesResponse>(
            '/crisis/resources',
            { country_code: countryCode, user_id: userId },
            { headers: userScopeHeader(userId) }
        )

        if (resources.ok && resources.data?.resources) {
            return { countryCode, resources: resources.data.resources, error: null }
        }
    } catch {
        // Fall through to a safe always-available default.
    }

    return {
        countryCode: DEFAULT_CRISIS_COUNTRY,
        resources: FALLBACK_RESOURCES,
        error: 'Unable to load live crisis resources. Showing Pakistan emergency resources.',
    }
}
