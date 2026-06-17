'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import dynamic from 'next/dynamic'
import { PanelLeftClose, PanelLeftOpen } from 'lucide-react'

import { Message, Session, Technique } from '@/types'
import { useChat } from '@/hooks/useChat'
import { useStream } from '@/hooks/useStream'
import { getSessionMessages } from '@/actions/chat'

import { ChatHeader } from '@/components/chat/ChatHeader'
import { ChatWindow } from '@/components/chat/ChatWindow'
import { ChatInput } from '@/components/chat/ChatInput'
import { cleanEmotionLabel } from '@/lib/chatEmotion'

const Sidebar = dynamic(
  () => import('@/components/layout/Sidebar').then((mod) => mod.Sidebar),
  {
    ssr: false,
    loading: () => <div className="h-full rounded-2xl border border-slate-200 bg-white" />,
  }
)

const TechniquePanel = dynamic(
  () => import('@/components/layout/TechniquePanel').then((mod) => mod.TechniquePanel),
  { ssr: false }
)

interface ChatLayoutProps {
  userId: string
  userName?: string | null
  userEmail?: string | null
  initialSessions: Session[]
  initialMessages: Message[]
  initialSessionId: string | null
  children?: React.ReactNode
}

const WELCOME_MESSAGE: Message = {
  role: 'assistant',
  content: "Hi, I'm SentiMind. I'm here to understand what is going on first, then support you at a pace that fits. What would you like to talk through today?",
}

function useDesktopViewport() {
  const [isDesktop, setIsDesktop] = useState(false)

  useEffect(() => {
    const media = window.matchMedia('(min-width: 1024px)')
    const update = () => setIsDesktop(media.matches)
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])

  return isDesktop
}

