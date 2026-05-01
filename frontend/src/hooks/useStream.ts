'use client'

import { useState, useCallback, useRef, useEffect } from 'react'
import { Message, Technique } from '@/types'
import { API_BASE } from '@/lib/api'

// Configuration for smooth streaming effect
const STREAMING_CONFIG = {
    BATCH_SIZE: 8, // Accumulate tokens before rendering
    RENDER_DELAY_MS: 15, // Delay between token renders for smooth animation
    FIRST_TOKEN_TIMEOUT: 3000, // Timeout to show "typing..." if no first token
}

// Manage SSE streaming chat logic
export function useStream(userId: string) {
    const [messages, setMessages] = useState<Message[]>([])
    const [isStreaming, setIsStreaming] = useState(false)
    const [latestEmotion, setLatestEmotion] = useState<string | null>(null)
    const [latestSentiment, setLatestSentiment] = useState<string | null>(null)
    const [activeTechnique, setActiveTechnique] = useState<Technique | null>(null)
    const [alternativeTechniques, setAlternativeTechniques] = useState<Technique[]>([])
    const [showTypingIndicator, setShowTypingIndicator] = useState(false)

    // Refs for smooth streaming management
    const tokenBufferRef = useRef<string>('')
    const firstTokenTimeoutRef = useRef<NodeJS.Timeout | null>(null)
    const renderTimeoutRef = useRef<NodeJS.Timeout | null>(null)

    // Cleanup timeouts on unmount
    useEffect(() => {
        return () => {
            if (firstTokenTimeoutRef.current) clearTimeout(firstTokenTimeoutRef.current)
            if (renderTimeoutRef.current) clearTimeout(renderTimeoutRef.current)
        }
    }, [])

    const sendMessage = useCallback(
        async (
            text: string,
            currentSessionId: string | null,
            onSessionCreated: (sid: string) => void,
            audioData?: string
        ) => {
            if (!text.trim() && !audioData || isStreaming) return

            setMessages((prev) => [...prev, { role: 'user', content: text }])
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

            try {
                const res = await fetch(`${API_BASE}/chat/stream`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        user_id: userId,
                        message: text,
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
                                                ? { ...m, content: m.content + batchContent }
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

                                // Flush any remaining tokens in buffer
                                if (tokenBufferRef.current) {
                                    setMessages((prev) =>
                                        prev.map((m) =>
                                            m._streamingId === streamingId
                                                ? { ...m, content: m.content + tokenBufferRef.current }
                                                : m
                                        )
                                    )
                                    tokenBufferRef.current = ''
                                }

                                // Mark streaming as complete and update metadata
                                setMessages((prev) =>
                                    prev.map((m) =>
                                        m._streamingId === streamingId
                                            ? {
                                                ...m,
                                                _streaming: false,
                                                _showCursor: false,
                                                emotion: meta.emotion,
                                                sentiment: meta.sentiment,
                                                crisis_detected: meta.crisis_detected,
                                                recommendedTechniquesByCategory:
                                                    meta.recommended_techniques_by_category ?? {},
                                                alternativeTechniques:
                                                    meta.alternative_techniques ?? [],
                                            }
                                            : m
                                    )
                                )

                                setLatestEmotion(meta.emotion ?? null)
                                setLatestSentiment(meta.sentiment ?? null)
                                setShowTypingIndicator(false)

                                // ── Crisis Location Alert (Using Browser GPS) ─────────────────
                                // If crisis detected, send GPS location via browser geolocation API
                                if (meta.crisis_detected && typeof navigator !== 'undefined' && 'geolocation' in navigator) {
                                    console.log('[CRISIS] 🚨 CRISIS DETECTED - Requesting precise GPS location from browser...')
                                    
                                    // Use enableHighAccuracy for the most precise location possible
                                    navigator.geolocation.getCurrentPosition(
                                        async (pos) => {
                                            const lat = pos.coords.latitude
                                            const lng = pos.coords.longitude
                                            const accuracy = pos.coords.accuracy
                                            const mapsLink = `https://www.google.com/maps?q=${lat},${lng}`
                                            
                                            console.log('[CRISIS] ✅ GPS ACQUIRED - Precise location obtained!')
                                            console.log('[CRISIS] 📍 Coordinates: ' + lat.toFixed(6) + ', ' + lng.toFixed(6))
                                            console.log('[CRISIS] 📏 Accuracy: ±' + Math.round(accuracy) + ' metres')
                                            console.log('[CRISIS] 🗺️ Google Maps: ' + mapsLink)
                                            
                                            try {
                                                const response = await fetch(`${API_BASE}/crisis/send-location`, {
                                                    method: 'POST',
                                                    headers: { 'Content-Type': 'application/json' },
                                                    body: JSON.stringify({
                                                        user_id: userId,
                                                        latitude: lat,
                                                        longitude: lng,
                                                        accuracy: accuracy,
                                                        crisis_level: 'high',
                                                    }),
                                                })
                                                const data = await response.json()
                                                if (data.success) {
                                                    console.log('[CRISIS] 📲 GPS location sent to WhatsApp via ' + data.channel)
                                                    console.log('[CRISIS] ✅ Alert SID: ' + data.message_sid)
                                                    console.log('[CRISIS] 🆗 Crisis help has been alerted to your location')
                                                } else {
                                                    console.warn('[CRISIS] ⚠️ Failed to send location alert:', data.error)
                                                }
                                            } catch (err) {
                                                console.error('[CRISIS] ❌ Error sending GPS location:', err)
                                            }
                                        },
                                        (err) => {
                                            // GPS permission denied, denied, or not available
                                            console.warn('[CRISIS] ⚠️ GPS permission denied or unavailable')
                                            console.log('[CRISIS] 🔄 Will fall back to IP-based location')
                                            
                                            if (err.code === 1) {
                                                console.warn('[CRISIS] 📍 User denied GPS permission')
                                            } else if (err.code === 2) {
                                                console.warn('[CRISIS] 📍 Position unavailable (GPS may be blocked)')
                                            } else if (err.code === 3) {
                                                console.warn('[CRISIS] 📍 GPS request timeout')
                                            }
                                            
                                            // Backend should still send IP-based location alert automatically
                                            console.log('[CRISIS] ℹ️ Automatic IP-based fallback being sent from server')
                                        },
                                        { 
                                            enableHighAccuracy: true,  // Request precise GPS
                                            timeout: 8000,              // Wait up to 8 seconds for GPS
                                            maximumAge: 0               // Don't use cached location
                                        }
                                    )
                                } else if (meta.crisis_detected) {
                                    console.warn('[CRISIS] ⚠️ Geolocation not available in this browser/context')
                                    console.log('[CRISIS] 🔄 Will fall back to IP-based location')
                                }
                                // ────────────────────────────────────────────────────────────

                                // Pick all recommended techniques from category dict
                                if (meta.recommended_techniques_by_category) {
                                    const all = Object.values(
                                        meta.recommended_techniques_by_category as Record<string, Technique>
                                    )
                                    if (all.length > 0) {
                                        setActiveTechnique(all[0])
                                        setAlternativeTechniques(all.slice(1))
                                    }
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
        [isStreaming, userId]
    )

    const clearMessages = useCallback((defaultMsg?: Message) => {
        setMessages(defaultMsg ? [defaultMsg] : [])
        setLatestEmotion(null)
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
        latestSentiment,
        activeTechnique,
        alternativeTechniques,
        sendMessage,
        clearMessages,
        setIsStreaming,
    }
}
