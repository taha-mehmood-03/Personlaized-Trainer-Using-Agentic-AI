'use server'

import { api } from '@/lib/api'
import { Session, Message } from '@/types'

// ─── Chat Actions ────────────────────────────────────────────────────────────

export async function getSessions(userId: string): Promise<Session[]> {
    const { data, ok } = await api.get<{ sessions: Session[] }>(
        `/user/${userId}/sessions?limit=50`
    )
    if (!ok || !data?.sessions) return []

    // Normalize message roles from API uppercase ("USER"/"ASSISTANT") to lowercase
    // so that MessageBubble's `role === 'user'` check works correctly
    return data.sessions.map((session) => ({
        ...session,
        messages: (session.messages ?? []).map((m) => ({
            ...m,
            role: (m.role as string)?.toLowerCase() as 'user' | 'assistant',
        })),
    }))
}

export async function getLatestSession(
    userId: string
): Promise<{ messages: Message[]; sessionId: string | null }> {
    const { data, ok } = await api.get<{ sessions: Session[] }>(
        `/user/${userId}/sessions?limit=1`
    )

    const lastSession = data?.sessions?.[0]
    if (!ok || !lastSession?.messages?.length) {
        return { messages: [], sessionId: null }
    }

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

export async function deleteSession(sessionId: string): Promise<boolean> {
    const { ok } = await api.delete(`/session/${sessionId}`)
    return ok
}

export async function renameSession(
    sessionId: string,
    title: string
): Promise<boolean> {
    const { ok } = await api.patch(`/session/${sessionId}/rename`, { title })
    return ok
}
