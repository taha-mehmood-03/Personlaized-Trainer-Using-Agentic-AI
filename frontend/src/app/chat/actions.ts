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
        if (!res.ok) {
            console.error(`[API] ${options?.method ?? 'GET'} ${path} → ${res.status} ${res.statusText}`)
            return null
        }
        return res.json() as Promise<T>
    } catch (err) {
        console.error(`[API] Network error for ${path}:`, err)
        return null
    }
}

// ─── Normalise a raw session from the backend ───────────────────────────────
// Backend returns snake_case (started_at, ended_at), frontend expects camelCase
function normaliseSession(raw: Record<string, unknown>): Session {
    return {
        id: raw.id as string,
        title: (raw.title as string | null) ?? 'Untitled Chat',
        // started_at is the canonical DB field; fallback to createdAt if already mapped
        createdAt: (raw.started_at as string) ?? (raw.createdAt as string) ?? new Date().toISOString(),
        updatedAt: (raw.ended_at as string) ?? (raw.updatedAt as string) ?? (raw.started_at as string) ?? new Date().toISOString(),
        messages: ((raw.messages as unknown[]) ?? []).map((m: unknown) => {
            const msg = m as Record<string, unknown>
            return {
                role: ((msg.role as string) ?? 'assistant').toLowerCase() as 'user' | 'assistant',
                content: msg.content as string,
                emotion: msg.emotion as string | undefined,
                sentiment: msg.sentiment as string | undefined,
                timestamp: (msg.createdAt as string) ?? (msg.timestamp as string),
                technique: (msg.technique as Message['technique']) ?? null,
            }
        }),
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
    const data = await apiFetch<{ sessions: Record<string, unknown>[] }>(
        `/user/${userId}/sessions?limit=50`
    )
    return (data?.sessions ?? []).map(normaliseSession)
}

// ─── Get latest session with messages ──────────────────────────────────────
export async function getLatestSession(
    userId: string
): Promise<{ messages: Message[]; sessionId: string | null }> {
    const data = await apiFetch<{ sessions: Record<string, unknown>[] }>(
        `/user/${userId}/sessions?limit=1`
    )

    const rawSession = data?.sessions?.[0]
    if (!rawSession) return { messages: [], sessionId: null }

    const session = normaliseSession(rawSession)
    if (!session.messages.length) return { messages: [], sessionId: null }

    return { messages: session.messages, sessionId: session.id }
}

// ─── Delete a session ───────────────────────────────────────────────────────
export async function deleteSession(sessionId: string): Promise<boolean> {
    const res = await apiFetch<{ status: string }>(`/session/${sessionId}`, {
        method: 'DELETE',
    })
    return res?.status === 'success'
}

// ─── Rename a session ───────────────────────────────────────────────────────
export async function renameSession(
    sessionId: string,
    title: string
): Promise<boolean> {
    const res = await apiFetch<{ status: string }>(`/session/${sessionId}/rename`, {
        method: 'PATCH',
        body: JSON.stringify({ title }),
    })
    return res?.status === 'success'
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
