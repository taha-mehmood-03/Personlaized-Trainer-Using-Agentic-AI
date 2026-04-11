'use server'

import { Session, Message } from './types'

const API_URL = 'http://localhost:8000/api'

// ─── Generic fetch helper ───────────────────────────────────────────────────
async function apiFetch<T>(
    path: string,
    options?: RequestInit
): Promise<T | null> {
    try {
        const res = await fetch(`${API_URL}${path}`, {
            ...options,
            headers: { 'Content-Type': 'application/json', ...options?.headers },
            cache: 'no-store',
        })
        if (!res.ok) return null
        return res.json() as Promise<T>
    } catch {
        return null
    }
}

// ─── Ensure user exists ─────────────────────────────────────────────────────
export async function ensureUser(userId: string): Promise<boolean> {
    const data = await apiFetch<{ status: string }>('/user/ensure', {
        method: 'POST',
        body: JSON.stringify({ user_id: userId, message: '' }),
    })
    return data !== null
}

// ─── Get all sessions (sidebar list) ───────────────────────────────────────
export async function getSessions(userId: string): Promise<Session[]> {
    const data = await apiFetch<{ sessions: Session[] }>(
        `/user/${userId}/sessions?limit=50`
    )
    return data?.sessions ?? []
}

// ─── Get latest session with messages ──────────────────────────────────────
export async function getLatestSession(
    userId: string
): Promise<{ messages: Message[]; sessionId: string | null }> {
    const data = await apiFetch<{ sessions: Session[] }>(
        `/user/${userId}/sessions?limit=1`
    )

    const lastSession = data?.sessions?.[0]
    if (!lastSession?.messages?.length) return { messages: [], sessionId: null }

    const messages: Message[] = lastSession.messages.map((m) => ({
        role: m.role?.toLowerCase() as 'user' | 'assistant',
        content: m.content,
        emotion: m.emotion,
        sentiment: m.sentiment,
        timestamp: m.timestamp,
        technique: m.technique ?? null,
    }))

    return { messages, sessionId: lastSession.id }
}

// ─── Delete a session ───────────────────────────────────────────────────────
export async function deleteSession(sessionId: string): Promise<boolean> {
    const res = await apiFetch<unknown>(`/session/${sessionId}`, {
        method: 'DELETE',
    })
    return res !== null
}

// ─── Rename a session ───────────────────────────────────────────────────────
export async function renameSession(
    sessionId: string,
    title: string
): Promise<boolean> {
    const res = await apiFetch<unknown>(`/session/${sessionId}/rename`, {
        method: 'PATCH',
        body: JSON.stringify({ title }),
    })
    return res !== null
}

// ─── Submit technique rating ────────────────────────────────────────────────
export async function submitTechniqueRating(payload: {
    user_id: string
    technique_id: string
    rating: number
    feedback?: string | null
    completed?: boolean
}): Promise<{ status: string; message?: string }> {
    const data = await apiFetch<{ status: string; message?: string }>(
        '/technique/rate',
        { method: 'POST', body: JSON.stringify(payload) }
    )
    return data ?? { status: 'error', message: 'Request failed' }
}
