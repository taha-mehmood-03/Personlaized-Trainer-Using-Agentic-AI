'use server'

import { api } from '@/lib/api'

// ─── Technique Actions ─────────────────────────────────────────────────────

export interface RatingPayload {
    user_id: string
    technique_id: string
    rating: number
    feedback?: string | null
    completed?: boolean
}

export async function submitTechniqueRating(
    payload: RatingPayload
): Promise<{ status: 'success' | 'error'; message?: string }> {
    const { data, ok, error } = await api.post<{ status: string; message?: string }>(
        '/technique/rate',
        payload
    )

    if (!ok) return { status: 'error', message: error ?? 'Request failed' }
    return { status: 'success', message: data?.message }
}
