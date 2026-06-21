'use client'

import { useState, useCallback, useRef, useEffect } from 'react'
import { Message, Technique } from '@/types'
import { API_BASE } from '@/lib/api'
import { cleanAssistantContent, cleanEmotionList, firstEmotionLabel } from '@/lib/chatEmotion'
import { sendCrisisLocation, shouldRequestCrisisGps } from '@/lib/crisisLocation'
import {
    classifyPostCrisisSafetyReply,
    postCrisisSafetyStorageKey,
    POST_CRISIS_DANGER_PROMPT,
    POST_CRISIS_SAFETY_PROMPT,
} from '@/lib/crisisSafety'

// Configuration for smooth streaming effect
const STREAMING_CONFIG = {
    BATCH_SIZE: 8, // Accumulate tokens before rendering
    RENDER_DELAY_MS: 15, // Delay between token renders for smooth animation
    FIRST_TOKEN_TIMEOUT: 3000, // Timeout to show "typing..." if no first token
}

function cleanEmotionScores(value: unknown): Record<string, number> {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
    return value as Record<string, number>
}

function normalizeTechnique(value: unknown): Technique | null {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null

    const source = value as Partial<Technique> & {
        technique_id?: unknown
        techniqueId?: unknown
    }
    const rawId = source.id ?? source.technique_id ?? source.techniqueId
    const id = typeof rawId === 'string' ? rawId.trim() : rawId == null ? '' : String(rawId).trim()

    if (!id) return null

    return {
        ...source,
        id,
    } as Technique
}

function normalizeTechniqueList(value: unknown): Technique[] {
    if (!Array.isArray(value)) return []
    return value
        .map(normalizeTechnique)
        .filter((item): item is Technique => item !== null)
}

function normalizeTechniqueMap(value: unknown): Record<string, Technique> {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {}

    return Object.entries(value as Record<string, unknown>).reduce<Record<string, Technique>>(
        (acc, [category, technique]) => {
            const normalized = normalizeTechnique(technique)
            if (normalized) acc[category] = normalized
            return acc
        },
        {}
    )
}

