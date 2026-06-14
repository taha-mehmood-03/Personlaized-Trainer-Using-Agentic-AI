'use server'

import { api, userScopeHeader } from '@/lib/api'
import { UserProfile } from '@/types'

export async function getUserProfile(userId: string): Promise<UserProfile | null> {
    const res = await api.get<UserProfile>(
        `/user/${userId}/profile`,
        { headers: userScopeHeader(userId) }
    )
    if (!res.ok || !res.data) return null
    return res.data
}

export async function saveUserSettings(
    userId: string,
    settings: Record<string, unknown>
): Promise<boolean> {
    const res = await api.post(
        '/user/settings',
        { user_id: userId, settings },
        { headers: userScopeHeader(userId) }
    )
    return res.ok
}

export async function exportUserData(
    userId: string
): Promise<{ ok: boolean; data?: unknown; message?: string }> {
    const res = await api.get<{ status: string; data: unknown }>(
        `/user/${userId}/data-export`,
        { headers: userScopeHeader(userId) }
    )
    return {
        ok: res.ok,
        data: res.data?.data,
        message: res.ok ? 'Data export generated.' : 'Failed to generate data export.',
    }
}

export async function withdrawUserConsent(
    userId: string,
    scopes?: string[],
    reason = 'user_requested'
): Promise<{ ok: boolean; message?: string }> {
    const res = await api.post<{ status: string; scopes: string[] }>(
        `/user/${userId}/consent/withdraw`,
        { scopes, reason },
        { headers: userScopeHeader(userId) }
    )
    return {
        ok: res.ok,
        message: res.ok ? 'Consent withdrawn.' : 'Failed to withdraw consent.',
    }
}

/** Legacy hard-delete — kept for internal admin use. */
export async function deleteUserAccount(userId: string): Promise<boolean> {
    const res = await api.delete(`/user/${userId}`, { headers: userScopeHeader(userId) })
    return res.ok
}

/**
 * GAP-06: GDPR Art. 17 Right to Erasure.
 * Submits a formal erasure request — revokes consent, soft-deletes the user,
 * and creates a DataSubjectRequest audit trail. Use this in the UI instead of deleteUserAccount().
 */
export async function requestAccountErasure(
    userId: string,
    reason = 'user_requested'
): Promise<{ ok: boolean; message?: string }> {
    const res = await api.post<{ status: string; message: string }>(
        '/user/erasure-request',
        { user_id: userId, reason },
        { headers: userScopeHeader(userId) }
    )
    return {
        ok: res.ok,
        message: res.data?.message ?? (res.ok ? 'Erasure request submitted.' : 'Failed to submit erasure request.'),
    }
}
