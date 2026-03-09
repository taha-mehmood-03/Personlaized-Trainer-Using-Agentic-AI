import React, { useState, useRef, useEffect, useCallback } from 'react'
import { Send, Menu, Plus, Sparkles, Heart, Brain, MessageCircle, Loader, History, Mic, MicOff, Pencil, Check, X, Settings } from 'lucide-react'
import HistoryPage from './HistoryPage'
import TechniqueCard from './TechniqueCard'
import CategoryTechniqueDisplay from './CategoryTechniqueDisplay'
import VoiceIndicator from './VoiceIndicator'

import SessionPanel from './SessionPanel'

const API_URL = 'http://localhost:8000/api'

// Helper function to convert AudioBuffer to WAV
function audioBufferToWav(audioBuffer) {
  const numberOfChannels = audioBuffer.numberOfChannels
  const sampleRate = audioBuffer.sampleRate
  const format = 1 // PCM
  const bitDepth = 16

  const bytesPerSample = bitDepth / 8
  const blockAlign = numberOfChannels * bytesPerSample

  const channelData = []
  for (let i = 0; i < numberOfChannels; i++) {
    channelData.push(audioBuffer.getChannelData(i))
  }

  // Calculate file size
  const dataLength = audioBuffer.length * numberOfChannels * bytesPerSample
  const fileLength = 36 + dataLength
  const arrayBuffer = new ArrayBuffer(44 + dataLength)
  const view = new DataView(arrayBuffer)

  // Write WAV header
  const writeString = (offset, string) => {
    for (let i = 0; i < string.length; i++) {
      view.setUint8(offset + i, string.charCodeAt(i))
    }
  }

  writeString(0, 'RIFF')
  view.setUint32(4, fileLength, true)
  writeString(8, 'WAVE')
  writeString(12, 'fmt ')
  view.setUint32(16, 16, true) // fmt chunk size
  view.setUint16(20, format, true)
  view.setUint16(22, numberOfChannels, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * blockAlign, true)
  view.setUint16(32, blockAlign, true)
  view.setUint16(34, bitDepth, true)
  writeString(36, 'data')
  view.setUint32(40, dataLength, true)

  // Write audio data
  let offset = 44
  for (let i = 0; i < audioBuffer.length; i++) {
    for (let channel = 0; channel < numberOfChannels; channel++) {
      const sample = Math.max(-1, Math.min(1, channelData[channel][i]))
      const int16 = sample < 0 ? sample * 0x8000 : sample * 0x7FFF
      view.setInt16(offset, int16, true)
      offset += 2
    }
  }

  return arrayBuffer
}

// Memoized message component for performance
const MessageBubble = React.memo(({ message, index }) => {
  const isAssistant = message.role === 'assistant'

  return (
    <div key={index} className={`flex ${isAssistant ? 'justify-start' : 'justify-end'} animate-slide-up`}>
      <div className={`max-w-xl px-5 py-3 rounded-2xl ${isAssistant
        ? 'bg-white text-gray-800 border-2 border-gray-200 shadow-sm'
        : 'bg-gradient-to-br from-purple-500 to-teal-500 text-white shadow-md'
        }`}>
        <p className="text-sm leading-relaxed whitespace-pre-wrap">
          {message.content}
          {/* Blinking cursor while streaming */}
          {message._streaming && (
            <span className="inline-block w-0.5 h-4 bg-purple-500 ml-0.5 animate-pulse align-middle" />
          )}
        </p>
        {isAssistant && message.emotion && !message._streaming && (
          <div className="mt-2 text-xs text-gray-500 flex items-center gap-2">
            <span>💭 Detected: {message.emotion}</span>
          </div>
        )}
        {!isAssistant && message.voiceEmotion && (
          <div className="mt-2 text-xs text-purple-200 flex items-center gap-2">
            <span>🎤 Voice emotion: {message.voiceEmotion} ({(message.voiceConfidence * 100).toFixed(0)}%)</span>
          </div>
        )}
      </div>
    </div>
  )
})

