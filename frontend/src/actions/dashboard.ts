'use server'

import { api, userScopeHeader } from '@/lib/api'
import {
    DashboardDataQuality,
    DashboardImprovementAnalysis,
    DashboardLongTermOutcomes,
    DashboardSignalSlice,
    DashboardStats,
    DashboardSuggestion,
    DashboardTechniqueOutcome,
    EmotionSlice,
    EmotionType,
    MoodDataPoint,
    PsychologicalProfile,
    SessionSummary,
    SubEmotionSlice,
    TopTechniqueEntry,
} from '@/types'

const EMOTIONS: EmotionType[] = [
    'joy',
    'sadness',
    'anger',
    'fear',
    'disgust',
    'surprise',
    'neutral',
    'anxiety',
    'guilt',
]

interface RawDashboardResponse {
    success?: boolean
    generated_at?: string | null
    window_days?: number
    overview?: {
        total_sessions?: number
        total_messages?: number
        total_checkins?: number
        current_checkin_streak?: number
        longest_checkin_streak?: number
        average_mood_rating?: number
        most_common_emotion?: string
        most_common_sub_emotion?: string | null
        last_session_at?: string | null
        last_checkin_at?: string | null
    }
    mood?: {
        average_score?: number
        trend?: { label?: string; delta?: number }
        volatility?: number
        distribution?: Record<string, number>
        sub_emotion_distribution?: Record<string, number>
        secondary_emotion_distribution?: Record<string, number>
        all_sub_emotion_distribution?: Record<string, number>
        symptom_distribution?: Record<string, number>
        behavior_distribution?: Record<string, number>
        context_distribution?: Record<string, number>
        emotion_baselines?: Record<string, number>
        top_sub_emotions?: Array<{ sub_emotion?: string; count?: number }>
        top_secondary_emotions?: Array<{ emotion?: string; count?: number; percentage?: number }>
        top_symptoms?: Array<{ symptom?: string; count?: number; percentage?: number }>
        top_behaviors?: Array<{ behavior?: string; count?: number; percentage?: number }>
        top_contexts?: Array<{ context?: string; count?: number; percentage?: number }>
        timeline?: Array<{
            created_at?: string | null
            emotion?: string
            primary_sub_emotion?: string | null
            secondary_sub_emotions?: string[]
            detected_symptoms?: string[]
            detected_behaviors?: string[]
            detected_contexts?: string[]
            sentiment?: string
            intensity?: number
            score?: number
            context?: string | null
        }>
        snapshots?: Array<{
            created_at?: string | null
            emotion?: string
            primary_sub_emotion?: string | null
            secondary_sub_emotions?: string[]
            detected_symptoms?: string[]
            detected_behaviors?: string[]
            detected_contexts?: string[]
            intensity?: number
            sentiment?: string
        }>
    }
    sessions?: {
        recent?: Array<{
            id?: string | null
            title?: string | null
            started_at?: string | null
            ended_at?: string | null
            duration_minutes?: number
            message_count?: number
            dominant_emotion?: string | null
            dominant_sub_emotion?: string | null
            secondary_sub_emotions?: string[]
            detected_symptoms?: string[]
            detected_behaviors?: string[]
            detected_contexts?: string[]
            average_score?: number
            trend?: { label?: string; delta?: number }
            summary?: string | null
            techniques?: string[]
            outcome?: string | null
        }>
        /** Per-session average score series (oldest → newest, already 0-100 scale) */
        score_trajectory?: Array<{
            session_id?: string | null
            title?: string
            started_at?: string | null
            average_score?: number
            dominant_emotion?: string
            outcome?: string | null
        }>
    }
    techniques?: {
        total_used?: number
        average_rating?: number
        most_used_technique_id?: string | null
        preferred_categories?: string[]
        adherence_rate?: number
        mean_effectiveness?: number
        /** Composite-ranked techniques from backend (usage × effectiveness) */
        ranked?: Array<{
            name?: string
            category?: string
            usageCount?: number
            meanEffectiveness?: number | null
            compositeScore?: number
        }>
        ratings?: Array<{
            used_at?: string | null
            technique_id?: string | null
            technique?: { name?: string; category?: string | null }
            rating?: number
            completed?: boolean
            feedback?: string | null
        }>
        outcomes?: Array<{
            created_at?: string | null
            technique_id?: string | null
            technique?: { name?: string; category?: string | null }
            effectiveness?: number
            intensity_before?: number
            intensity_after?: number
            sub_emotion_before?: string | null
            sub_emotion_after?: string | null
            symptoms_before?: string[]
            symptoms_after?: string[]
            behaviors_before?: string[]
            behaviors_after?: string[]
        }>
    }
    personalization?: {
        profile?: {
            coping_style?: string
            technique_acceptance_rate?: number
            reflection_depth?: number
            anxiety_baseline?: number
            distress_baseline?: number
            emotion_baselines?: Record<string, number>
            resilience_score?: number
            dominant_emotion?: string
            emotional_triggers?: string[]
            motivation_type?: string
            social_dependency?: number
            top_distortions?: string[]
            top_primary_sub_emotions?: string[]
            top_secondary_emotions?: string[]
            top_symptoms?: string[]
            top_behaviors?: string[]
            top_contexts?: string[]
        }
        session_summaries?: Array<{
            created_at?: string | null
            session_id?: string
            title?: string | null
            summary?: string | null
            emotion?: string | null
            primary_sub_emotion?: string | null
            techniques?: string[]
            outcome?: string | null
        }>
    }
    long_term_outcomes?: {
        mood_trend?: { label?: string; delta?: number }
        average_mood_score?: number
        emotional_volatility?: number
        technique_effectiveness?: number
        technique_adherence_rate?: number
        resilience_score?: number
        distress_baseline?: number
        intervention_readiness?: number
        improvement_analysis?: {
            status?: 'improving' | 'declining' | 'stable' | 'insufficient_data'
            summary?: string
            score_delta?: number
            intensity_delta?: number
            early_average_score?: number
            recent_average_score?: number
            early_average_intensity?: number
            recent_average_intensity?: number
            contributing_factors?: string[]
            blockers?: string[]
            symptoms_reduced?: Array<{ name?: string; delta?: number; before?: number; after?: number }>
            symptoms_increased?: Array<{ name?: string; delta?: number; before?: number; after?: number }>
            evidence?: string[]
            composite_score?: number
            session_outcome_stats?: { positive?: number; neutral?: number; negative?: number; total?: number }
        }
        within_session_improvement?: {
            avg_intensity_delta?: number
            sessions_measured?: number
            label?: 'relieving' | 'neutral' | 'worsening' | 'insufficient_data'
            summary?: string
        }
        composite_score?: number
        session_outcome_stats?: { positive?: number; neutral?: number; negative?: number; total?: number }
    }
    suggestions?: DashboardSuggestion[]
    data_quality?: {
        mood_logs?: number
        emotion_snapshots?: number
        sessions?: number
        ratings?: number
        warnings?: string[]
    }
}

