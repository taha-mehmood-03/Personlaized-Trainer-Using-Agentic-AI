import React, { memo, useState } from 'react'
import { Message, Technique } from '@/types'
import {
  Check,
  Clock3,
  Gauge,
  Sparkles,
  Tag,
  UserRound,
} from 'lucide-react'
import { cleanAssistantContent } from '@/lib/chatEmotion'
import { API_BASE } from '@/lib/api'

interface MessageBubbleProps {
  message: Message
}

/** Inline bold: split on ** pairs */
function applyBold(text: string, isUser: boolean): React.ReactNode[] {
  return text.split('**').map((chunk, i) =>
    i % 2 === 1 ? (
      <strong key={i} className={isUser ? 'font-semibold text-white' : 'font-semibold text-slate-900'}>
        {chunk}
      </strong>
    ) : (
      <React.Fragment key={i}>{chunk}</React.Fragment>
    )
  )
}

/**
 * Renders AI markdown-style text properly:
 * - ### / ## / # headings
 * - * bullet lines (leading asterisk or dash)
 * - 1. 2. 3. numbered lists
 * - **bold** inline
 * - blank lines → paragraph gap
 */
function renderRichText(content: string, isUser: boolean): React.ReactNode {
  if (isUser) {
    // User messages: just bold, preserve whitespace
    return <span className="whitespace-pre-wrap">{applyBold(content, true)}</span>
  }

  const lines = content.split('\n')
  const nodes: React.ReactNode[] = []
  let listBuffer: { type: 'ul' | 'ol'; items: React.ReactNode[] } | null = null
  let key = 0

  const flushList = () => {
    if (!listBuffer) return
    if (listBuffer.type === 'ul') {
      nodes.push(
        <ul key={key++} className="my-2 space-y-1 pl-5">
          {listBuffer.items.map((item, i) => (
            <li key={i} className="list-disc text-slate-700">{item}</li>
          ))}
        </ul>
      )
    } else {
      nodes.push(
        <ol key={key++} className="my-2 space-y-1 pl-5">
          {listBuffer.items.map((item, i) => (
            <li key={i} className="list-decimal text-slate-700">{item}</li>
          ))}
        </ol>
      )
    }
    listBuffer = null
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const trimmed = line.trim()

    // Blank line — flush list, add paragraph gap
    if (trimmed === '') {
      flushList()
      nodes.push(<div key={key++} className="h-2" />)
      continue
    }

    // ### heading 3
    if (trimmed.startsWith('### ')) {
      flushList()
      nodes.push(
        <h3 key={key++} className="mt-3 mb-1 text-sm font-bold text-slate-900 first:mt-0">
          {applyBold(trimmed.slice(4), false)}
        </h3>
      )
      continue
    }

    // ## heading 2
    if (trimmed.startsWith('## ')) {
      flushList()
      nodes.push(
        <h2 key={key++} className="mt-3 mb-1 text-[15px] font-bold text-slate-900 first:mt-0">
          {applyBold(trimmed.slice(3), false)}
        </h2>
      )
      continue
    }

    // # heading 1
    if (trimmed.startsWith('# ')) {
      flushList()
      nodes.push(
        <h1 key={key++} className="mt-3 mb-1 text-base font-extrabold text-slate-900 first:mt-0">
          {applyBold(trimmed.slice(2), false)}
        </h1>
      )
      continue
    }

    // Bullet: * text or - text (but not **bold**)
    if (/^[*-] /.test(trimmed) && !trimmed.startsWith('**')) {
      const itemText = trimmed.slice(2)
      if (!listBuffer || listBuffer.type !== 'ul') {
        flushList()
        listBuffer = { type: 'ul', items: [] }
      }
      listBuffer.items.push(applyBold(itemText, false))
      continue
    }

    // Numbered list: 1. text
    const numberedMatch = trimmed.match(/^(\d+)\.\s+(.*)$/)
    if (numberedMatch) {
      const itemText = numberedMatch[2]
      if (!listBuffer || listBuffer.type !== 'ol') {
        flushList()
        listBuffer = { type: 'ol', items: [] }
      }
      listBuffer.items.push(applyBold(itemText, false))
      continue
    }

    // Plain paragraph line
    flushList()
    nodes.push(
      <p key={key++} className="text-slate-700">
        {applyBold(trimmed, false)}
      </p>
    )
  }

  flushList()
  return <div className="space-y-1">{nodes}</div>
}

function cleanTechniqueText(value: unknown) {
  return typeof value === 'string' ? value.trim() : ''
}

const STAR_LABELS = ['', 'Not helpful', 'Slightly helpful', 'Somewhat helpful', 'Very helpful', 'Extremely helpful']