export default function SentiMindChat() {
  // States
  // ── Restore persisted messages from localStorage (survives page refresh) ──
  const _restoredMessages = (() => {
    try {
      const saved = localStorage.getItem('sentimind_messages')
      if (saved) {
        const parsed = JSON.parse(saved)
        if (Array.isArray(parsed) && parsed.length > 0) return parsed
      }
    } catch { /* ignore corrupt storage */ }
    return null
  })()

  const [messages, setMessages] = useState(
    _restoredMessages ?? [
      {
        role: 'assistant',
        content: "👋 Hello! I'm SentiMind, your AI wellness companion. I'm here to listen, understand, and help you feel better. You can chat with me or use voice messages. How are you feeling today?",
      }
    ]
  )
  const [input, setInput] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [isLoading, setIsLoading] = useState(false)
  const [moodData, setMoodData] = useState(null)
  const [chatHistory, setChatHistory] = useState([])
  const [userId, setUserId] = useState(null)
  const [currentSessionId, setCurrentSessionId] = useState(
    localStorage.getItem('sentimind_session_id') || null
  )
  const [isRecording, setIsRecording] = useState(false)
  const [voiceEmotion, setVoiceEmotion] = useState(null)
  const [voiceConfidence, setVoiceConfidence] = useState(0)
  const [acousticFeatures, setAcousticFeatures] = useState(null)
  const [loadingSessions, setLoadingSessions] = useState(false)
  const [showHistory, setShowHistory] = useState(false)

  // Refs
  const messagesEndRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const audioChunksRef = useRef([])
  const streamRef = useRef(null)
  const onStopHandlerRef = useRef(null)
  const recorderMimeTypeRef = useRef('audio/webm')

  // Persist chat messages + session to localStorage on every change
  useEffect(() => {
    try {
      // Only save non-streaming (finalized) messages to avoid saving incomplete bubbles
      const toSave = messages.filter(m => !m._streaming)
      localStorage.setItem('sentimind_messages', JSON.stringify(toSave))
    } catch { /* storage full or unavailable */ }
  }, [messages])

  useEffect(() => {
    if (currentSessionId) {
      localStorage.setItem('sentimind_session_id', currentSessionId)
    }
  }, [currentSessionId])

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Update onstop handler with current state
  useEffect(() => {
    onStopHandlerRef.current = async () => {
      console.log('[VOICE] 🛑 MediaRecorder stopped, creating blob...')
      const mimeType = recorderMimeTypeRef.current || 'audio/webm'
      let audioBlob = new Blob(audioChunksRef.current, { type: mimeType })
      console.log('[VOICE] 📦 Audio blob created:', audioBlob.size, 'bytes, type:', mimeType)
      audioChunksRef.current = []

      // Convert WebM to WAV on the frontend to avoid ffmpeg dependency on backend
      if (mimeType.includes('webm') || mimeType.includes('mp4') || mimeType.includes('ogg')) {
        console.log('[VOICE] 🔄 Converting audio format on frontend...')
        try {
          // Use Web Audio API to decode and re-encode as WAV
          const audioContext = new (window.AudioContext || window.webkitAudioContext)()
          const arrayBuffer = await audioBlob.arrayBuffer()
          const audioBuffer = await audioContext.decodeAudioData(arrayBuffer)

          // Convert AudioBuffer to WAV
          const wav = audioBufferToWav(audioBuffer)
          audioBlob = new Blob([wav], { type: 'audio/wav' })
          console.log('[VOICE] ✅ Converted to WAV:', audioBlob.size, 'bytes')
        } catch (err) {
          console.warn('[VOICE] ⚠️ Frontend conversion failed, will try backend:', err)
          // If frontend conversion fails, send as-is and let backend try
        }
      }

      if (!userId) {
        console.error('[VOICE] User ID missing')
        alert('User not initialized. Please refresh the page.')
        return
      }

      let sessionId = currentSessionId

      if (!sessionId) {
        console.log('[VOICE] No session, creating new one...')
        try {
          const sessionResponse = await fetch(`${API_URL}/session/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId })
          })

          if (sessionResponse.ok) {
            const sessionData = await sessionResponse.json()
            sessionId = sessionData.session_id
            setCurrentSessionId(sessionId)
            console.log('[VOICE] ✅ Created new session:', sessionId)
          } else {
            throw new Error('Failed to create session')
          }
        } catch (error) {
          console.error('[VOICE] Error creating session:', error)
          setMessages(prev => [...prev, {
            role: 'assistant',
            content: "Sorry, failed to create session. Please try text message first."
          }])
          return
        }
      }

      try {
        setIsLoading(true)

        const formData = new FormData()
        formData.append('audio', audioBlob, 'voice.wav')
        formData.append('user_id', userId)
        // IMPORTANT: Send empty message for voice - let backend use transcription from audio
        formData.append('message', '')
        formData.append('session_id', sessionId)

        console.log('[VOICE] 📤 Sending voice message...', { userId, sessionId, audioSize: audioBlob.size })

        const response = await fetch(`${API_URL}/chat/voice`, {
          method: 'POST',
          body: formData
        })

        if (!response.ok) {
          throw new Error(`Voice analysis failed: ${response.statusText}`)
        }

        const data = await response.json()
        console.log('[VOICE] ✅ Response received:', data)

        if (data.voice_emotion && data.voice_emotion.emotion) {
          setVoiceEmotion(data.voice_emotion.emotion)
          setVoiceConfidence(data.voice_emotion.confidence || 0)
          setAcousticFeatures(data.voice_emotion.acoustic_features || null)
          console.log(`🎤 Voice detected: ${data.voice_emotion.emotion} (confidence: ${data.voice_emotion.confidence})`)
        }

        const newUserMessage = {
          role: 'user',
          content: data.transcription || input || '(voice message)',
          voiceEmotion: data.voice_emotion?.emotion,
          voiceConfidence: data.voice_emotion?.confidence
        }

        const assistantMessage = {
          role: 'assistant',
          content: data.response || data.message || "I'm listening...",
          emotion: data.emotion || 'neutral'
        }

        setMessages(prev => [...prev, newUserMessage, assistantMessage])
        setInput('')
        setMoodData(data.mood || null)
      } catch (error) {
        console.error('[VOICE] Voice message error:', error)
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: "Sorry, voice analysis failed. Please try text instead."
        }])
      } finally {
        setIsLoading(false)
      }
    }
  }, [userId, currentSessionId, input])

  // Initialize app
  useEffect(() => {
    const initializeApp = async () => {
      const userIdToUse = await initializeUser()
      if (userIdToUse) {
        // If we restored from localStorage, skip remote history load to avoid
        // overwriting the rich technique-card data we already have.
        const hasRestoredSession = Boolean(_restoredMessages)
        if (!hasRestoredSession) {
          loadChatHistory(userIdToUse)
        }
        loadAllSessions(userIdToUse)
      }
    }
    initializeApp()

    // Cleanup on unmount
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop())
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
        mediaRecorderRef.current.stop()
      }
    }
  }, [])

  // Initialize voice recording using MediaRecorder
  const initializeVoiceRecording = useCallback(async () => {
    console.log('[VOICE] 🔧 Initializing voice recording...')

    try {
      // Check browser support
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error('Your browser does not support microphone access')
      }

      console.log('[VOICE] 🔐 Requesting microphone permission...')

      // Use basic audio constraints first
      let stream
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: false
          }
        })
      } catch (e) {
        console.warn('[VOICE] ⚠️ Advanced constraints failed, using basic:', e.message)
        // Fallback to basic audio without constraints
        stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      }

      console.log('[VOICE] ✅ Microphone permission granted')
      console.log('[VOICE] 📡 Stream tracks:', stream.getTracks().length, stream.getTracks().map(t => `${t.kind}:${t.enabled}`))
      streamRef.current = stream

      // Try different MIME types in order of preference
      const mimeTypes = [
        'audio/webm',
        'audio/webm;codecs=opus',
        'audio/mp4',
        'audio/ogg;codecs=opus',
        'audio/wav',
      ]

      let selectedMimeType = ''
      for (const mimeType of mimeTypes) {
        const supported = MediaRecorder.isTypeSupported(mimeType)
        console.log(`[VOICE] 🔍 MIME type "${mimeType}": ${supported}`)
        if (supported) {
          selectedMimeType = mimeType
          console.log('[VOICE] 📝 Selected MIME type:', mimeType)
          break
        }
      }

      let mediaRecorder
      try {
        // Try with selected MIME type if available, otherwise let browser choose
        if (selectedMimeType) {
          console.log('[VOICE] 🎙️ Creating MediaRecorder with MIME:', selectedMimeType)
          mediaRecorder = new MediaRecorder(stream, { mimeType: selectedMimeType })
        } else {
          console.log('[VOICE] 🎙️ Creating MediaRecorder with default MIME')
          mediaRecorder = new MediaRecorder(stream)
        }
      } catch (e) {
        console.warn('[VOICE] ⚠️ Failed to create with selected type, trying default:', e.message)
        mediaRecorder = new MediaRecorder(stream)
      }

      console.log('[VOICE] 📝 MediaRecorder created:', mediaRecorder.mimeType || 'default')
      // Store the MIME type for later use
      recorderMimeTypeRef.current = mediaRecorder.mimeType || 'audio/webm'
      audioChunksRef.current = []

      mediaRecorder.ondataavailable = (event) => {
        console.log('[VOICE] 📊 Data available:', event.data.size, 'bytes, type:', event.data.type)
        audioChunksRef.current.push(event.data)
      }

      mediaRecorder.onerror = (event) => {
        console.error('[VOICE] ❌ MediaRecorder error:', event.error)
      }

      mediaRecorder.onstop = async () => {
        if (onStopHandlerRef.current) {
          await onStopHandlerRef.current()
        }
      }

      mediaRecorderRef.current = mediaRecorder
      console.log('[VOICE] ✅ Voice recording initialized successfully')
      return true

    } catch (error) {
      console.error('[VOICE] ❌ Initialization error:', error.message || error)
      alert(`Microphone error: ${error.message}\n\nPlease:\n1. Check microphone permissions\n2. Ensure HTTPS (not HTTP)\n3. Try a different browser`)
      return false
    }
  }, [])

  // User initialization
  const initializeUser = useCallback(async () => {
    try {
      let storedUserId = localStorage.getItem('sentimind_user_id')
      const isValidStoredId = storedUserId && storedUserId !== 'undefined' && storedUserId !== 'null'
      let userId = isValidStoredId ? storedUserId : "anonymous"

      if (!isValidStoredId) {
        localStorage.setItem('sentimind_user_id', userId)
      }

      const response = await fetch(`${API_URL}/user/ensure`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, message: '' })
      })

      if (response.ok) {
        setUserId(userId)
        return userId
      }
    } catch (error) {
      console.error('Error initializing user:', error)
    }
    setUserId("anonymous")
    return "anonymous"
  }, [])

  // Load chat history
  const loadChatHistory = useCallback(async (userIdToLoad) => {
    if (!userIdToLoad) return

    try {
      const response = await fetch(`${API_URL}/user/${userIdToLoad}/sessions?limit=1`)
      const data = await response.json()

      if (data.sessions?.[0]?.messages?.length > 0) {
        const lastSession = data.sessions[0]
        const loadedMessages = lastSession.messages.map(msg => ({
          role: msg.role.toLowerCase(),
          content: msg.content,
          emotion: msg.emotion,
          sentiment: msg.sentiment,
          timestamp: msg.createdAt,
          technique: msg.technique || null
        }))

        setMessages(loadedMessages)
        setCurrentSessionId(lastSession.id)
      }
    } catch (error) {
      console.error('Error loading chat history:', error)
    }
  }, [])

  // Load all sessions
  const loadAllSessions = useCallback(async (userIdToLoad) => {
    if (!userIdToLoad) return

    try {
      setLoadingSessions(true)
      const response = await fetch(`${API_URL}/user/${userIdToLoad}/sessions?limit=50`)
      const data = await response.json()
      setChatHistory(data.sessions || [])
    } catch (error) {
      console.error('Error loading sessions:', error)
      setChatHistory([])
    } finally {
      setLoadingSessions(false)
    }
  }, [])

  // Load specific session
  const loadSession = useCallback((sessionId) => {
    const session = chatHistory.find(s => s.id === sessionId)
    if (session?.messages?.length > 0) {
      const loadedMessages = session.messages.map(msg => ({
        role: msg.role.toLowerCase(),
        content: msg.content,
        emotion: msg.emotion,
        timestamp: msg.createdAt,
        technique: msg.technique || null
      }))
      setMessages(loadedMessages)
      setCurrentSessionId(sessionId)

    }
  }, [chatHistory])

  // Handle send message — uses streaming endpoint for instant word-by-word response
  const handleSend = useCallback(async () => {
    if (!input.trim() || isLoading || !userId) return

    const userMessage = input.trim()
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: userMessage }])
    setIsLoading(true)

    // Placeholder message that we'll update token-by-token
    const streamingId = Date.now()
    setMessages(prev => [...prev, {
      role: 'assistant',
      content: '',
      _streamingId: streamingId,
      _streaming: true
    }])

    try {
      const response = await fetch(`${API_URL}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          message: userMessage,
          session_id: currentSessionId
        })
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      // Clear the "Thinking..." spinner as soon as we start streaming
      setIsLoading(false)

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() // keep incomplete line in buffer

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const jsonStr = line.slice(6).trim()
          if (!jsonStr) continue

          try {
            const event = JSON.parse(jsonStr)

            if (event.type === 'token') {
              // Append token to the streaming message bubble
              setMessages(prev => prev.map(msg =>
                msg._streamingId === streamingId
                  ? { ...msg, content: msg.content + event.content }
                  : msg
              ))
            } else if (event.type === 'done') {
              // Finalize the message with metadata
              setMessages(prev => prev.map(msg =>
                msg._streamingId === streamingId
                  ? {
                    ...msg,
                    _streaming: false,
                    emotion: event.emotion,
                    sentiment: event.sentiment,
                    crisis_detected: event.crisis_detected,
                    recommendedTechniquesByCategory: event.recommended_techniques_by_category || {},
                    tools_used: event.tools_used || []
                  }
                  : msg
              ))

              setMoodData({
                emotion: event.emotion,
                sentiment: event.sentiment,
                textEmotion: event.emotion
              })

              if (!currentSessionId && event.session_id) {
                setCurrentSessionId(event.session_id)
              }
            } else if (event.type === 'error') {
              setMessages(prev => prev.map(msg =>
                msg._streamingId === streamingId
                  ? { ...msg, content: event.content, _streaming: false }
                  : msg
              ))
            }
          } catch (parseError) {
            // Ignore malformed SSE lines
          }
        }
      }
    } catch (error) {
      console.error('Streaming error:', error)
      setMessages(prev => prev.map(msg =>
        msg._streamingId === streamingId
          ? { ...msg, content: "Sorry, I encountered an error. Please try again.", _streaming: false }
          : msg
      ))
    } finally {
      setIsLoading(false)
    }
  }, [input, isLoading, userId, currentSessionId])

  // Voice recording handlers
  const handleStartRecording = useCallback(async () => {
    try {
      console.log('[VOICE] 🎤 Start recording clicked')

      // Always check if we need to reinitialize (stream might have been stopped)
      if (!mediaRecorderRef.current || !streamRef.current || streamRef.current.getTracks().length === 0) {
        console.log('[VOICE] 🔧 Stream not available or stopped, reinitializing...')
        mediaRecorderRef.current = null
        streamRef.current = null
        await initializeVoiceRecording()
      }

      const recorder = mediaRecorderRef.current
      if (!recorder) {
        throw new Error('MediaRecorder failed to initialize')
      }

      if (recorder.state !== 'inactive') {
        console.warn('[VOICE] ⚠️ Recorder not in inactive state:', recorder.state)
        return
      }

      console.log('[VOICE] 🔴 Starting recording...')
      audioChunksRef.current = []

      // Debug: check stream tracks
      const streamTracks = streamRef.current?.getTracks() || []
      console.log('[VOICE] 📡 Stream tracks:', streamTracks.length, streamTracks.map(t => t.kind))

      recorder.start()
      setIsRecording(true)
      console.log('[VOICE] ✅ Recording started')

    } catch (error) {
      console.error('[VOICE] ❌ Error:', error.message || error)
      alert('Failed to start recording: ' + (error.message || 'Unknown error'))
      setIsRecording(false)
    }
  }, [initializeVoiceRecording])

  const handleStopRecording = useCallback(() => {
    console.log('[VOICE] ⏹️ Stop recording clicked')
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      try {
        mediaRecorderRef.current.stop()
        setIsRecording(false)
        console.log('[VOICE] ✅ Recording stopped')
      } catch (error) {
        console.error('[VOICE] ❌ Error stopping recording:', error)
      }
    } else {
      console.warn('[VOICE] ⚠️ No active recording to stop', {
        exists: !!mediaRecorderRef.current,
        state: mediaRecorderRef.current?.state
      })
    }
  }, [])

  // Handle new session — clear localStorage so old exercises don't bleed in
  const handleNewSession = useCallback(() => {
    localStorage.removeItem('sentimind_messages')
    localStorage.removeItem('sentimind_session_id')
    setMessages([{
      role: 'assistant',
      content: "👋 Hello! I'm SentiMind. How are you feeling today?"
    }])
    setCurrentSessionId(null)
    setVoiceEmotion(null)
  }, [])

  // Handle select session
  const handleSelectSession = useCallback((sessionId) => {
    loadSession(sessionId)
  }, [loadSession])

  // Delete session
  const handleDeleteSession = useCallback(async (sessionId) => {
    try {
      const response = await fetch(`${API_URL}/session/${sessionId}`, {
        method: 'DELETE'
      })
      if (response.ok) {
        setChatHistory(prev => prev.filter(s => s.id !== sessionId))
        if (currentSessionId === sessionId) {
          handleNewSession()
        }
      }
    } catch (error) {
      console.error('Error deleting session:', error)
    }
  }, [currentSessionId, handleNewSession])

  // Rename session
  const handleRenameSession = useCallback(async (sessionId, newTitle) => {
    try {
      const response = await fetch(`${API_URL}/session/${sessionId}/rename`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newTitle })
      })
      if (response.ok) {
        setChatHistory(prev => prev.map(s =>
          s.id === sessionId ? { ...s, title: newTitle } : s
        ))
      }
    } catch (error) {
      console.error('Error renaming session:', error)
    }
  }, [])

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        handleSend()
      }
      if (e.key === 'Escape') {
        setSidebarOpen(false)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleSend])

  // Show history page if requested
  if (showHistory && userId) {
    return <HistoryPage userId={userId} onBack={() => setShowHistory(false)} />
  }

  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden">
      {/* Sidebar */}
      <div className={`${sidebarOpen ? 'w-72' : 'w-0'} bg-white border-r border-gray-200 transition-all duration-300 flex flex-col overflow-hidden shadow-lg`}>
        <SessionPanel
          sessions={chatHistory}
          currentSessionId={currentSessionId}
          onNewSession={handleNewSession}
          onSelectSession={handleSelectSession}
          onDeleteSession={handleDeleteSession}
          onRenameSession={handleRenameSession}
          isLoading={loadingSessions}
        />
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <div className="bg-white border-b border-gray-200 px-6 py-4 shadow-sm">
          <div className="max-w-6xl mx-auto flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <Menu className="w-6 h-6 text-gray-700" />
              </button>
              <div>
                <h1 className="text-2xl font-bold bg-gradient-to-r from-purple-600 to-teal-600 bg-clip-text text-transparent">
                  SentiMind
                </h1>
                <p className="text-xs text-gray-500">AI Mental Health Companion</p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                <span>Online</span>
              </div>
            </div>
          </div>
        </div>

        {/* Messages Area */}
        <div className="flex-1 overflow-y-auto px-6 py-6">
          <div className="max-w-4xl mx-auto space-y-4">


            {/* Messages Stream */}
            {messages.map((message, index) => (
              <React.Fragment key={index}>
                <MessageBubble message={message} index={index} />

                {/* Render category technique display with the message */}
                {message.role === 'assistant' && message.recommendedTechniquesByCategory &&
                  Object.keys(message.recommendedTechniquesByCategory).length > 0 && (
                    <CategoryTechniqueDisplay
                      techniquesByCategory={message.recommendedTechniquesByCategory}
                      userId={userId}
                    />
                  )}
              </React.Fragment>
            ))}

            {isLoading && (
              <div className="flex justify-start animate-slide-up">
                <div className="flex gap-3 items-center">
                  <div className="flex-shrink-0 w-10 h-10 rounded-full bg-gradient-to-br from-purple-500 to-teal-500 flex items-center justify-center">
                    <Loader className="w-5 h-5 text-white animate-spin" />
                  </div>
                  <div className="px-5 py-3 rounded-2xl bg-white text-gray-800 border-2 border-gray-200 shadow-sm">
                    <p className="text-sm">Thinking...</p>
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input Area */}
        <div className="bg-white border-t border-gray-200 px-6 py-4 shadow-lg">
          <div className="max-w-4xl mx-auto space-y-4">
            {/* Voice Indicator */}
            {(isRecording || voiceEmotion) && (
              <VoiceIndicator
                isRecording={isRecording}
                voiceEmotion={voiceEmotion}
                voiceConfidence={voiceConfidence}
                acousticFeatures={acousticFeatures}
                onStartRecording={handleStartRecording}
                onStopRecording={handleStopRecording}
              />
            )}

            {/* Text Input */}
            <div className="flex gap-3 items-end">
              <div className="flex-1 relative">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyPress={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      handleSend()
                    }
                  }}
                  placeholder="Share how you're feeling... or use voice"
                  className="w-full px-5 py-4 bg-white border-2 border-gray-200 rounded-2xl focus:outline-none focus:border-purple-400 focus:ring-2 focus:ring-purple-100 resize-none transition-all text-gray-700 placeholder-gray-400"
                  rows="1"
                  style={{ minHeight: '56px', maxHeight: '200px' }}
                />
              </div>

              <button
                onClick={isRecording ? handleStopRecording : handleStartRecording}
                className={`p-3 rounded-2xl transition-all ${isRecording
                  ? 'bg-red-500 text-white animate-recording-pulse shadow-lg shadow-red-500/50'
                  : 'bg-cyan-500 text-white hover:bg-cyan-600 hover:shadow-lg'
                  }`}
              >
                {isRecording ? (
                  <MicOff className="w-5 h-5" />
                ) : (
                  <Mic className="w-5 h-5" />
                )}
              </button>

              <button
                onClick={handleSend}
                disabled={!input.trim() || isLoading}
                className="p-3 bg-gradient-to-br from-purple-500 to-teal-500 text-white rounded-2xl hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed transition-all hover:scale-105 active:scale-95"
              >
                {isLoading ? (
                  <Loader className="w-5 h-5 animate-spin" />
                ) : (
                  <Send className="w-5 h-5" />
                )}
              </button>
            </div>

            <p className="text-xs text-gray-500 text-center">
              💡 For emergencies, please contact a mental health professional immediately
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