type RawDashboardProfile = NonNullable<RawDashboardResponse['personalization']>['profile']

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value))

function toEmotion(value?: string | null): EmotionType {
    const lower = String(value ?? 'neutral').toLowerCase() as EmotionType
    return EMOTIONS.includes(lower) ? lower : 'neutral'
}

function scoreToPercent(score?: number): number {
    return Math.round(clamp(Number(score ?? 5), 0, 10) * 10)
}

function ratioToPercent(value?: number): number {
    return Math.round(clamp(Number(value ?? 0), 0, 1) * 100)
}

function dateLabel(value?: string | null): string {
    if (!value) return 'No date'
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return 'No date'
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function trendDirection(label?: string): DashboardStats['moodTrend'] {
    if (label === 'improving') return 'up'
    if (label === 'declining') return 'down'
    if (label === 'insufficient_data') return 'insufficient_data'
    return 'stable'
}

function anxietyLabel(value?: number): PsychologicalProfile['anxietyBaseline'] {
    const score = Number(value ?? 0.5)
    if (score >= 0.65) return 'High'
    if (score <= 0.35) return 'Low'
    return 'Moderate'
}

function copingLabel(value?: string): PsychologicalProfile['copingStyle'] {
    const normalized = String(value ?? '').toLowerCase()
    if (normalized === 'proactive') return 'Active'
    if (normalized === 'avoidant') return 'Avoidant'
    if (normalized === 'supportive') return 'Supportive'
    return 'Mixed'
}

function buildInsight(profile?: RawDashboardProfile): string {
    const triggers = profile?.emotional_triggers ?? []
    const distortions = profile?.top_distortions ?? []
    const symptoms = profile?.top_symptoms ?? []
    const secondary = profile?.top_secondary_emotions ?? []
    if (symptoms.length && secondary.length) {
        return `Recent patterns connect ${secondary.slice(0, 2).join(' and ')} with ${symptoms[0].replaceAll('_', ' ')}. Track both the feeling and body/cognitive signal before deciding which support helps.`
    }
    if (triggers.length && distortions.length) {
        return `Recent patterns connect ${triggers.slice(0, 2).join(' and ')} with ${distortions[0]}. Keep support focused on that trigger before choosing an exercise.`
    }
    if (symptoms.length) {
        return `The clearest current signal is ${symptoms[0].replaceAll('_', ' ')}. Improvement should be judged by whether that symptom eases, not only by the core emotion label.`
    }
    if (triggers.length) {
        return `The clearest current trigger is ${triggers[0]}. The next best support step is to keep tracking what changes before and after that situation.`
    }
    return 'More check-ins will make the profile sharper. Current analytics are ready, but personalization improves with repeated mood and technique feedback.'
}

function mapMoodTimeline(raw: RawDashboardResponse): MoodDataPoint[] {
    const timeline = raw.mood?.timeline ?? []
    const points = timeline.map((point) => ({
        date: dateLabel(point.created_at),
        score: scoreToPercent(point.score),
        emotion: toEmotion(point.emotion),
        primarySubEmotion: point.primary_sub_emotion ?? null,
        secondarySubEmotions: point.secondary_sub_emotions ?? [],
        detectedSymptoms: point.detected_symptoms ?? [],
        detectedBehaviors: point.detected_behaviors ?? [],
        detectedContexts: point.detected_contexts ?? [],
        intensity: ratioToPercent(point.intensity),
        sentiment: point.sentiment,
        context: point.context,
    }))
    return points.slice(-30)
}

function mapSubEmotionDistribution(raw: RawDashboardResponse): SubEmotionSlice[] {
    const distribution = raw.mood?.sub_emotion_distribution ?? {}
    const entries = Object.entries(distribution).filter(([sub]) => Boolean(sub))
    const total = entries.reduce((sum, [, count]) => sum + Number(count || 0), 0)
    return entries
        .map(([subEmotion, count]) => ({
            subEmotion,
            count: Number(count || 0),
            percentage: total > 0 ? Math.round((Number(count || 0) / total) * 100) : 0,
        }))
        .sort((a, b) => b.count - a.count)
        .slice(0, 8)
}

function mapSignalDistribution(distribution?: Record<string, number>, limit = 10): DashboardSignalSlice[] {
    const entries = Object.entries(distribution ?? {}).filter(([name]) => Boolean(name))
    const total = entries.reduce((sum, [, count]) => sum + Number(count || 0), 0)
    return entries
        .map(([name, count]) => ({
            name,
            count: Number(count || 0),
            percentage: total > 0 ? Math.round((Number(count || 0) / total) * 100) : 0,
        }))
        .sort((a, b) => b.count - a.count)
        .slice(0, limit)
}

function mapDistribution(raw: RawDashboardResponse): EmotionSlice[] {
    const distribution = raw.mood?.distribution ?? {}
    const entries = Object.entries(distribution)
    const total = entries.reduce((sum, [, count]) => sum + Number(count || 0), 0)
    return entries
        .map(([emotion, count]) => ({
            emotion: toEmotion(emotion),
            count: Number(count || 0),
            percentage: total > 0 ? Math.round((Number(count || 0) / total) * 100) : 0,
        }))
        .sort((a, b) => b.count - a.count)
}

function topEmotionFromDistribution(raw: RawDashboardResponse): EmotionType | null {
    const entries = Object.entries(raw.mood?.distribution ?? {})
        .filter(([, count]) => Number(count || 0) > 0)
        .sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0))
    return entries[0] ? toEmotion(entries[0][0]) : null
}

