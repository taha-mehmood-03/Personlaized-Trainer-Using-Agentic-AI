'use client'

import { Brain, Circle, HeartPulse, MessageSquareText, ShieldCheck, Sparkles } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cleanEmotionLabel } from '@/lib/chatEmotion'

interface ChatHeaderProps {
  emotion: string | null
  subEmotion?: string | null
  sentiment: string | null
  messageCount?: number
  isStreaming?: boolean
  hasTechnique?: boolean
}

function sentimentTone(sentiment: string | null) {
  const value = sentiment?.toLowerCase()
  if (value === 'positive') return 'bg-emerald-50 text-emerald-700 border-emerald-100'
  if (value === 'negative') return 'bg-rose-50 text-rose-700 border-rose-100'
  return 'bg-slate-100 text-slate-600 border-slate-200'
}

export function ChatHeader({
  emotion,
  subEmotion,
  sentiment,
  messageCount = 0,
  isStreaming = false,
  hasTechnique = false,
}: ChatHeaderProps) {
  const cleanEmotion = cleanEmotionLabel(emotion)
  const cleanSubEmotion = cleanEmotionLabel(subEmotion)
  const cleanSentiment = cleanEmotionLabel(sentiment)

  return (
    <header className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-900 text-white shadow-sm">
          <Sparkles className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="truncate text-sm font-black tracking-tight text-slate-900">
              SentiMind Companion
            </h1>
            <span className="inline-flex items-center rounded-full border border-emerald-100 bg-emerald-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-700">
              <Circle className="mr-1 h-1.5 w-1.5 fill-current" />
              {isStreaming ? 'Responding' : 'Listening'}
            </span>
          </div>
          <p className="mt-0.5 text-xs text-slate-500">
            Context-aware support with safety and continuity tracking
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary" className="border-slate-200 bg-white text-slate-700">
          <MessageSquareText className="mr-1 h-3.5 w-3.5" />
          {messageCount} turns
        </Badge>
        {(cleanEmotion || cleanSubEmotion) && (
          <Badge variant="secondary" className="border-amber-100 bg-amber-50 capitalize text-amber-700">
            <Brain className="mr-1 h-3.5 w-3.5" />
            {cleanEmotion && cleanSubEmotion && cleanSubEmotion.toLowerCase() !== cleanEmotion.toLowerCase()
              ? `${cleanEmotion} / ${cleanSubEmotion}`
              : cleanEmotion ?? cleanSubEmotion}
          </Badge>
        )}
        {cleanSentiment && (
          <Badge variant="secondary" className={sentimentTone(cleanSentiment)}>
            <HeartPulse className="mr-1 h-3.5 w-3.5" />
            {cleanSentiment}
          </Badge>
        )}
        <Badge variant="secondary" className="border-slate-200 bg-white text-slate-700">
          <ShieldCheck className="mr-1 h-3.5 w-3.5" />
          Safety on
        </Badge>
        {hasTechnique && (
          <Badge variant="secondary" className="border-cyan-100 bg-cyan-50 text-cyan-700">
            Technique active
          </Badge>
        )}
      </div>
    </header>
  )
}
