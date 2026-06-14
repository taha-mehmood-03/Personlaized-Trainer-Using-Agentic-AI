'use server'

import { api, userScopeHeader } from '@/lib/api'
import { Session, Message } from '@/types'
import { cleanAssistantContent, cleanEmotionList, firstEmotionLabel } from '@/lib/chatEmotion'

function normalizeRole(value: unknown): 'user' | 'assistant' {
    const text = typeof value === 'string' ? value.trim().split('.').pop()?.toLowerCase() : null
    return text === 'user' ? 'user' : 'assistant'
}

function normalizeMessage(raw: Message & Record<string, unknown>): Message {
    const role = normalizeRole(raw.role)
    const moodAnalysis = (raw.mood_analysis ?? raw.moodAnalysis ?? {}) as Record<string, unknown>

    return {
        ...raw,
        role,
        content: cleanAssistantContent(raw.content, role),
        timestamp: (raw.timestamp as string | undefined) ?? (raw.createdAt as string | undefined),
        emotion: firstEmotionLabel(raw.emotion, raw.fused_emotion, raw.mood, moodAnalysis.emotion) ?? undefined,
        emotionLabel: firstEmotionLabel(raw.emotionLabel, raw.emotion_label, moodAnalysis.emotion_label),
        rawEmotionLabel: firstEmotionLabel(raw.rawEmotionLabel, raw.raw_emotion_label, moodAnalysis.raw_emotion_label),
        primarySubEmotion: firstEmotionLabel(
            raw.primarySubEmotion,
            raw.primary_sub_emotion,
            moodAnalysis.primary_sub_emotion,
            moodAnalysis.primarySubEmotion,
            moodAnalysis.sub_emotion,
            moodAnalysis.subEmotion
        ),
        secondarySubEmotions: cleanEmotionList(
            raw.secondarySubEmotions ?? raw.secondary_sub_emotions ?? moodAnalysis.secondary_sub_emotions
        ),
        detectedSymptoms: cleanEmotionList(raw.detectedSymptoms ?? raw.detected_symptoms ?? moodAnalysis.detected_symptoms),
        detectedBehaviors: cleanEmotionList(raw.detectedBehaviors ?? raw.detected_behaviors ?? moodAnalysis.detected_behaviors),
        detectedContexts: cleanEmotionList(raw.detectedContexts ?? raw.detected_contexts ?? moodAnalysis.detected_contexts),
        emotionScores:
            (raw.emotionScores as Record<string, number> | undefined) ??
            (raw.emotion_scores as Record<string, number> | undefined) ??
            (moodAnalysis.emotion_scores as Record<string, number> | undefined) ??
            {},
        sentiment: firstEmotionLabel(raw.sentiment, raw.moodSummary, moodAnalysis.sentiment) ?? undefined,
    }
}

// ─── Chat Actions ────────────────────────────────────────────────────────────

export async function getSessions(userId: string): Promise<Session[]> {
    const { data, ok } = await api.get<{ sessions: Session[] }>(
        `/user/${userId}/sessions?limit=50`,
        { headers: userScopeHeader(userId) }
    )
    if (!ok || !data?.sessions) return []

    return data.sessions.map((session) => ({
        ...session,
        createdAt:
            ((session as Session & Record<string, unknown>).createdAt as string | undefined) ??
            ((session as Session & Record<string, unknown>).started_at as string | undefined) ??
            new Date().toISOString(),
        updatedAt:
            ((session as Session & Record<string, unknown>).updatedAt as string | undefined) ??
            ((session as Session & Record<string, unknown>).ended_at as string | undefined) ??
            ((session as Session & Record<string, unknown>).started_at as string | undefined) ??
            new Date().toISOString(),
        messages: (session.messages ?? []).map((m) => normalizeMessage(m as Message & Record<string, unknown>)),
    }))
}

export async function getLatestSession(
    userId: string
): Promise<{ messages: Message[]; sessionId: string | null }> {
    const { data, ok } = await api.get<{ sessions: Session[] }>(
        `/user/${userId}/sessions?limit=1&include_messages=true`,
        { headers: userScopeHeader(userId) }
    )

    const lastSession = data?.sessions?.[0]
    if (!ok || !lastSession?.id) {
        return { messages: [], sessionId: null }
    }

    const messages = (lastSession.messages ?? []).map((m) => ({
        ...normalizeMessage(m as Message & Record<string, unknown>),
        technique: m.technique ?? null,
    }))
    return { messages, sessionId: messages.length ? lastSession.id : null }
}

export async function getSessionMessages(
    sessionId: string,
    userId: string
): Promise<Message[]> {
    const { data, ok } = await api.get<{ messages: Message[] }>(
        `/session/${sessionId}/messages`,
        { headers: userScopeHeader(userId) }
    )

    if (!ok || !data?.messages) return []

    return data.messages.map((m) => ({
        ...normalizeMessage(m as Message & Record<string, unknown>),
        technique: m.technique ?? null,
    }))
}

export async function deleteSession(sessionId: string, userId?: string): Promise<boolean> {
    const { ok } = await apiRequestWithOptionalUserScope(`/session/${sessionId}`, 'DELETE', userId)
    return ok
}

export async function renameSession(
    sessionId: string,
    title: string,
    userId?: string
): Promise<boolean> {
    const { ok } = await api.patch(
        `/session/${sessionId}/rename`,
        { title },
        userId ? { headers: userScopeHeader(userId) } : undefined
    )
    return ok
}

async function apiRequestWithOptionalUserScope(path: string, method: 'DELETE', userId?: string) {
    return api.delete(path, userId ? { headers: userScopeHeader(userId) } : undefined)
}