function TechniqueRatingWidget({ technique }: { technique: Technique }) {
  const [rating, setRating] = useState(0)
  const [hover, setHover] = useState(0)
  const [feedback, setFeedback] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [showFeedback, setShowFeedback] = useState(false)
  const [loading, setLoading] = useState(false)

  const category = cleanTechniqueText(technique.category) || 'Exercise'
  const difficulty = cleanTechniqueText(technique.difficulty) || 'Guided'

  const handleSubmit = async () => {
    if (!rating || loading) return
    setLoading(true)
    try {
      await fetch(`${API_BASE}/technique/rate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          technique_id: technique.id,
          rating,
          feedback: feedback || null,
          completed: true,
        }),
      })
    } catch {
      // silent — outcome is tracked server-side via conversation signals too
    }
    setLoading(false)
    setSubmitted(true)
  }

  const activeLevel = hover || rating

  return (
    <div className="mt-2.5 overflow-hidden rounded-xl border border-slate-200/80 bg-white shadow-sm">
      {/* Header — dark gradient strip */}
      <div className="flex flex-wrap items-start justify-between gap-3 bg-gradient-to-r from-slate-950 via-slate-900 to-slate-800 px-4 py-3">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Exercise completed</p>
          <h3 className="mt-0.5 text-sm font-bold leading-snug text-white">{technique.name}</h3>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <span className="inline-flex items-center gap-1 rounded-md bg-white/10 px-2 py-0.5 text-[10px] font-medium text-slate-300">
            <Tag className="h-2.5 w-2.5" />
            {category}
          </span>
          <span className="inline-flex items-center gap-1 rounded-md bg-white/10 px-2 py-0.5 text-[10px] font-medium text-slate-300">
            <Clock3 className="h-2.5 w-2.5" />
            {technique.duration_minutes ?? '–'} min
          </span>
          <span className="inline-flex items-center gap-1 rounded-md bg-white/10 px-2 py-0.5 text-[10px] font-medium capitalize text-slate-300">
            <Gauge className="h-2.5 w-2.5" />
            {difficulty.toLowerCase()}
          </span>
        </div>
      </div>

      {/* Rating body */}
      <div className="px-4 py-3.5">
        {submitted ? (
          <div className="flex items-center gap-2 text-sm font-semibold text-emerald-600">
            <div className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-50">
              <Check className="h-3.5 w-3.5" />
            </div>
            Rating saved — thank you for the feedback!
          </div>
        ) : (
          <>
            <p className="mb-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">
              How helpful was this exercise?
            </p>

            <div className="flex items-center gap-0.5">
              {[1, 2, 3, 4, 5].map((star) => (
                <button
                  key={star}
                  type="button"
                  onMouseEnter={() => setHover(star)}
                  onMouseLeave={() => setHover(0)}
                  onClick={() => {
                    setRating(star)
                    setShowFeedback(true)
                  }}
                  aria-label={`Rate ${star} star${star !== 1 ? 's' : ''}`}
                  className="select-none p-0.5 text-2xl leading-none transition-transform hover:scale-110 active:scale-95"
                >
                  <span className={activeLevel >= star ? 'text-amber-400' : 'text-slate-200'}>★</span>
                </button>
              ))}
              {rating > 0 && (
                <span className="ml-2 text-xs font-medium text-slate-400">{STAR_LABELS[rating]}</span>
              )}
            </div>

            {showFeedback && (
              <div className="mt-3 space-y-2">
                <textarea
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                  placeholder="Optional: what felt helpful or unhelpful?"
                  rows={2}
                  className="w-full resize-none rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700 outline-none placeholder:text-slate-400 focus:border-slate-400 focus:bg-white transition-colors"
                />
                <button
                  type="button"
                  onClick={handleSubmit}
                  disabled={loading}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-slate-700 disabled:opacity-60"
                >
                  <Check className="h-3 w-3" />
                  {loading ? 'Saving…' : 'Submit rating'}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function MessageBubbleComponent({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user'
  const technique = message.technique
  const displayContent = cleanAssistantContent(message.content, isUser ? 'user' : 'assistant')

  return (
    <article className={`flex w-full ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`flex max-w-[92%] gap-3 sm:max-w-[80%] ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
        {/* Avatar */}
        <div
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl shadow-sm ${
            isUser
              ? 'border border-slate-200 bg-white text-slate-600'
              : 'bg-slate-900 text-white'
          }`}
        >
          {isUser ? <UserRound className="h-4 w-4" /> : <Sparkles className="h-4 w-4" />}
        </div>

        <div className="min-w-0">
          {/* Message bubble */}
          <div
            className={`rounded-2xl px-4 py-3.5 shadow-sm ${
              isUser
                ? 'rounded-tr-md bg-slate-900 text-sm leading-7 text-white'
                : 'rounded-tl-md border border-slate-200/80 bg-white text-[14.5px] leading-[1.8] text-slate-700'
            }`}
          >
            {/* Message text */}
            <div className="break-words tracking-normal">
              {renderRichText(displayContent, isUser)}
              {message._streaming && message._showCursor && (
                <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-full bg-slate-400 align-middle opacity-80" />
              )}
            </div>
          </div>

          {/* Technique rating widget — replaces the old step wizard card */}
          {!isUser && technique && message.techniqueOfferedThisTurn && <TechniqueRatingWidget technique={technique} />}
        </div>
      </div>
    </article>
  )
}

export const MessageBubble = memo(MessageBubbleComponent)
