'use client'

import { useState, useCallback } from 'react'
import { Message, Technique } from '@/types'
import { API_BASE } from '@/lib/api'

// Manage SSE streaming chat logic
export function useStream(userId: string) {
    const [messages, setMessages] = useState<Message[]>([])
    const [isStreaming, setIsStreaming] = useState(false)
    const [latestEmotion, setLatestEmotion] = useState<string | null>(null)
    const [latestSentiment, setLatestSentiment] = useState<string | null>(null)
    const [activeTechnique, setActiveTechnique] = useState<Technique | null>(null)
    const [alternativeTechniques, setAlternativeTechniques] = useState<Technique[]>([])

    const sendMessage = useCallback(
        async (
            text: string,
            currentSessionId: string | null,
            onSessionCreated: (sid: string) => void
        ) => {
            if (!text.trim() || isStreaming) return

            setMessages((prev) => [...prev, { role: 'user', content: text }])
            setIsStreaming(true)

            const streamingId = Date.now()
            setMessages((prev) => [
                ...prev,
                {
                    role: 'assistant',
                    content: '',
                    _streamingId: streamingId,
                    _streaming: true,
                },
            ])

            try {
                const res = await fetch(`${API_BASE}/chat/stream`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        user_id: userId,
                        message: text,
                        session_id: currentSessionId,
                    }),
                })

                if (!res.ok) throw new Error()

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
                                setMessages((prev) =>
                                    prev.map((m) =>
                                        m._streamingId === streamingId
                                            ? { ...m, content: m.content + ev.content }
                                            : m
                                    )
                                )
                            } else if (ev.type === 'done') {
                                setMessages((prev) =>
                                    prev.map((m) =>
                                        m._streamingId === streamingId
                                            ? {
                                                ...m,
                                                _streaming: false,
                                                emotion: ev.emotion,
                                                sentiment: ev.sentiment,
                                                crisis_detected: ev.crisis_detected,
                                                recommendedTechniquesByCategory:
                                                    ev.recommended_techniques_by_category ?? {},
                                                alternativeTechniques:
                                                    ev.alternative_techniques ?? [],
                                            }
                                            : m
                                    )
                                )
                                setLatestEmotion(ev.emotion ?? null)
                                setLatestSentiment(ev.sentiment ?? null)

                                // Pick all recommended techniques from category dict
                                if (ev.recommended_techniques_by_category) {
                                    const all = Object.values(
                                        ev.recommended_techniques_by_category as Record<string, Technique>
                                    )
                                    if (all.length > 0) {
                                        setActiveTechnique(all[0])
                                        setAlternativeTechniques(all.slice(1))
                                    }
                                }

                                if (!currentSessionId && ev.session_id) {
                                    onSessionCreated(ev.session_id)
                                }
                            }
                        } catch {
                            // Ignore malformed JSON
                        }
                    }
                }
            } catch {
                setMessages((prev) =>
                    prev.map((m) =>
                        m._streamingId === streamingId
                            ? {
                                ...m,
                                content: 'Connection lost. Please try again.',
                                _streaming: false,
                            }
                            : m
                    )
                )
            } finally {
                setIsStreaming(false)
            }
        },
        [isStreaming, userId]
    )

    const clearMessages = useCallback((defaultMsg?: Message) => {
        setMessages(defaultMsg ? [defaultMsg] : [])
        setLatestEmotion(null)
        setLatestSentiment(null)
        setActiveTechnique(null)
        setAlternativeTechniques([])
    }, [])

    return {
        messages,
        setMessages,
        isStreaming,
        latestEmotion,
        latestSentiment,
        activeTechnique,
        alternativeTechniques,
        sendMessage,
        clearMessages,
        setIsStreaming,
    }
}
