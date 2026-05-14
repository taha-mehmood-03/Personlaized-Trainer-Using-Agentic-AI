'use client'

import React from 'react'
import { SessionSummary, EmotionType } from '@/types'
import { format, parseISO } from 'date-fns'

const EMOTION_PILL: Record<EmotionType, string> = {
    joy: 'bg-emerald-50 text-emerald-700',
    sadness: 'bg-indigo-50 text-indigo-700',
    anxiety: 'bg-amber-50 text-amber-700',
    anger: 'bg-red-50 text-red-700',
    fear: 'bg-purple-50 text-purple-700',
    disgust: 'bg-slate-100 text-slate-600',
    neutral: 'bg-slate-100 text-slate-600',
    surprise: 'bg-cyan-50 text-cyan-700',
    guilt: 'bg-orange-50 text-orange-700',
}

interface SessionHistoryTableProps {
    sessions: SessionSummary[]
}

/** Table listing recent chat sessions with emotion badge and duration. */
export const SessionHistoryTable = ({ sessions }: SessionHistoryTableProps) => {
    return (
        <div className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm overflow-hidden">
            <h3 className="text-sm font-bold text-slate-700 mb-4">Session History</h3>
            <div className="overflow-x-auto">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="border-b border-slate-100">
                            <th className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wider pb-3 pr-4">Session</th>
                            <th className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wider pb-3 pr-4">Date</th>
                            <th className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wider pb-3 pr-4">Emotion</th>
                            <th className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wider pb-3 pr-4">Duration</th>
                            <th className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wider pb-3">Technique</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                        {sessions.map((s) => (
                            <tr key={s.id} className="hover:bg-slate-50 transition-colors group">
                                <td className="py-3 pr-4 font-medium text-slate-800 max-w-[180px] truncate">
                                    {s.title || 'Untitled Session'}
                                </td>
                                <td className="py-3 pr-4 text-slate-500 whitespace-nowrap">
                                    {format(parseISO(s.date), 'MMM d, yyyy')}
                                </td>
                                <td className="py-3 pr-4">
                                    <span
                                        className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold capitalize ${
                                            EMOTION_PILL[s.dominantEmotion] ?? EMOTION_PILL.neutral
                                        }`}
                                    >
                                        {s.dominantEmotion}
                                    </span>
                                </td>
                                <td className="py-3 pr-4 text-slate-500 whitespace-nowrap">
                                    {s.durationMinutes} min
                                </td>
                                <td className="py-3 text-slate-500 max-w-[160px] truncate">
                                    {s.techniqueUsed ?? '—'}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    )
}
