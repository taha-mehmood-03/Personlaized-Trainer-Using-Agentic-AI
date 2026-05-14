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
    <div className={`flex w-full mb-2 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`flex max-w-[88%] sm:max-w-[78%] gap-3 items-end ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
        {/* Avatar */}
        <div className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 border select-none transition-transform duration-500 hover:scale-105 ${
          isUser
            ? 'bg-gradient-to-tr from-slate-50 to-slate-100 border-slate-200 text-slate-500 shadow-sm'
            : 'bg-gradient-to-br from-purple-brand via-purple-500 to-teal-brand border-white/20 text-white shadow-[0_4px_12px_rgba(124,58,237,0.25)]'
        }`}>
          {isUser ? <span className="text-xs font-bold tracking-tight">ME</span> : <Sparkles className="w-4 h-4" />}
        </div>

        {/* Bubble */}
        <div className={`relative px-5 py-3.5 rounded-2xl text-[15px] leading-relaxed transition-all duration-300 animate-slide-up ${
          isUser
            ? 'bg-gradient-to-br from-purple-brand to-teal-500 text-white rounded-br-sm shadow-[0_4px_15px_rgba(124,58,237,0.15)]'
            : 'bg-white/90 backdrop-blur-xl border border-white/60 text-slate-800 rounded-bl-sm shadow-[0_8px_30px_rgb(0,0,0,0.04)] hover:shadow-[0_8px_30px_rgb(0,0,0,0.06)]'
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
                  Mood: {message.emotion}
                </Badge>
              )}
            </div>
          )}

          {/* Markdown-like simple parsing for bolding */}
          <div className="whitespace-pre-wrap break-words tracking-tight">
            {message.content.split('**').map((chunk, i) => (
              i % 2 === 1 ? <strong key={i} className={`font-semibold ${isUser ? 'text-white' : 'text-slate-900'}`}>{chunk}</strong> : chunk
            ))}
            {message._streaming && message._showCursor && (
              <span className="inline-block w-1.5 h-4 ml-1 bg-current align-middle rounded-full animate-pulse opacity-80 shadow-[0_0_8px_currentColor]" />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
