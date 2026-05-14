'use server'

import { api } from '@/lib/api'
import {
    DashboardStats,
    EmotionType,
    MoodDataPoint,
    EmotionSlice,
    TopTechniqueEntry,
    SessionSummary,
    PsychologicalProfile,
} from '@/types'

// ─── Dashboard Actions ──────────────────────────────────────────────────────

interface RawDashboardResponse {
    total_sessions?: number
    sessions_this_week?: number
    avg_mood?: number
    streak?: number
    top_emotion?: string
    mood_trend?: 'up' | 'down' | 'stable'
    techniques_tried?: number
    mood_timeline?: Array<{ date: string; score: number; emotion: string }>
    emotion_distribution?: Array<{ emotion: string; count: number; percentage: number }>
    top_techniques?: Array<{ name: string; category: string; usage_count: number }>
    recent_sessions?: Array<{
        id: string
        title: string
        date: string
        dominant_emotion: string
        duration_minutes: number
        technique_used?: string
    }>
    psychological_profile?: {
        coping_style: string
        resilience: number
        anxiety_baseline: string
        ai_insight: string
    }
}

export async function getUserStats(userId: string): Promise<DashboardStats | null> {
    const res = await api.get<RawDashboardResponse>(`/dashboard/stats?user_id=${userId}`)
    if (!res.ok || !res.data) return null

    const d = res.data
    return {
        totalSessions: d.total_sessions ?? 0,
        sessionsThisWeek: d.sessions_this_week ?? 0,
        avgMood: d.avg_mood ?? 0,
        streak: d.streak ?? 0,
        topEmotion: (d.top_emotion ?? 'neutral') as EmotionType,
        moodTrend: d.mood_trend ?? 'stable',
        techniquesTried: d.techniques_tried ?? 0,
        moodTimeline: (d.mood_timeline ?? []).map((p) => ({
            date: p.date,
            score: p.score,
            emotion: p.emotion as EmotionType,
        })) satisfies MoodDataPoint[],
        emotionDistribution: (d.emotion_distribution ?? []).map((e) => ({
            emotion: e.emotion as EmotionType,
            count: e.count,
            percentage: e.percentage,
        })) satisfies EmotionSlice[],
        topTechniques: (d.top_techniques ?? []).map((t) => ({
            name: t.name,
            category: t.category,
            usageCount: t.usage_count,
        })) satisfies TopTechniqueEntry[],
        recentSessions: (d.recent_sessions ?? []).map((s) => ({
            id: s.id,
            title: s.title,
            date: s.date,
            dominantEmotion: s.dominant_emotion as EmotionType,
            durationMinutes: s.duration_minutes,
            techniqueUsed: s.technique_used,
        })) satisfies SessionSummary[],
        psychologicalProfile: {
            copingStyle: (d.psychological_profile?.coping_style ?? 'Active') as PsychologicalProfile['copingStyle'],
            resilience: d.psychological_profile?.resilience ?? 0,
            anxietyBaseline: (d.psychological_profile?.anxiety_baseline ?? 'Moderate') as PsychologicalProfile['anxietyBaseline'],
            aiInsight: d.psychological_profile?.ai_insight ?? '',
        },
    }
}

export async function saveUserSettings(
    userId: string,
    settings: Record<string, unknown>
): Promise<boolean> {
    const res = await api.post('/user/settings', { user_id: userId, settings })
    return res.ok
}

export async function deleteUserAccount(userId: string): Promise<boolean> {
    const res = await api.delete(`/user/${userId}`)
    return res.ok
}

// ─── User Profile ───────────────────────────────────────────────────────────

interface RawProfileResponse {
    id: string
    name: string
    email: string
    created_at?: string
    settings: {
        dailyReminderEnabled: boolean
        weeklyEmailEnabled: boolean
        sessionAutoSave: boolean
        anonymousMode: boolean
        shareLocationInCrisis: boolean
        theme: 'light' | 'dark' | 'system'
    }
}

export async function getUserProfile(userId: string): Promise<RawProfileResponse | null> {
    const res = await api.get<RawProfileResponse>(`/user/${userId}/profile`)
    if (!res.ok || !res.data) return null
    return res.data
}
