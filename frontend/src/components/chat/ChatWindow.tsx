'use client'

import { useEffect, useRef } from 'react'
import { Loader } from 'lucide-react'
import { Message } from '@/types'
import { MessageBubble } from './MessageBubble'

interface ChatWindowProps {
  messages: Message[]
  isLoading: boolean
  userId: string
}

export function ChatWindow({ messages, isLoading, userId }: ChatWindowProps) {
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

        {/* Thinking spinner */}
        {isLoading && (
          <div className="flex justify-start items-end gap-2.5 animate-fade-in">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-400 to-teal-400 flex items-center justify-center shrink-0 shadow-sm border border-purple-200">
              <Loader className="w-4 h-4 text-white animate-spin" />
            </div>
            <div className="px-4 py-3 rounded-2xl bg-white border border-slate-200 text-slate-500 text-sm rounded-tl-sm shadow-sm">
              Thinking…
            </div>
          </div>
        )}

        <div ref={bottomRef} className="h-4" />
      </div>
    </div>
  )
}
