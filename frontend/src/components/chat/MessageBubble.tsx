import React from 'react'
import { Message } from '@/types'
import { Sparkles, Brain } from 'lucide-react'
import { Badge } from '@/components/ui/badge'

interface MessageBubbleProps {
  message: Message
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex w-full ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`flex max-w-[85%] sm:max-w-[75%] gap-3 items-end ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
        {/* Avatar */}
        <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 border shadow-sm select-none ${
          isUser
            ? 'bg-slate-100 border-slate-200 text-slate-500'
            : 'bg-gradient-to-br from-purple-500 to-teal-400 border-purple-400/50 text-white'
        }`}>
          {isUser ? <span className="text-xs font-semibold">ME</span> : <Sparkles className="w-4 h-4" />}
        </div>

        {/* Bubble */}
        <div className={`relative px-4 py-3 rounded-2xl shadow-sm text-sm ${
          isUser
            ? 'bg-gradient-to-br from-purple-600 to-purple-500 text-white rounded-br-sm'
            : 'bg-white border border-slate-200 text-slate-800 rounded-bl-sm'
        }`}>
          {/* Audio feature info for user */}
          {isUser && message.voiceEmotion && (
            <div className="flex items-center gap-1.5 mb-2 pb-2 border-b border-white/20 text-xs text-white/90">
              <span className="opacity-80">🎙️ Detected tone:</span>
              <span className="font-semibold capitalize">{message.voiceEmotion}</span>
              <span className="opacity-75 text-[10px]">
                ({Math.round((message.voiceConfidence ?? 0) * 100)}%)
              </span>
            </div>
          )}

          {/* Assistant metadata (emotion/sentiment badges) */}
          {!isUser && (message.emotion || message.sentiment) && (
            <div className="flex flex-wrap gap-1.5 mb-2 pb-2 border-b border-slate-100/50">
              {message.emotion && (
                <Badge variant="emotion" className="capitalize text-[10px] h-5 px-1.5 flex items-center gap-1">
                  <Brain className="w-3 h-3" />
                  {message.emotion} check
                </Badge>
              )}
            </div>
          )}

          {/* Markdown-like simple parsing for bolding */}
          <div className="leading-relaxed whitespace-pre-wrap break-words">
            {message.content.split('**').map((chunk, i) => (
              i % 2 === 1 ? <strong key={i} className="font-bold">{chunk}</strong> : chunk
            ))}
            {message._streaming && (
              <span className="inline-block w-1.5 h-4 ml-1 bg-current animate-pulse align-middle" />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