function topSubEmotionFromDistribution(raw: RawDashboardResponse): string | null {
    const entries = Object.entries(raw.mood?.sub_emotion_distribution ?? {})
        .filter(([name, count]) => Boolean(name) && Number(count || 0) > 0)
        .sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0))
    return entries[0]?.[0] ?? null
}

function countRecentSessions(raw: RawDashboardResponse, days: number): number {
    const cutoff = Date.now() - days * 24 * 60 * 60 * 1000
    return (raw.sessions?.recent ?? []).filter((session) => {
        if (!session.started_at) return false
        const started = new Date(session.started_at).getTime()
        return Number.isFinite(started) && started >= cutoff
    }).length
}

function mapTopTechniques(raw: RawDashboardResponse): TopTechniqueEntry[] {
    // Prefer the backend's composite-ranked array when available
    const ranked = raw.techniques?.ranked
    if (ranked && ranked.length > 0) {
        return ranked.slice(0, 5).map((item) => ({
            name: item.name || 'Unnamed technique',
            category: item.category || 'general',
            usageCount: item.usageCount ?? 0,
            meanEffectiveness: item.meanEffectiveness ?? null,
            compositeScore: item.compositeScore,
        }))
    }
    // Fallback: compute from raw ratings/outcomes (old path)
    const counts = new Map<string, TopTechniqueEntry & { ratingCount: number; outcomeCount: number }>()
    for (const rating of raw.techniques?.ratings ?? []) {
        const name = rating.technique?.name || rating.technique_id || 'Unnamed technique'
        const category = rating.technique?.category || 'general'
        const current = counts.get(name) ?? { name, category, usageCount: 0, ratingCount: 0, outcomeCount: 0 }
        current.ratingCount += 1
        current.usageCount = Math.max(current.ratingCount, current.outcomeCount)
        counts.set(name, current)
    }
    for (const outcome of raw.techniques?.outcomes ?? []) {
        const name = outcome.technique?.name || outcome.technique_id || 'Unnamed technique'
        const category = outcome.technique?.category || 'general'
        const current = counts.get(name) ?? { name, category, usageCount: 0, ratingCount: 0, outcomeCount: 0 }
        current.outcomeCount += 1
        current.usageCount = Math.max(current.ratingCount, current.outcomeCount)
        counts.set(name, current)
    }
    return Array.from(counts.values())
        .sort((a, b) => b.usageCount - a.usageCount)
        .map(({ name, category, usageCount }) => ({ name, category, usageCount }))
        .slice(0, 5)
}

