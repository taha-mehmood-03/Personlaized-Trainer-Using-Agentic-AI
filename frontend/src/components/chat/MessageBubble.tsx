import React, { memo, useMemo, useState } from 'react'
import { Message, Technique } from '@/types'
import {
  Brain,
  Check,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Gauge,
  Play,
  Sparkles,
  Tag,
  UserRound,
  Volume2,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cleanAssistantContent, cleanEmotionLabel, cleanEmotionList } from '@/lib/chatEmotion'

interface MessageBubbleProps {
  message: Message
}

function renderRichText(content: string, isUser: boolean) {
  return content.split('**').map((chunk, index) =>
    index % 2 === 1 ? (
      <strong key={index} className={isUser ? 'font-semibold text-white' : 'font-semibold text-slate-950'}>
        {chunk}
      </strong>
    ) : (
      <React.Fragment key={index}>{chunk}</React.Fragment>
    )
  )
}

function compactList(values?: string[]) {
  return (values ?? []).filter(Boolean).slice(0, 3).join(', ')
}

function cleanTechniqueText(value: unknown) {
  return typeof value === 'string' ? value.trim() : ''
}

function InlineTechniqueCard({ technique }: { technique: Technique }) {
  const steps = useMemo(
    () => (Array.isArray(technique.steps) ? technique.steps.map(cleanTechniqueText).filter(Boolean) : []),
    [technique.steps]
  )
  const [stepIndex, setStepIndex] = useState(0)
  const [started, setStarted] = useState(false)
  const [completed, setCompleted] = useState(false)
  const stepCount = steps.length
  const currentStep = steps[stepIndex] ?? 'Take one slow breath and notice where your body feels supported.'
  const progress = stepCount ? ((stepIndex + 1) / stepCount) * 100 : 0
  const reason = cleanTechniqueText(technique.why_it_works) || cleanTechniqueText(technique.brief)
  const category = cleanTechniqueText(technique.category) || 'Exercise'
  const difficulty = cleanTechniqueText(technique.difficulty) || 'Guided'

  const handlePrimaryAction = () => {
    if (!started) {
      setStarted(true)
      return
    }

    if (stepIndex < stepCount - 1) {
      setStepIndex((value) => value + 1)
      return
    }

    setCompleted(true)
  }

  return (
    <section className="mt-3 overflow-hidden rounded-xl border border-cyan-100 bg-white shadow-sm">
      <div className="border-b border-slate-100 bg-gradient-to-br from-slate-950 to-cyan-800 p-4 text-white">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-cyan-100">Suggested exercise</p>
            <h3 className="mt-1 text-base font-black leading-tight">{technique.name}</h3>
          </div>
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-white/20 bg-white/15">
            <Sparkles className="h-4 w-4" />
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-2 text-[11px] font-semibold text-cyan-50">
          <span className="inline-flex items-center gap-1 rounded-lg bg-white/15 px-2 py-1">
            <Tag className="h-3 w-3" />
            {category}
          </span>
          <span className="inline-flex items-center gap-1 rounded-lg bg-white/15 px-2 py-1">
            <Clock3 className="h-3 w-3" />
            {technique.duration_minutes ?? 'N/A'} min
          </span>
          <span className="inline-flex items-center gap-1 rounded-lg bg-white/15 px-2 py-1 capitalize">
            <Gauge className="h-3 w-3" />
            {difficulty.toLowerCase()}
          </span>
        </div>

        {reason && <p className="mt-3 text-xs leading-5 text-cyan-50/90">{reason}</p>}
      </div>

      <div className="space-y-3 bg-slate-50 p-3">
        <div className="flex items-center justify-between gap-3 text-[11px] font-semibold text-slate-500">
          <span>{stepCount ? `Step ${stepIndex + 1} of ${stepCount}` : 'First step'}</span>
          {stepCount > 0 && (
            <div className="h-1.5 min-w-24 flex-1 overflow-hidden rounded-full bg-slate-200">
              <div className="h-full rounded-full bg-cyan-600 transition-all duration-300" style={{ width: `${progress}%` }} />
            </div>
          )}
          <span className={completed ? 'text-emerald-700' : 'text-cyan-700'}>
            {completed ? 'Complete' : started ? 'In progress' : 'Ready'}
          </span>
        </div>

        <div className="flex gap-3 rounded-lg border border-slate-200 bg-white p-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-cyan-50 text-sm font-black text-cyan-700">
            {stepIndex + 1}
          </div>
          <p className="min-w-0 text-sm leading-6 text-slate-800">{currentStep}</p>
        </div>

        <div className="flex items-center justify-between gap-2">
          <button
            type="button"
            title="Previous step"
            aria-label="Previous step"
            onClick={() => {
              setCompleted(false)
              setStepIndex((value) => Math.max(0, value - 1))
            }}
            disabled={stepIndex === 0}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>

          <button
            type="button"
            onClick={handlePrimaryAction}
            disabled={completed}
            className="inline-flex min-h-9 flex-1 items-center justify-center gap-2 rounded-lg bg-slate-950 px-3 py-2 text-xs font-bold text-white transition-colors hover:bg-slate-800 disabled:bg-emerald-600"
          >
            {completed ? (
              <>
                <Check className="h-4 w-4" />
                Done
              </>
            ) : !started ? (
              <>
                <Play className="h-4 w-4" />
                Start first step
              </>
            ) : stepIndex < stepCount - 1 ? (
              <>
                Next step
                <ChevronRight className="h-4 w-4" />
              </>
            ) : (
              <>
                <Check className="h-4 w-4" />
                Mark complete
              </>
            )}
          </button>
        </div>
      </div>
    </section>
  )
}