export function ChatLayout({
  userId,
  userName,
  userEmail,
  initialSessions,
  initialMessages,
  initialSessionId,
}: ChatLayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const isDesktop = useDesktopViewport()

  const {
    sessions,
    currentSessionId,
    loadingSessions,
    refreshSessions,
    startNewSession,
    selectSession,
    removeSession,
    updateSessionName,
    setCurrentSessionId,
  } = useChat(userId, initialSessions)

  const {
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
  } = useStream(userId)

  const [displayedTechnique, setDisplayedTechnique] = useState<Technique | null>(null)
  const [displayedAlternatives, setDisplayedAlternatives] = useState<Technique[]>([])
  const selectedSessionRef = useRef<string | null>(initialSessionId)
  const hasInitializedSessionsRef = useRef(initialSessions.length > 0)
  const latestTrackedMessage = useMemo(
    () =>
      [...messages].reverse().find(
        (message) =>
          cleanEmotionLabel(message.emotion) ||
          cleanEmotionLabel(message.emotionLabel) ||
          cleanEmotionLabel(message.emotion_label) ||
          cleanEmotionLabel(message.primarySubEmotion) ||
          cleanEmotionLabel(message.primary_sub_emotion) ||
          cleanEmotionLabel(message.sentiment)
      ),
    [messages]
  )
  const headerEmotion =
    cleanEmotionLabel(latestTrackedMessage?.emotion) ??
    cleanEmotionLabel(latestTrackedMessage?.emotionLabel) ??
    cleanEmotionLabel(latestTrackedMessage?.emotion_label) ??
    cleanEmotionLabel(latestEmotion)
  const headerSubEmotion =
    cleanEmotionLabel(latestTrackedMessage?.primarySubEmotion) ??
    cleanEmotionLabel(latestTrackedMessage?.primary_sub_emotion) ??
    cleanEmotionLabel(latestSubEmotion)
  const headerSentiment = cleanEmotionLabel(latestTrackedMessage?.sentiment) ?? cleanEmotionLabel(latestSentiment)

  useEffect(() => {
    hasInitializedSessionsRef.current = initialSessions.length > 0
  }, [initialSessions.length, userId])

  useEffect(() => {
    if (activeTechnique) {
      setDisplayedTechnique(activeTechnique)
      setDisplayedAlternatives(alternativeTechniques)
    }
  }, [activeTechnique, alternativeTechniques])

  useEffect(() => {
    if (!isDesktop || sessions.length > 0 || loadingSessions || hasInitializedSessionsRef.current) return
    hasInitializedSessionsRef.current = true
    void refreshSessions().catch((error) => {
      console.error('[ChatLayout] Failed to load sessions:', error)
    })
  }, [isDesktop, loadingSessions, refreshSessions, sessions.length])

  useEffect(() => {
    if (initialMessages.length > 0) {
      setMessages(initialMessages)
    } else {
      clearMessages(WELCOME_MESSAGE)
    }
    if (initialSessionId) {
      selectedSessionRef.current = initialSessionId
      setCurrentSessionId(initialSessionId)
    }
  }, [initialMessages, initialSessionId, setMessages, clearMessages, setCurrentSessionId])

  const handleSessionCreated = useCallback(
    (sid: string) => {
      selectedSessionRef.current = sid
      setCurrentSessionId(sid)
      refreshSessions()
    },
    [refreshSessions, setCurrentSessionId]
  )

  const handleSend = useCallback(
    (text: string, audioData?: string) => {
      sendMessage(text, currentSessionId, handleSessionCreated, audioData)
    },
    [currentSessionId, handleSessionCreated, sendMessage]
  )

  const handleSelectSession = useCallback(
    async (id: string) => {
      selectedSessionRef.current = id
      selectSession(id)
      const session = sessions.find((item) => item.id === id)
      if (session && session.messages.length) {
        setMessages(session.messages as Message[])
        const lastTechniqueMessage = [...session.messages].reverse().find(
          (message) => message.role === 'assistant' && message.technique
        )
        setDisplayedTechnique(lastTechniqueMessage?.technique ?? null)
        setDisplayedAlternatives([])
        return
      }

      const fetchedMessages = await getSessionMessages(id, userId)
      if (selectedSessionRef.current !== id) return
      setMessages(fetchedMessages.length ? fetchedMessages : [WELCOME_MESSAGE])
      const lastTechniqueMessage = [...fetchedMessages].reverse().find(
        (message) => message.role === 'assistant' && message.technique
      )
      setDisplayedTechnique(lastTechniqueMessage?.technique ?? null)
      setDisplayedAlternatives([])
    },
    [selectSession, sessions, setMessages, userId]
  )

  const handleNewSession = useCallback(() => {
    selectedSessionRef.current = null
    startNewSession()
    clearMessages(WELCOME_MESSAGE)
    setDisplayedTechnique(null)
    setDisplayedAlternatives([])
  }, [clearMessages, startNewSession])

  const handleDeleteSession = useCallback(
    async (id: string) => {
      const wasCurrentSession = id === currentSessionId
      await removeSession(id)
      if (wasCurrentSession) {
        selectedSessionRef.current = null
        clearMessages(WELCOME_MESSAGE)
        setDisplayedTechnique(null)
        setDisplayedAlternatives([])
      }
    },
    [clearMessages, currentSessionId, removeSession]
  )

  const currentMessages = messages
  const currentDisplayedTechnique = displayedTechnique
  const currentDisplayedAlternatives = displayedAlternatives

  const handleRenameSession = useCallback(
    (id: string, title: string) => updateSessionName(id, title),
    [updateSessionName]
  )

  const techniquePanel = useMemo(() => {
    return null
  }, [])

  const chatWindow = useMemo(
    () => (
      <ChatWindow
        messages={currentMessages}
        isLoading={isStreaming}
        showTypingIndicator={showTypingIndicator}
      />
    ),
    [currentMessages, isStreaming, showTypingIndicator]
  )

  return (
      <div className="flex min-h-0 flex-1 gap-3 overflow-hidden p-2 sm:p-3">
        {isDesktop && (
          <aside className={`${sidebarOpen ? 'lg:w-72' : 'lg:w-0'} hidden shrink-0 overflow-hidden transition-all duration-300 lg:block`}>
            <Sidebar
              sessions={sessions}
              currentSessionId={currentSessionId}
              isLoading={loadingSessions}
              activeTechnique={displayedTechnique}
              userName={userName}
              userEmail={userEmail}
              onNewSession={handleNewSession}
            onSelectSession={handleSelectSession}
            onDeleteSession={handleDeleteSession}
            onRenameSession={handleRenameSession}
          />
          </aside>
        )}

        <section className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="flex shrink-0 items-center gap-2 border-b border-slate-200 bg-white px-3">
            <button
              onClick={() => setSidebarOpen((open) => !open)}
              className="hidden rounded-xl p-2 text-slate-600 transition-colors hover:bg-slate-100 lg:inline-flex"
              title={sidebarOpen ? 'Hide sessions' : 'Show sessions'}
            >
              {sidebarOpen ? <PanelLeftClose className="h-5 w-5" /> : <PanelLeftOpen className="h-5 w-5" />}
            </button>
            <div className="flex-1">
              <ChatHeader
                emotion={headerEmotion}
                subEmotion={headerSubEmotion}
                sentiment={headerSentiment}
                messageCount={messages.length}
                isStreaming={isStreaming}
                hasTechnique={Boolean(displayedTechnique)}
              />
            </div>
          </div>

          {chatWindow}

          <ChatInput
            isLoading={isStreaming}
            postCrisisSafetyCheck={postCrisisSafetyCheck}
            onSend={handleSend}
          />
        </section>

        {techniquePanel}
      </div>
  )
}