function mapSessions(raw: RawDashboardResponse): SessionSummary[] {
    const detailed = raw.sessions?.recent ?? []
    if (detailed.length) {
        return detailed.slice(0, 8).map((session) => ({
            id: session.id ?? session.title ?? 'session',
            title: session.title || 'Therapeutic session',
            date: session.started_at || new Date().toISOString(),
            dominantEmotion: toEmotion(session.dominant_emotion),
            dominantSubEmotion: session.dominant_sub_emotion ?? null,
            secondarySubEmotions: session.secondary_sub_emotions ?? [],
            detectedSymptoms: session.detected_symptoms ?? [],
            detectedBehaviors: session.detected_behaviors ?? [],
            detectedContexts: session.detected_contexts ?? [],
            averageScore: scoreToPercent(session.average_score),
            trendLabel: session.trend?.label,
            trendDelta: session.trend?.delta,
            summary: session.summary ?? null,
            outcome: session.outcome ?? null,
            durationMinutes: session.duration_minutes ?? 0,
            techniqueUsed: session.techniques?.[0],
            techniques: session.techniques ?? [],
        }))
    }

    return (raw.personalization?.session_summaries ?? []).slice(0, 8).map((summary) => ({
        id: summary.session_id ?? summary.title ?? 'session',
        title: summary.title || 'Therapeutic session',
        date: summary.created_at || new Date().toISOString(),
        dominantEmotion: toEmotion(summary.emotion),
        dominantSubEmotion: summary.primary_sub_emotion ?? null,
        summary: summary.summary ?? null,
        outcome: summary.outcome ?? null,
        durationMinutes: 0,
        techniqueUsed: summary.techniques?.[0],
        techniques: summary.techniques ?? [],
    }))
}

function mapScoreTrajectory(raw: RawDashboardResponse): import('@/types').SessionScorePoint[] {
    return (raw.sessions?.score_trajectory ?? []).map((point) => ({
        sessionId: point.session_id ?? null,
        title: point.title || 'Session',
        startedAt: point.started_at ?? null,
        averageScore: Number(point.average_score ?? 0),  // already 0-100
        dominantEmotion: point.dominant_emotion || 'neutral',
        outcome: point.outcome ?? null,
    }))
}

function mapTechniqueOutcomes(raw: RawDashboardResponse): DashboardTechniqueOutcome[] {
    return (raw.techniques?.outcomes ?? []).slice(0, 10).map((outcome) => ({
        createdAt: outcome.created_at ?? null,
        techniqueName: outcome.technique?.name || outcome.technique_id || 'Unnamed technique',
        category: outcome.technique?.category,
        subEmotionBefore: outcome.sub_emotion_before ?? null,
        subEmotionAfter: outcome.sub_emotion_after ?? null,
        symptomsBefore: outcome.symptoms_before ?? [],
        symptomsAfter: outcome.symptoms_after ?? [],
        behaviorsBefore: outcome.behaviors_before ?? [],
        behaviorsAfter: outcome.behaviors_after ?? [],
        effectiveness: ratioToPercent(outcome.effectiveness),
        intensityBefore: ratioToPercent(outcome.intensity_before),
        intensityAfter: ratioToPercent(outcome.intensity_after),
    }))
}