function MessageBubbleComponent({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user'
  const technique = message.technique
  const emotion = cleanEmotionLabel(message.emotion)
  const primarySubEmotion = cleanEmotionLabel(message.primarySubEmotion ?? message.primary_sub_emotion)
  const secondarySubEmotions = cleanEmotionList(message.secondarySubEmotions ?? message.secondary_sub_emotions)
  const detectedSymptoms = cleanEmotionList(message.detectedSymptoms ?? message.detected_symptoms)
  const sentiment = cleanEmotionLabel(message.sentiment)
  const explicitEmotionLabel = cleanEmotionLabel(message.emotionLabel ?? message.emotion_label)
  const emotionLabel =
    explicitEmotionLabel ??
    (emotion && primarySubEmotion && primarySubEmotion.toLowerCase() !== emotion.toLowerCase()
      ? `${emotion} / ${primarySubEmotion}`
      : emotion ?? primarySubEmotion)
  const displayContent = cleanAssistantContent(message.content, isUser ? 'user' : 'assistant')
  const hasMoodMetadata = Boolean(
    emotionLabel || sentiment || secondarySubEmotions.length || detectedSymptoms.length
  )
  const metadataBorderClass = isUser ? 'border-white/15' : 'border-slate-100'
  const emotionBadgeClass = isUser
    ? 'border-white/15 bg-white/10 text-[11px] capitalize text-white/90'
    : 'border-amber-100 bg-amber-50 text-[11px] capitalize text-amber-700'
  const secondaryBadgeClass = isUser
    ? 'border-white/15 bg-white/10 text-[11px] capitalize text-white/85'
    : 'border-sky-100 bg-sky-50 text-[11px] capitalize text-sky-700'
  const signalBadgeClass = isUser
    ? 'border-white/15 bg-white/10 text-[11px] capitalize text-white/85'
    : 'border-cyan-100 bg-cyan-50 text-[11px] capitalize text-cyan-700'
  const sentimentBadgeClass = isUser
    ? 'border-white/15 bg-white/10 text-[11px] capitalize text-white/85'
    : 'border-slate-200 bg-slate-50 text-[11px] capitalize text-slate-600'

  return (
    <article className={`flex w-full ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`flex max-w-[92%] gap-3 sm:max-w-[78%] ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
        <div
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border shadow-sm ${
            isUser
              ? 'border-slate-200 bg-white text-slate-600'
              : 'border-slate-900 bg-slate-900 text-white'
          }`}
        >
          {isUser ? <UserRound className="h-4 w-4" /> : <Sparkles className="h-4 w-4" />}
        </div>

        <div className="min-w-0">
          <div
            className={`rounded-2xl px-4 py-3 text-[15px] leading-7 shadow-sm ${
              isUser
                ? 'rounded-tr-md bg-slate-900 text-white'
                : 'rounded-tl-md border border-slate-200 bg-white text-slate-800'
            }`}
          >
            {isUser && message.voiceEmotion && (
              <div className="mb-2 flex flex-wrap items-center gap-2 border-b border-white/15 pb-2 text-xs text-white/85">
                <Volume2 className="h-3.5 w-3.5" />
                <span className="capitalize">Voice tone: {message.voiceEmotion}</span>
                <span>{Math.round((message.voiceConfidence ?? 0) * 100)}%</span>
              </div>
            )}

            {hasMoodMetadata && (
              <div className={`mb-2 flex flex-wrap gap-1.5 border-b ${metadataBorderClass} pb-2`}>
                {emotionLabel && (
                  <Badge variant="secondary" className={emotionBadgeClass}>
                    <Brain className="mr-1 h-3 w-3" />
                    {emotionLabel}
                  </Badge>
                )}
                {secondarySubEmotions.length > 0 && (
                  <Badge variant="secondary" className={secondaryBadgeClass}>
                    also {compactList(secondarySubEmotions)}
                  </Badge>
                )}
                {detectedSymptoms.length > 0 && (
                  <Badge variant="secondary" className={signalBadgeClass}>
                    signals: {compactList(detectedSymptoms)}
                  </Badge>
                )}
                {sentiment && (
                  <Badge variant="secondary" className={sentimentBadgeClass}>
                    {sentiment}
                  </Badge>
                )}
              </div>
            )}

            <div className="whitespace-pre-wrap break-words tracking-normal">
              {renderRichText(displayContent, isUser)}
              {message._streaming && message._showCursor && (
                <span className="ml-1 inline-block h-4 w-1.5 animate-pulse rounded-full bg-current align-middle opacity-80" />
              )}
            </div>
          </div>

          {!isUser && technique && <InlineTechniqueCard technique={technique} />}
        </div>
      </div>
    </article>
  )
}

export const MessageBubble = memo(MessageBubbleComponent)
