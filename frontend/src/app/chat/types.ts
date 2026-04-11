// ─── Shared Types ──────────────────────────────────────────────────────────
// Used by server actions, server page, and client components alike.

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
    // Streaming-only (ephemeral, never persisted)
    _streaming?: boolean
    _streamingId?: number
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
    emotionalBalance: number  // 0-100
    resilienceScore: number   // 0-100
}

export interface ChatInitialData {
    userId: string
    sessions: Session[]
    initialMessages: Message[]
    initialSessionId: string | null
}