function mapProfile(raw: RawDashboardResponse): PsychologicalProfile {
    const profile = raw.personalization?.profile
    return {
        copingStyle: copingLabel(profile?.coping_style),
        resilience: ratioToPercent(profile?.resilience_score),
        anxietyBaseline: anxietyLabel(profile?.anxiety_baseline),
        distressBaseline: ratioToPercent(profile?.distress_baseline ?? profile?.anxiety_baseline),
        emotionBaselines: profile?.emotion_baselines ?? {},
        aiInsight: buildInsight(profile),
        techniqueAcceptanceRate: ratioToPercent(profile?.technique_acceptance_rate),
        reflectionDepth: ratioToPercent(profile?.reflection_depth),
        socialDependency: ratioToPercent(profile?.social_dependency),
        dominantEmotion: profile?.dominant_emotion ?? 'neutral',
        emotionalTriggers: profile?.emotional_triggers ?? [],
        topDistortions: profile?.top_distortions ?? [],
        topPrimarySubEmotions: profile?.top_primary_sub_emotions ?? [],
        topSecondaryEmotions: profile?.top_secondary_emotions ?? [],
        topSymptoms: profile?.top_symptoms ?? [],
        topBehaviors: profile?.top_behaviors ?? [],
        topContexts: profile?.top_contexts ?? [],
    }
}

function mapImprovement(raw: RawDashboardResponse): DashboardImprovementAnalysis {
    const analysis = raw.long_term_outcomes?.improvement_analysis
    const sos = analysis?.session_outcome_stats ?? raw.long_term_outcomes?.session_outcome_stats
    return {
        status: analysis?.status ?? 'insufficient_data',
        summary: analysis?.summary ?? 'More mood records are needed before the dashboard can explain a reliable improvement trend.',
        scoreDelta: Number(analysis?.score_delta ?? 0),
        intensityDelta: Number(analysis?.intensity_delta ?? 0),
        // Normalize 1-10 scores to 0-100 % scale for UI consistency
        earlyAverageScore: analysis?.early_average_score !== undefined
            ? Math.round(analysis.early_average_score * 10)
            : undefined,
        recentAverageScore: analysis?.recent_average_score !== undefined
            ? Math.round(analysis.recent_average_score * 10)
            : undefined,
        earlyAverageIntensity: analysis?.early_average_intensity !== undefined
            ? ratioToPercent(analysis.early_average_intensity)
            : undefined,
        recentAverageIntensity: analysis?.recent_average_intensity !== undefined
            ? ratioToPercent(analysis.recent_average_intensity)
            : undefined,
        contributingFactors: analysis?.contributing_factors ?? [],
        blockers: analysis?.blockers ?? [],
        symptomsReduced: (analysis?.symptoms_reduced ?? []).map((item) => ({
            name: item.name ?? 'signal',
            delta: Number(item.delta ?? 0),
            before: Number(item.before ?? 0),
            after: Number(item.after ?? 0),
        })),
        symptomsIncreased: (analysis?.symptoms_increased ?? []).map((item) => ({
            name: item.name ?? 'signal',
            delta: Number(item.delta ?? 0),
            before: Number(item.before ?? 0),
            after: Number(item.after ?? 0),
        })),
        evidence: analysis?.evidence ?? [],
        compositeScore: analysis?.composite_score,
        sessionOutcomeStats: sos ? {
            positive: sos.positive ?? 0,
            neutral: sos.neutral ?? 0,
            negative: sos.negative ?? 0,
            total: sos.total ?? 0,
        } : undefined,
    }
}

