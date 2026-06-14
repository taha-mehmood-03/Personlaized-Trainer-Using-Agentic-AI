import React from 'react'
import { SessionSummary, EmotionType } from '@/types'

const EMOTION_PILL: Record<EmotionType, string> = {
    joy: 'bg-emerald-50 text-emerald-700',
    sadness: 'bg-indigo-50 text-indigo-700',
    anxiety: 'bg-amber-50 text-amber-700',
    anger: 'bg-red-50 text-red-700',
    fear: 'bg-cyan-50 text-cyan-700',
    disgust: 'bg-slate-100 text-slate-600',
    neutral: 'bg-slate-100 text-slate-600',
    surprise: 'bg-cyan-50 text-cyan-700',
    guilt: 'bg-orange-50 text-orange-700',
}

interface SessionHistoryTableProps {
    sessions: SessionSummary[]
}

function label(value: string) {
    return value.replaceAll('_', ' ')
}

function safeDate(value: string) {
    try {
        const date = new Date(value)
        if (Number.isNaN(date.getTime())) return 'No date'
        return new Intl.DateTimeFormat('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric',
        }).format(date)
    } catch {
        return 'No date'
    }
}

/** Table listing recent chat sessions with emotion badge and duration. */
export const SessionHistoryTable = ({ sessions }: SessionHistoryTableProps) => {
    return (
        <section className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm overflow-hidden">
            <h3 className="text-sm font-bold text-slate-800 mb-4">Session History</h3>
            {!sessions.length && (
                <div className="flex h-32 items-center justify-center rounded-xl border border-dashed border-slate-200 bg-slate-50 text-sm text-slate-500">
                    Session summaries will appear after longer therapeutic conversations.
                </div>
            )}
            {!!sessions.length && (
            <div className="overflow-x-auto">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="border-b border-slate-100">
                            <th className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wider pb-3 pr-4">Session</th>
                            <th className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wider pb-3 pr-4">Date</th>
                            <th className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wider pb-3 pr-4">Emotion</th>
                            <th className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wider pb-3 pr-4">Signals</th>
                            <th className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wider pb-3 pr-4">Duration</th>
                            <th className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wider pb-3">Technique</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                        {sessions.map((s) => (
                            <tr key={s.id} className="hover:bg-slate-50 transition-colors group">
                                <td className="py-3 pr-4 max-w-[220px]">
                                    <p className="truncate font-medium text-slate-800">{s.title || 'Untitled Session'}</p>
                                    {s.summary && (
                                        <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">
                                            {s.summary}
                                        </p>
                                    )}
                                </td>
                                <td className="py-3 pr-4 text-slate-500 whitespace-nowrap">
                                    {safeDate(s.date)}
                                </td>
                                <td className="py-3 pr-4">
                                    <span
                                        className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold capitalize ${
                                            EMOTION_PILL[s.dominantEmotion] ?? EMOTION_PILL.neutral
                                        }`}
                                    >
                                        {s.dominantEmotion}
                                    </span>
                                    {s.dominantSubEmotion && (
                                        <span className="ml-2 text-xs capitalize text-slate-400">
                                            {label(s.dominantSubEmotion)}
                                        </span>
                                    )}
                                    <p className="mt-1 text-xs text-slate-400">
                                        {s.trendLabel ? `${s.trendLabel.replaceAll('_', ' ')} - ` : ''}
                                        {s.averageScore !== undefined ? `${s.averageScore}% score` : 'score pending'}
                                    </p>
                                </td>
                                <td className="py-3 pr-4 min-w-[220px]">
                                    <div className="flex flex-wrap gap-1.5">
                                        {[...(s.secondarySubEmotions ?? []), ...(s.detectedSymptoms ?? []), ...(s.detectedContexts ?? [])]
                                            .slice(0, 5)
                                            .map((item) => (
                                                <span key={item} className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium capitalize text-slate-600">
                                                    {label(item)}
                                                </span>
                                            ))}
                                        {!s.secondarySubEmotions?.length && !s.detectedSymptoms?.length && !s.detectedContexts?.length && (
                                            <span className="text-xs text-slate-400">No detailed signals</span>
                                        )}
                                    </div>
                                </td>
                                <td className="py-3 pr-4 text-slate-500 whitespace-nowrap">
                                    {s.durationMinutes} min
                                </td>
                                <td className="py-3 text-slate-500 max-w-[160px] truncate">
                                    {s.techniqueUsed ?? '-'}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            )}
        </section>
    )
}
