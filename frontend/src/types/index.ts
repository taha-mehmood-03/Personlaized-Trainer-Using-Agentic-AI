// ─── Shared Domain Types ────────────────────────────────────────────────────

export interface Message {
    role: 'user' | 'assistant'
    content: string
    emotion?: string
    sentiment?: string
    timestamp?: string
    technique?: Technique | null
    voiceEmotion?: string
    voiceConfidence?: number
    crisis_detected?: boolean
    recommendedTechniquesByCategory?: Record<string, Technique>
    alternativeTechniques?: Technique[]
    tools_used?: string[]
    // Streaming-only — never persisted
    _streaming?: boolean
    _streamingId?: number
    _showCursor?: boolean
}

export interface Session {
    id: string
    title: string | null
    createdAt: string
    updatedAt?: string
    messages: Message[]
}

export interface Technique {
    id: string
    name: string
    brief: string
    description?: string
    why_it_works?: string
    category: string
    duration_minutes: number
    difficulty?: string
    steps: string[]
}

export interface AcousticFeatures {
    pitch_mean?: number
    loudness_mean?: number
    speech_rate?: number
}

export interface VoiceResult {
    emotion: string
    confidence: number
    acoustic_features?: AcousticFeatures
}

export interface UserProgress {
    emotionalBalance: number
    resilienceScore: number
}

export interface ChatInitialData {
    userId: string
    sessions: Session[]
    initialMessages: Message[]
    initialSessionId: string | null
}

export interface User {
    id: string
    name?: string
    email?: string
    plan?: 'free' | 'premium'
    createdAt?: string
}

export type EmotionType =
    | 'joy'
    | 'sadness'
    | 'anger'
    | 'fear'
    | 'disgust'
    | 'surprise'
    | 'neutral'
    | 'anxiety'
    | 'guilt'

export interface MoodDataPoint {
    date: string       // 'Mon', 'Tue', …
    score: number      // 0–100
    emotion: EmotionType
}

export interface EmotionSlice {
    emotion: EmotionType
    count: number
    percentage: number
}

export interface TopTechniqueEntry {
    name: string
    category: string
    usageCount: number
}

export interface SessionSummary {
    id: string
    title: string
    date: string
    dominantEmotion: EmotionType
    durationMinutes: number
    techniqueUsed?: string
}

export interface PsychologicalProfile {
    copingStyle: 'Active' | 'Avoidant' | 'Supportive' | 'Mixed'
    resilience: number        // 0–100
    anxietyBaseline: 'Low' | 'Moderate' | 'High'
    aiInsight: string
}

export interface DashboardStats {
    totalSessions: number
    avgMood: number
    streak: number
    topEmotion: EmotionType
    sessionsThisWeek: number
    moodTrend: 'up' | 'down' | 'stable'
    techniquesTried: number
    moodTimeline: MoodDataPoint[]
    emotionDistribution: EmotionSlice[]
    topTechniques: TopTechniqueEntry[]
    recentSessions: SessionSummary[]
    psychologicalProfile: PsychologicalProfile
}

// ─── Onboarding ─────────────────────────────────────────────────────────────

export type MoodLevel = 'great' | 'good' | 'okay' | 'low' | 'awful'

export interface OnboardingGoal {
    id: string
    label: string
    icon: string
}

export interface OnboardingData {
    mood: MoodLevel | null
    goals: string[]
    notificationsEnabled: boolean
}

// ─── Profile / Settings ──────────────────────────────────────────────────────

export interface UserSettings {
    dailyReminderEnabled: boolean
    weeklyEmailEnabled: boolean
    sessionAutoSave: boolean
    anonymousMode: boolean
    shareLocationInCrisis: boolean
    theme: 'light' | 'dark' | 'system'
}
