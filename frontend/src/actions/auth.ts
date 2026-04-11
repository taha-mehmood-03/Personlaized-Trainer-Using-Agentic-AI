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

// Real Auth Actions
export async function loginUser(email: string, pass: string): Promise<User | null> {
    try {
        const res = await api.post('/auth/login', {
            email: email,
            password: pass,
        })

        const data = res.data as { status: string; user_id: string; name: string } | undefined

        if (res.ok && data && data.status === 'success') {
            return {
                id: data.user_id,
                name: data.name || email.split('@')[0]
            }
        }
        return null
    } catch (error) {
        console.error("Login API error:", error)
        return null
    }
}

export async function signupUser(email: string, pass: string): Promise<User | null> {
    try {
        const res = await api.post('/auth/signup', {
            email: email,
            password: pass,
        })

        const data = res.data as { status: string; user_id: string; name: string } | undefined

        if (res.ok && data && data.status === 'success') {
            return {
                id: data.user_id,
                name: data.name || email.split('@')[0]
            }
        }
        return null
    } catch (error) {
        console.error("Signup API error:", error)
        return null
    }
}
