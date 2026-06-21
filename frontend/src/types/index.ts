// ─── Shared Domain Types ────────────────────────────────────────────────────

export interface Message {
    id?: string
    role: 'user' | 'assistant'
    content: string
    emotion?: string
    emotionLabel?: string | null
    emotion_label?: string | null
    rawEmotionLabel?: string | null
    raw_emotion_label?: string | null
    primarySubEmotion?: string | null
    primary_sub_emotion?: string | null
    secondarySubEmotions?: string[]
    secondary_sub_emotions?: string[]
    detectedSymptoms?: string[]
    detected_symptoms?: string[]
    detectedBehaviors?: string[]
    detected_behaviors?: string[]
    detectedContexts?: string[]
    detected_contexts?: string[]
    emotionScores?: Record<string, number>
    emotion_scores?: Record<string, number>
    sentiment?: string
    timestamp?: string
    technique?: Technique | null
    techniqueOfferedThisTurn?: boolean
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
    user_rating?: number
    user_completed?: boolean
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
    primarySubEmotion?: string | null
    secondarySubEmotions?: string[]
    detectedSymptoms?: string[]
    detectedBehaviors?: string[]
    detectedContexts?: string[]
    intensity?: number
    sentiment?: string
    context?: string | null
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
    /** Mean effectiveness across outcome records, 0–100 (null if no outcomes yet) */
    meanEffectiveness?: number | null
    /** Composite ranking score (usageCount × max(0, effectiveness)) */
    compositeScore?: number
}

export interface SessionSummary {
    id: string
    title: string
    date: string
    dominantEmotion: EmotionType
    dominantSubEmotion?: string | null
    secondarySubEmotions?: string[]
    detectedSymptoms?: string[]
    detectedBehaviors?: string[]
    detectedContexts?: string[]
    averageScore?: number
    trendLabel?: string
    trendDelta?: number
    summary?: string | null
    outcome?: string | null
    durationMinutes: number
    techniqueUsed?: string
    techniques?: string[]
}

export interface PsychologicalProfile {
    copingStyle: 'Active' | 'Avoidant' | 'Supportive' | 'Mixed'
    resilience: number        // 0–100
    anxietyBaseline: 'Low' | 'Moderate' | 'High'
    distressBaseline?: number
    emotionBaselines?: Record<string, number>
    aiInsight: string
    techniqueAcceptanceRate?: number
    reflectionDepth?: number
    socialDependency?: number
    dominantEmotion?: string
    emotionalTriggers?: string[]
    topDistortions?: string[]
    topPrimarySubEmotions?: string[]
    topSecondaryEmotions?: string[]
    topSymptoms?: string[]
    topBehaviors?: string[]
    topContexts?: string[]
}

export interface DashboardSuggestion {
    priority: 'high' | 'medium' | 'low'
    area: string
    title: string
    action: string
}

export interface DashboardTechniqueOutcome {
    createdAt: string | null
    techniqueName: string
    category?: string | null
    subEmotionBefore?: string | null
    subEmotionAfter?: string | null
    symptomsBefore?: string[]
    symptomsAfter?: string[]
    behaviorsBefore?: string[]
    behaviorsAfter?: string[]
    effectiveness: number
    intensityBefore: number
    intensityAfter: number
}

export interface SubEmotionSlice {
    subEmotion: string
    count: number
    percentage: number
}

export interface DashboardSignalSlice {
    name: string
    count: number
    percentage: number
}

export interface DashboardSignalChange {
    name: string
    delta: number
    before: number
    after: number
}

export interface DashboardImprovementAnalysis {
    status: 'improving' | 'declining' | 'stable' | 'insufficient_data'
    summary: string
    scoreDelta: number
    intensityDelta: number
    earlyAverageScore?: number
    recentAverageScore?: number
    earlyAverageIntensity?: number
    recentAverageIntensity?: number
    contributingFactors: string[]
    blockers: string[]
    symptomsReduced: DashboardSignalChange[]
    symptomsIncreased: DashboardSignalChange[]
    evidence: string[]
    /** 0.0–1.0 weighted composite of all signals */
    compositeScore?: number
    sessionOutcomeStats?: { positive: number; neutral: number; negative: number; total: number }
}

export interface SessionScorePoint {
    sessionId: string | null
    title: string
    startedAt: string | null
    averageScore: number   // 0-100
    dominantEmotion: string
    outcome: string | null
}

export interface WithinSessionImprovement {
    avgIntensityDelta: number
    sessionsMeasured: number
    label: 'relieving' | 'neutral' | 'worsening' | 'insufficient_data'
    summary: string
}

