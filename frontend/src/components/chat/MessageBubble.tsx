import React, { memo } from 'react'
import { Message } from '@/types'
import { Brain, CheckCircle2, Sparkles, UserRound, Volume2 } from 'lucide-react'
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

          {!isUser && technique && (
            <div className="mt-2 rounded-xl border border-cyan-100 bg-cyan-50 px-3 py-2 text-xs text-cyan-900">
              <div className="flex items-center gap-2 font-semibold">
                <CheckCircle2 className="h-3.5 w-3.5" />
                Suggested technique: {technique.name}
              </div>
              <p className="mt-1 text-cyan-700">
                {technique.category} - {technique.duration_minutes} min
              </p>
            </div>
          )}
        </div>
      </div>
    </article>
  )
}

export const MessageBubble = memo(MessageBubbleComponent)