// Manage SSE streaming chat logic
export function useStream(userId: string) {
    const [messages, setMessages] = useState<Message[]>([])
    const [isStreaming, setIsStreaming] = useState(false)
    const [latestEmotion, setLatestEmotion] = useState<string | null>(null)
    const [latestSubEmotion, setLatestSubEmotion] = useState<string | null>(null)
    const [latestSentiment, setLatestSentiment] = useState<string | null>(null)
    const [activeTechnique, setActiveTechnique] = useState<Technique | null>(null)
    const [alternativeTechniques, setAlternativeTechniques] = useState<Technique[]>([])
    const [showTypingIndicator, setShowTypingIndicator] = useState(false)
    const [postCrisisSafetyCheck, setPostCrisisSafetyCheck] = useState(false)

    // Refs for smooth streaming management
    const tokenBufferRef = useRef<string>('')
    const firstTokenTimeoutRef = useRef<NodeJS.Timeout | null>(null)
    const renderTimeoutRef = useRef<NodeJS.Timeout | null>(null)
    const postCrisisSafetyCheckRef = useRef(false)

    // Cleanup timeouts on unmount
    useEffect(() => {
        return () => {
            if (firstTokenTimeoutRef.current) clearTimeout(firstTokenTimeoutRef.current)
            if (renderTimeoutRef.current) clearTimeout(renderTimeoutRef.current)
        }
    }, [])

    useEffect(() => {
        if (typeof window === 'undefined') return
        const active = window.localStorage.getItem(postCrisisSafetyStorageKey(userId)) === '1'
        postCrisisSafetyCheckRef.current = active
        setPostCrisisSafetyCheck(active)
    }, [userId])

    const setSafetyCheckRequired = useCallback(
        (required: boolean) => {
            postCrisisSafetyCheckRef.current = required
            setPostCrisisSafetyCheck(required)
            if (typeof window === 'undefined') return
            const key = postCrisisSafetyStorageKey(userId)
            if (required) {
                window.localStorage.setItem(key, '1')
            } else {
                window.localStorage.removeItem(key)
            }
        },
        [userId]
    )

    const appendLocalSafetyPrompt = useCallback((userText: string, prompt: string) => {
        setMessages((prev) => [
            ...prev,
            {
                role: 'user',
                content: userText || 'Voice message',
            },
            {
                role: 'assistant',
                content: prompt,
                crisis_detected: true,
            },
        ])
        setShowTypingIndicator(false)
    }, [])

    const sendMessage = useCallback(
        async (
            text: string,
            currentSessionId: string | null,
            onSessionCreated: (sid: string) => void,
            audioData?: string
        ) => {
            const trimmedText = text.trim()
            if ((!trimmedText && !audioData) || isStreaming) return

            if (postCrisisSafetyCheckRef.current) {
                const safetyStatus = classifyPostCrisisSafetyReply(trimmedText)
                if (safetyStatus === 'safe') {
                    setSafetyCheckRequired(false)
                } else {
                    appendLocalSafetyPrompt(
                        trimmedText,
                        safetyStatus === 'danger' ? POST_CRISIS_DANGER_PROMPT : POST_CRISIS_SAFETY_PROMPT
                    )
                    return
                }
            }

            setMessages((prev) => [...prev, { role: 'user', content: trimmedText }])
            setIsStreaming(true)
            setShowTypingIndicator(true)

            const streamingId = Date.now()
            setMessages((prev) => [
                ...prev,
                {
                    role: 'assistant',
                    content: '',
                    _streamingId: streamingId,
                    _streaming: true,
                    _showCursor: true, // Show blinking cursor
                },
            ])

            // Reset token buffer for this stream
            tokenBufferRef.current = ''
            let receivedFirstToken = false
            let crisisGpsRequested = false

            const requestCrisisGpsOnce = () => {
                if (crisisGpsRequested) return
                crisisGpsRequested = true
                void sendCrisisLocation({ apiBase: API_BASE, userId })
                    .then((sent) => {
                        if (sent) setSafetyCheckRequired(true)
                    })
                    .catch((error) => {
                        console.error('[CRISIS] Could not send browser GPS location:', error)
                    })
            }

            if (shouldRequestCrisisGps(trimmedText)) {
                requestCrisisGpsOnce()
            }

            try {
                const res = await fetch(`${API_BASE}/chat/stream`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-SentiMind-User-Id': userId,
                    },
                    body: JSON.stringify({
                        user_id: userId,
                        message: trimmedText,
                        session_id: currentSessionId,
                        audio_data: audioData,
                    }),
                })

                if (!res.ok) throw new Error('Stream failed')

                // Set timeout to show typing indicator if no first token arrives quickly
                firstTokenTimeoutRef.current = setTimeout(() => {
                    if (!receivedFirstToken) {
                        setShowTypingIndicator(true)
                    }
                }, STREAMING_CONFIG.FIRST_TOKEN_TIMEOUT)

                const reader = res.body!.getReader()
                const decoder = new TextDecoder()
                let buf = ''

                while (true) {
                    const { done, value } = await reader.read()
                    if (done) break

                    buf += decoder.decode(value, { stream: true })
                    const lines = buf.split('\n')
                    buf = lines.pop() ?? ''

                    for (const line of lines) {
                        if (!line.startsWith('data: ')) continue
                        const json = line.slice(6).trim()
                        if (!json) continue

                        try {
                            const ev = JSON.parse(json)
                            
                            if (ev.type === 'token') {
                                // Got first token - clear timeout
                                if (!receivedFirstToken && firstTokenTimeoutRef.current) {
                                    clearTimeout(firstTokenTimeoutRef.current)
                                    receivedFirstToken = true
                                    setShowTypingIndicator(false)
                                }

                                // Add token to buffer
                                tokenBufferRef.current += ev.content

                                // Render buffered tokens (batch rendering for smooth effect)
                                if (tokenBufferRef.current.length >= STREAMING_CONFIG.BATCH_SIZE) {
                                    const batchContent = tokenBufferRef.current
                                    tokenBufferRef.current = ''

                                    setMessages((prev) =>
                                        prev.map((m) =>
                                            m._streamingId === streamingId
                                                ? { ...m, content: cleanAssistantContent(m.content + batchContent) }
                                                : m
                                        )
                                    )

                                    // Add slight delay for human-like typing effect
                                    await new Promise((resolve) =>
                                        (renderTimeoutRef.current = setTimeout(
                                            resolve,
                                            STREAMING_CONFIG.RENDER_DELAY_MS
                                        ))
                                    )
                                }
                            } else if (ev.type === 'done') {
                                // The backend sends: {type: 'done', metadata: {...}}
                                // All fields are nested under ev.metadata
                                const meta = ev.metadata ?? ev  // fallback to ev for older compat
                                const moodAnalysis = meta.mood_analysis ?? meta.moodAnalysis ?? {}

                                // Flush any remaining tokens in buffer
                                if (tokenBufferRef.current) {
                                    const remaining = tokenBufferRef.current
                                    setMessages((prev) =>
                                        prev.map((m) =>
                                            m._streamingId === streamingId
                                                ? { ...m, content: cleanAssistantContent(m.content + remaining) }
                                                : m
                                        )
                                    )
                                    tokenBufferRef.current = ''
                                }

                                // Mark streaming as complete and update metadata
                                const emotion = firstEmotionLabel(
                                    meta.emotion,
                                    meta.fused_emotion,
                                    meta.mood,
                                    moodAnalysis.emotion
                                )
                                const primarySubEmotion = firstEmotionLabel(
                                    meta.primary_sub_emotion,
                                    meta.primarySubEmotion,
                                    moodAnalysis.primary_sub_emotion,
                                    moodAnalysis.primarySubEmotion,
                                    moodAnalysis.sub_emotion,
                                    moodAnalysis.subEmotion
                                )
                                const secondarySubEmotions = cleanEmotionList(
                                    meta.secondary_sub_emotions ??
                                        meta.secondarySubEmotions ??
                                        moodAnalysis.secondary_sub_emotions
                                )
                                const detectedSymptoms = cleanEmotionList(
                                    meta.detected_symptoms ?? meta.detectedSymptoms ?? moodAnalysis.detected_symptoms
                                )
                                const detectedBehaviors = cleanEmotionList(
                                    meta.detected_behaviors ?? meta.detectedBehaviors ?? moodAnalysis.detected_behaviors
                                )
                                const detectedContexts = cleanEmotionList(
                                    meta.detected_contexts ?? meta.detectedContexts ?? moodAnalysis.detected_contexts
                                )
                                const sentiment = firstEmotionLabel(meta.sentiment, meta.moodSummary, moodAnalysis.sentiment)
                                const emotionMetadata = {
                                    emotion: emotion ?? undefined,
                                    emotionLabel: firstEmotionLabel(
                                        meta.emotion_label,
                                        meta.emotionLabel,
                                        moodAnalysis.emotion_label
                                    ),
                                    rawEmotionLabel: firstEmotionLabel(
                                        meta.raw_emotion_label,
                                        meta.rawEmotionLabel,
                                        moodAnalysis.raw_emotion_label
                                    ),
                                    primarySubEmotion,
                                    secondarySubEmotions,
                                    detectedSymptoms,
                                    detectedBehaviors,
                                    detectedContexts,
                                    emotionScores: cleanEmotionScores(
                                        meta.emotion_scores ?? meta.emotionScores ?? moodAnalysis.emotion_scores
                                    ),
                                    sentiment: sentiment ?? undefined,
                                }
                                const recommendedTechniquesByCategory = normalizeTechniqueMap(
                                    meta.recommended_techniques_by_category
                                )
                                const directTechnique = normalizeTechnique(
                                    meta.recommended_technique ?? meta.recommendedTechnique ?? meta.technique
                                )
                                const primaryTechnique =
                                    Object.values(recommendedTechniquesByCategory)[0] ?? directTechnique
                                const hasAlternativeTechniques = Object.prototype.hasOwnProperty.call(
                                    meta,
                                    'alternative_techniques'
                                )
                                const normalizedAlternativeTechniques = normalizeTechniqueList(
                                    meta.alternative_techniques
                                )
                                setMessages((prev) => {
                                    const streamingIndex = prev.findIndex((m) => m._streamingId === streamingId)
                                    return prev.map((m, index) => {
                                        if (m._streamingId === streamingId) {
                                            return {
                                                ...m,
                                                content: cleanAssistantContent(m.content),
                                                _streaming: false,
                                                _showCursor: false,
                                                crisis_detected: meta.crisis_detected,
                                                technique: primaryTechnique,
                                                techniqueOfferedThisTurn: !!primaryTechnique && !!meta.technique_offered_this_turn,
                                                recommendedTechniquesByCategory,
                                                alternativeTechniques: normalizedAlternativeTechniques,
                                            }
                                        }
                                        if (index === streamingIndex - 1 && m.role === 'user') {
                                            return { ...m, ...emotionMetadata }
                                        }
                                        return m
                                    })
                                })

                                setLatestEmotion(emotion)
                                setLatestSubEmotion(primarySubEmotion)
                                setLatestSentiment(sentiment)
                                setShowTypingIndicator(false)

                                if (meta.crisis_detected) {
                                    requestCrisisGpsOnce()
                                }

                                // Pick all recommended techniques from category dict
                                if (primaryTechnique) {
                                    setActiveTechnique(primaryTechnique)
                                }

                                if (hasAlternativeTechniques) {
                                    setAlternativeTechniques(normalizedAlternativeTechniques)
                                }

                                if (!currentSessionId && meta.session_id) {
                                    onSessionCreated(meta.session_id)
                                }
                            }
                        } catch {
                            // Ignore malformed JSON
                        }
                    }
                }
            } catch (error) {
                console.error('Stream error:', error)
                setShowTypingIndicator(false)

                setMessages((prev) =>
                    prev.map((m) =>
                        m._streamingId === streamingId
                            ? {
                                ...m,
                                content: 'Connection lost. Please try again.',
                                _streaming: false,
                                _showCursor: false,
                            }
                            : m
                    )
                )
            } finally {
                setIsStreaming(false)
                setShowTypingIndicator(false)
                tokenBufferRef.current = ''
                if (firstTokenTimeoutRef.current) {
                    clearTimeout(firstTokenTimeoutRef.current)
                }
                if (renderTimeoutRef.current) {
                    clearTimeout(renderTimeoutRef.current)
                }
            }
        },
        [appendLocalSafetyPrompt, isStreaming, setSafetyCheckRequired, userId]
    )

    const clearMessages = useCallback((defaultMsg?: Message) => {
        setMessages(defaultMsg ? [defaultMsg] : [])
        setLatestEmotion(null)
        setLatestSubEmotion(null)
        setLatestSentiment(null)
        setActiveTechnique(null)
        setAlternativeTechniques([])
        setShowTypingIndicator(false)
        tokenBufferRef.current = ''
    }, [])

    return {
        messages,
        setMessages,
        isStreaming,
        showTypingIndicator,
        latestEmotion,
        latestSubEmotion,
        latestSentiment,
        activeTechnique,
        alternativeTechniques,
        postCrisisSafetyCheck,
        sendMessage,
        clearMessages,
        setIsStreaming,
    }
}