function mapLongTerm(raw: RawDashboardResponse): DashboardLongTermOutcomes {
    const outcomes = raw.long_term_outcomes
    const sos = outcomes?.session_outcome_stats
    return {
        moodTrendLabel: (outcomes?.mood_trend?.label ?? raw.mood?.trend?.label ?? 'stable').replaceAll('_', ' '),
        moodTrendDelta: Number(outcomes?.mood_trend?.delta ?? raw.mood?.trend?.delta ?? 0),
        averageMoodScore: scoreToPercent(outcomes?.average_mood_score ?? raw.mood?.average_score),
        emotionalVolatility: Math.round(Number(outcomes?.emotional_volatility ?? raw.mood?.volatility ?? 0) * 10),
        techniqueEffectiveness: ratioToPercent(outcomes?.technique_effectiveness),
        techniqueAdherenceRate: ratioToPercent(outcomes?.technique_adherence_rate ?? raw.techniques?.adherence_rate),
        resilienceScore: ratioToPercent(outcomes?.resilience_score),
        distressBaseline: ratioToPercent(outcomes?.distress_baseline ?? raw.personalization?.profile?.distress_baseline ?? raw.personalization?.profile?.anxiety_baseline),
        interventionReadiness: ratioToPercent(outcomes?.intervention_readiness),
        improvementAnalysis: mapImprovement(raw),
        withinSessionImprovement: outcomes?.within_session_improvement ? {
            avgIntensityDelta: Number(outcomes.within_session_improvement.avg_intensity_delta ?? 0),
            sessionsMeasured: Number(outcomes.within_session_improvement.sessions_measured ?? 0),
            label: outcomes.within_session_improvement.label ?? 'insufficient_data',
            summary: outcomes.within_session_improvement.summary ?? '',
        } : undefined,
        compositeScore: Number(outcomes?.composite_score ?? 0.5),
        sessionOutcomeStats: {
            positive: sos?.positive ?? 0,
            neutral: sos?.neutral ?? 0,
            negative: sos?.negative ?? 0,
            total: sos?.total ?? 0,
        },
    }
}

function mapDataQuality(raw: RawDashboardResponse): DashboardDataQuality {
    return {
        moodLogs: raw.data_quality?.mood_logs ?? 0,
        emotionSnapshots: raw.data_quality?.emotion_snapshots ?? 0,
        sessions: raw.data_quality?.sessions ?? raw.overview?.total_sessions ?? 0,
        ratings: raw.data_quality?.ratings ?? raw.techniques?.ratings?.length ?? 0,
        warnings: raw.data_quality?.warnings ?? [],
    }
}

export async function getUserStats(userId: string): Promise<DashboardStats | null> {
    const res = await api.get<RawDashboardResponse>(
        `/dashboard/user/${userId}?days=30`,
        { headers: userScopeHeader(userId) }
    )
    if (!res.ok || !res.data) return null

    const d = res.data
    const profile = mapProfile(d)
    const longTerm = mapLongTerm(d)
    const moodTrendLabel = d.long_term_outcomes?.mood_trend?.label ?? d.mood?.trend?.label
    const topEmotion = topEmotionFromDistribution(d) ?? toEmotion(d.overview?.most_common_emotion ?? profile.dominantEmotion)
    const topSubEmotion = topSubEmotionFromDistribution(d) ?? d.overview?.most_common_sub_emotion ?? d.mood?.top_sub_emotions?.[0]?.sub_emotion ?? null

    return {
        generatedAt: d.generated_at ?? null,
        windowDays: d.window_days ?? 30,
        totalSessions: d.overview?.total_sessions ?? 0,
        sessionsThisWeek: countRecentSessions(d, 7),
        avgMood: longTerm.averageMoodScore,
        streak: d.overview?.current_checkin_streak ?? 0,
        topEmotion,
        topSubEmotion,
        moodTrend: trendDirection(moodTrendLabel),
        techniquesTried: d.techniques?.total_used ?? 0,
        moodTimeline: mapMoodTimeline(d),
        emotionDistribution: mapDistribution(d),
        subEmotionDistribution: mapSubEmotionDistribution(d),
        secondaryEmotionDistribution: mapSignalDistribution(d.mood?.secondary_emotion_distribution, 8),
        symptomDistribution: mapSignalDistribution(d.mood?.symptom_distribution, 10),
        behaviorDistribution: mapSignalDistribution(d.mood?.behavior_distribution, 10),
        contextDistribution: mapSignalDistribution(d.mood?.context_distribution, 10),
        topTechniques: mapTopTechniques(d),
        recentSessions: mapSessions(d),
        psychologicalProfile: profile,
        preferredCategories: d.techniques?.preferred_categories ?? [],
        suggestions: d.suggestions ?? [],
        techniqueOutcomes: mapTechniqueOutcomes(d),
        longTermOutcomes: longTerm,
        dataQuality: mapDataQuality(d),
        scoreTrajectory: mapScoreTrajectory(d),
        compositeScore: longTerm.compositeScore,
    }
}
