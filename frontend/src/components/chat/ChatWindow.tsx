'use client'

import { useEffect, useRef } from 'react'
import { Message } from '@/types'
import { MessageBubble } from './MessageBubble'
import { TypingIndicator } from './TypingIndicator'
import { Sparkles } from 'lucide-react'

interface ChatWindowProps {
  messages: Message[]
  isLoading: boolean
  showTypingIndicator?: boolean
  userId: string
}

export function ChatWindow({ 
  messages, 
  isLoading, 
  showTypingIndicator = false,
  userId 
}: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <div className="flex-1 overflow-y-auto px-5 py-5 custom-scrollbar">
      <div className="max-w-3xl mx-auto space-y-4">
        {messages.map((message, i) => (
          <MessageBubble key={i} message={message} />
        ))}

        {/* Elegant Typing Indicator */}
        {(showTypingIndicator || isLoading) && (
          <div className="flex w-full justify-start items-end gap-3 animate-slide-up mb-2">
            {/* Assistant Avatar for Typing */}
            <div className="w-9 h-9 rounded-full bg-gradient-to-br from-purple-brand via-purple-500 to-teal-brand flex items-center justify-center shrink-0 border border-white/20 shadow-[0_4px_12px_rgba(124,58,237,0.25)]">
              <Sparkles className="w-4 h-4 text-white" />
            </div>
            
            {/* Glassmorphism Typing Pill */}
            <TypingIndicator message={showTypingIndicator ? "Thinking" : "Processing"} />
          </div>
        )}

        <div ref={bottomRef} className="h-4" />
      </div>
    </div>
  )
}
