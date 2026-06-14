'use client'

import { memo, useEffect, useMemo, useRef } from 'react'
import { Message } from '@/types'
import { MessageBubble } from './MessageBubble'
import { TypingIndicator } from './TypingIndicator'
import { Sparkles } from 'lucide-react'

interface ChatWindowProps {
  messages: Message[]
  isLoading: boolean
  showTypingIndicator?: boolean
}

function ChatWindowComponent({
  messages,
  isLoading,
  showTypingIndicator = false,
}: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const hasMountedRef = useRef(false)
  const messageStats = useMemo(
    () => ({
      userTurns: messages.reduce((count, message) => count + (message.role === 'user' ? 1 : 0), 0),
      techniques: messages.reduce((count, message) => count + (message.technique ? 1 : 0), 0),
    }),
    [messages]
  )

  useEffect(() => {
    bottomRef.current?.scrollIntoView({
      behavior: hasMountedRef.current && !isLoading ? 'smooth' : 'auto',
      block: 'end',
    })
    hasMountedRef.current = true
  }, [messages.length, isLoading])

  return (
    <div className="custom-scrollbar flex-1 overflow-y-auto bg-slate-50 px-4 py-6">
      <div className="mx-auto flex max-w-4xl flex-col gap-4">
        <div className="mb-2 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">Session focus</p>
              <h2 className="mt-1 text-base font-black text-slate-900">Understand first, then support</h2>
            </div>
            <div className="grid grid-cols-3 gap-2 text-center text-xs">
              <div className="rounded-lg bg-slate-50 px-3 py-2">
                <p className="font-black text-slate-900">{messageStats.userTurns}</p>
                <p className="text-slate-500">user turns</p>
              </div>
              <div className="rounded-lg bg-slate-50 px-3 py-2">
                <p className="font-black text-slate-900">{messageStats.techniques}</p>
                <p className="text-slate-500">techniques</p>
              </div>
              <div className="rounded-lg bg-slate-50 px-3 py-2">
                <p className="font-black text-slate-900">{isLoading ? 'Live' : 'Ready'}</p>
                <p className="text-slate-500">status</p>
              </div>
            </div>
          </div>
        </div>

        {messages.map((message, index) => (
          <MessageBubble key={`${message.role}-${index}`} message={message} />
        ))}

        {(showTypingIndicator || isLoading) && (
          <div className="mb-2 flex w-full animate-slide-up items-end gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-900 text-white shadow-sm">
              <Sparkles className="h-4 w-4" />
            </div>
            <TypingIndicator message={showTypingIndicator ? 'Thinking' : 'Processing'} />
          </div>
        )}

        <div ref={bottomRef} className="h-4" />
      </div>
    </div>
  )
}

export const ChatWindow = memo(ChatWindowComponent)
