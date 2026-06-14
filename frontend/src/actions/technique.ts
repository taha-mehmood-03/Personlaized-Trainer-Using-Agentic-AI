'use server'

import { api, userScopeHeader } from '@/lib/api'

// ─── Technique Actions ─────────────────────────────────────────────────────

export interface RatingPayload {
    user_id: string
    technique_id: string
    rating?: number | null
    feedback?: string | null
    completed?: boolean
    session_id?: string | null
}

export async function submitTechniqueRating(
    payload: RatingPayload
): Promise<{ status: 'success' | 'error'; message?: string }> {
    if (!payload.user_id || !payload.technique_id) {
        return {
            status: 'error',
            message: 'Cannot save technique feedback without a user and technique id.',
        }
    }

    const { data, ok, error } = await api.post<{ status: string; message?: string }>(
        '/technique/rate',
        payload,
        { headers: userScopeHeader(payload.user_id) }
    )

    if (!ok) return { status: 'error', message: error ?? 'Request failed' }
    return { status: 'success', message: data?.message }
}
