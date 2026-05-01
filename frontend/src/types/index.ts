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

export interface DashboardStats {
    totalSessions: number
    avgMood: number
    streak: number
    topEmotion: EmotionType
}
