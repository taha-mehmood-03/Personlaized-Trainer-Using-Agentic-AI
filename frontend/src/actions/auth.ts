'use server'

import { api } from '@/lib/api'
import { User } from '@/types'

// ─── Auth Actions ──────────────────────────────────────────────────────────

export async function ensureUser(userId: string): Promise<boolean> {
    const { ok } = await api.post('/user/ensure', {
        user_id: userId,
        message: '',
    })
    return ok
}

export async function loginUser(email: string, pass: string): Promise<User | null> {
    try {
        const res = await api.post('/auth/login', { email, password: pass })
        const data = res.data as { status: string; user_id: string; name: string; email: string } | undefined

        if (res.ok && data?.status === 'success') {
            return { id: data.user_id, name: data.name || email.split('@')[0], email: data.email || email }
        }
        return null
    } catch (error) {
        console.error('Login API error:', error)
        return null
    }
}

const CONSENT_VERSION = '2026-05-24'
const PRIVACY_NOTICE_VERSION = '2026-05-24'
const TERMS_VERSION = '2026-05-24'

export async function signupUser(
    email: string,
    pass: string,
    name?: string,
    consentAccepted = false
): Promise<User | null> {
    try {
        const res = await api.post('/auth/signup', {
            email,
            password: pass,
            name: name || email.split('@')[0],
            consent_accepted: consentAccepted,
            consent_version: CONSENT_VERSION,
            privacy_notice_version: PRIVACY_NOTICE_VERSION,
            terms_version: TERMS_VERSION,
        })
        const data = res.data as { status: string; user_id: string; name: string; email: string } | undefined

        if (res.ok && data?.status === 'success') {
            return { id: data.user_id, name: data.name || name || email.split('@')[0], email: data.email || email }
        }
        return null
    } catch (error) {
        console.error('Signup API error:', error)
        return null
    }
}