export interface DashboardLongTermOutcomes {
    moodTrendLabel: string
    moodTrendDelta: number
    averageMoodScore: number
    emotionalVolatility: number
    techniqueEffectiveness: number
    techniqueAdherenceRate: number
    resilienceScore: number
    distressBaseline: number
    interventionReadiness: number
    improvementAnalysis: DashboardImprovementAnalysis
    withinSessionImprovement?: WithinSessionImprovement
    /** 0.0–1.0 weighted composite wellness score */
    compositeScore: number
    sessionOutcomeStats: { positive: number; neutral: number; negative: number; total: number }
}

export interface DashboardDataQuality {
    moodLogs: number
    emotionSnapshots: number
    sessions: number
    ratings: number
    warnings: string[]
}

export interface VoiceInsights {
    used: boolean
    totalVoiceMessages: number
    dominantEmotion: string | null
    avgArousal: number | null
    avgValence: number | null
    avgConfidence: number | null
    avgAcousticDistressProxy: number | null
    recentEmotions: { emotion: string | null; arousal: number | null; valence: number | null; date: string | null }[]
}

export interface ClinicalAssessmentTrendPoint {
    date: string | null
    sessionTitle: string
    severity: string
    // Before therapy (first log in session)
    startPhq9: number
    startGad7: number
    // After therapy / session closing (last log in session)
    endPhq9: number
    endGad7: number
    // Within-session deltas (negative = improved during session)
    withinPhq9Delta: number
    withinGad7Delta: number
    // Cross-session delta vs first-ever session baseline
    delta: number | null
    indicators: string[]
    confidence: number
    logCount: number
}

export interface ClinicalAssessmentStats {
    hasData: boolean
    currentPhq9: number
    currentGad7: number
    currentSeverity: string
    improving: boolean
    latestDelta: number | null
    trend: ClinicalAssessmentTrendPoint[]
}

export interface DashboardStats {
    generatedAt?: string | null
    windowDays: number
    totalSessions: number
    avgMood: number
    streak: number
    topEmotion: EmotionType
    topSubEmotion?: string | null
    sessionsThisWeek: number
    moodTrend: 'up' | 'down' | 'stable' | 'insufficient_data'
    techniquesTried: number
    moodTimeline: MoodDataPoint[]
    emotionDistribution: EmotionSlice[]
    subEmotionDistribution: SubEmotionSlice[]
    secondaryEmotionDistribution: DashboardSignalSlice[]
    symptomDistribution: DashboardSignalSlice[]
    behaviorDistribution: DashboardSignalSlice[]
    contextDistribution: DashboardSignalSlice[]
    topTechniques: TopTechniqueEntry[]
    recentSessions: SessionSummary[]
    psychologicalProfile: PsychologicalProfile
    preferredCategories: string[]
    suggestions: DashboardSuggestion[]
    techniqueOutcomes: DashboardTechniqueOutcome[]
    longTermOutcomes: DashboardLongTermOutcomes
    dataQuality: DashboardDataQuality
    /** Per-session average score trajectory (oldest → newest, 0-100 scale) */
    scoreTrajectory: SessionScorePoint[]
    /** 0.0–1.0 weighted composite wellness score (same as longTermOutcomes.compositeScore) */
    compositeScore: number
    voiceInsights: VoiceInsights
    clinicalAssessment?: ClinicalAssessmentStats
}

// ─── Onboarding ─────────────────────────────────────────────────────────────

export type MoodLevel = 'great' | 'good' | 'okay' | 'low' | 'awful'

export interface OnboardingGoal {
    id: string
    label: string
    icon: string
}

export interface EmergencyContactInput {
    name: string
    phone: string
    relation?: string
    channel?: 'sms' | 'whatsapp'
}

export interface OnboardingData {
    mood: MoodLevel | null
    goals: string[]
    notificationsEnabled: boolean
    crisisLocationConsent: boolean
    emergencyContactConsent: boolean
    emergencyContacts: EmergencyContactInput[]
    /** GAP-07: GDPR Art.9 — separate explicit consent for voice tone analysis */
    voiceAnalysisConsent: boolean
}

// ─── Profile / Settings ──────────────────────────────────────────────────────

export interface UserSettings {
    dailyReminderEnabled: boolean
    weeklyEmailEnabled: boolean
    sessionAutoSave: boolean
    anonymousMode: boolean
    shareLocationInCrisis: boolean
    emergencyContactConsent: boolean
    voiceAnalysisConsent: boolean
    theme: 'light' | 'dark' | 'system'
}

export interface UserProfile {
    id: string
    name: string
    email: string
    created_at?: string
    settings: UserSettings
}
