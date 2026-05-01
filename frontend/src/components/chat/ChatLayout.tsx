'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { Menu } from 'lucide-react'

import { Message, Session, Technique, VoiceResult } from '@/types'
import { useChat } from '@/hooks/useChat'
import { useStream } from '@/hooks/useStream'

import { CrisisBanner } from '@/components/crisis/CrisisBanner'
import { Sidebar } from '@/components/layout/Sidebar'
import { ChatHeader } from '@/components/chat/ChatHeader'
import { ChatWindow } from '@/components/chat/ChatWindow'
import { ChatInput } from '@/components/chat/ChatInput'
import { VoiceIndicator } from '@/components/chat/VoiceIndicator'
import { TechniquePanel } from '@/components/layout/TechniquePanel'
import { LocationConsentModal } from '@/components/crisis/LocationConsentModal'

interface ChatLayoutProps {
  userId: string
  initialSessions: Session[]
  initialMessages: Message[]
  initialSessionId: string | null
  children?: React.ReactNode // Next.js layout children
}

const WELCOME_MESSAGE: Message = {
  role: 'assistant',
  content: "👋 Hello! I'm SentiMind, your AI wellness companion. I'm here to listen and support you. How are you feeling today?",
}

export function ChatLayout({ userId, initialSessions, initialMessages, initialSessionId, children }: ChatLayoutProps) {
  const [isConsentComplete, setIsConsentComplete] = useState(false)

  // Extract state management to custom hooks
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
    latestSentiment,
    activeTechnique,
    alternativeTechniques,
    sendMessage,
    clearMessages,
  } = useStream(userId)

  // Track the technique to display in the Resources panel
  // - Comes from live streaming (activeTechnique) OR from historical session messages
  const [displayedTechnique, setDisplayedTechnique] = useState<Technique | null>(null)
  const [displayedAlternatives, setDisplayedAlternatives] = useState<Technique[]>([])

  // Sync live streaming technique into Resources panel
  useEffect(() => {
    if (activeTechnique) {
      setDisplayedTechnique(activeTechnique)
      setDisplayedAlternatives(alternativeTechniques)
    }
  }, [activeTechnique, alternativeTechniques])

  const [sidebarOpen, setSidebarOpen] = useState(true)

  // Initialization overrides
  useEffect(() => {
    if (initialMessages.length > 0) {
      setMessages(initialMessages)
    } else {
      clearMessages(WELCOME_MESSAGE)
    }
    if (initialSessionId) {
      setCurrentSessionId(initialSessionId)
    }
  }, [initialMessages, initialSessionId, setMessages, clearMessages, setCurrentSessionId])

  const handleSend = (text: string, audioData?: string) => {
    sendMessage(text, currentSessionId, (sid) => {
      setCurrentSessionId(sid)
      refreshSessions()
    }, audioData)
  }

  // Handle sidebar selections overriding local chat messages state
  const handleSelectSession = (id: string) => {
    selectSession(id)
    const s = sessions.find(x => x.id === id)
    if (s && s.messages.length) {
       setMessages(s.messages as Message[])
       // Find the latest technique from this session's assistant messages
       const lastTechMessage = [...s.messages].reverse().find(
         (m) => m.role === 'assistant' && m.technique
       )
       setDisplayedTechnique(lastTechMessage?.technique ?? null)
       setDisplayedAlternatives([])
    }
  }

  return (
    <div className="flex flex-col h-screen w-full overflow-hidden bg-slate-50 relative">
      {!isConsentComplete && (
        <LocationConsentModal onComplete={() => setIsConsentComplete(true)} />
      )}
      
      <CrisisBanner />

      <div className="flex flex-1 overflow-hidden">
        {/* Left Sidebar */}
        <div className={`${sidebarOpen ? 'w-64' : 'w-0'} shrink-0 border-r border-slate-200 bg-white overflow-hidden transition-all duration-300 flex flex-col shadow-sm relative z-20`}>
          <Sidebar
            sessions={sessions}
            currentSessionId={currentSessionId}
            isLoading={loadingSessions}
            onNewSession={() => { startNewSession(); clearMessages(WELCOME_MESSAGE) }}
            onSelectSession={handleSelectSession}
            onDeleteSession={async (id) => {
              await removeSession(id)
              // Always clear chat view + show welcome after any deletion
              clearMessages(WELCOME_MESSAGE)
            }}
            onRenameSession={updateSessionName}
          />
        </div>

        {/* Center: Chat Window */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative z-10 bg-slate-50">
          <div className="bg-white border-b border-slate-100 flex items-center gap-2 px-3 shrink-0">
            <button
              onClick={() => setSidebarOpen(o => !o)}
              className="p-2 hover:bg-slate-100 rounded-lg transition-colors"
            >
              <Menu className="w-5 h-5 text-slate-600" />
            </button>
            <div className="flex-1">
              <ChatHeader emotion={latestEmotion} sentiment={latestSentiment} />
            </div>
          </div>

          <ChatWindow 
            messages={messages} 
            isLoading={isStreaming} 
            showTypingIndicator={showTypingIndicator}
            userId={userId} 
          />

          <ChatInput
            isLoading={isStreaming}
            isRecording={false}
            onSend={handleSend}
            onStartRecording={() => {}}
            onStopRecording={() => {}}
          />
        </div>

        {/* Right Panel */}
        <TechniquePanel technique={displayedTechnique} alternativeTechniques={displayedAlternatives} userId={userId} />
      </div>
    </div>
  )
}
