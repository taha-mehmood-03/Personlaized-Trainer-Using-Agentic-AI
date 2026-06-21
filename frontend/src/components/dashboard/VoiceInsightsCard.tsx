'use client'

import React from 'react'
import { Mic, MicOff } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface VoiceInsights {
    used: boolean
    totalVoiceMessages: number
    dominantEmotion: string | null
    avgArousal: number | null
    avgValence: number | null
    avgConfidence: number | null
    avgAcousticDistressProxy: number | null
    recentEmotions: { emotion: string | null; arousal: number | null; valence: number | null; date: string | null }[]
}

interface VoiceInsightsCardProps {
    insights: VoiceInsights
}

function pct(value: number | null): string {
    if (value === null || value === undefined) return '—'
    return `${Math.round(value * 100)}%`
}

function Meter({ value, leftLabel, rightLabel, color }: { value: number | null; leftLabel: string; rightLabel: string; color: string }) {
    const filled = value !== null ? Math.max(0, Math.min(1, value)) : 0
    return (
        <div className="space-y-1">
            <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                <div
                    className={cn('h-full rounded-full transition-all', color)}
                    style={{ width: `${Math.round(filled * 100)}%` }}
                />
            </div>
            <div className="flex justify-between text-[10px] text-slate-400">
                <span>{leftLabel}</span>
                <span>{rightLabel}</span>
            </div>
        </div>
    )
}

export function VoiceInsightsCard({ insights }: VoiceInsightsCardProps) {
    return (
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-50">
                    <Mic className="h-4 w-4 text-violet-600" />
                </div>
                <h2 className="text-sm font-semibold text-slate-800">Voice Analysis</h2>
                {insights.used && (
                    <span className="ml-auto rounded-full bg-violet-50 px-2.5 py-0.5 text-xs font-medium text-violet-700">
                        {insights.totalVoiceMessages} voice {insights.totalVoiceMessages === 1 ? 'message' : 'messages'}
                    </span>
                )}
            </div>

            {!insights.used ? (
                <div className="flex flex-col items-center gap-2 py-6 text-center">
                    <MicOff className="h-8 w-8 text-slate-300" />
                    <p className="text-sm text-slate-400">No voice sessions recorded yet</p>
                    <p className="text-xs text-slate-300">Send a voice message to see acoustic insights here</p>
                </div>
            ) : (
                <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-3">
                        <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
                            <p className="text-[10px] font-medium uppercase tracking-wide text-slate-400">Dominant Emotion</p>
                            <p className="mt-1 text-sm font-semibold capitalize text-slate-700">
                                {insights.dominantEmotion ?? '—'}
                            </p>
                        </div>
                        <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
                            <p className="text-[10px] font-medium uppercase tracking-wide text-slate-400">Avg Confidence</p>
                            <p className="mt-1 text-sm font-semibold text-slate-700">{pct(insights.avgConfidence)}</p>
                        </div>
                    </div>

                    <div className="space-y-3">
                        <div>
                            <div className="mb-1.5 flex items-center justify-between">
                                <span className="text-xs font-medium text-slate-600">Energy (Arousal)</span>
                                <span className="text-xs text-slate-400">{pct(insights.avgArousal)}</span>
                            </div>
                            <Meter
                                value={insights.avgArousal}
                                leftLabel="Low"
                                rightLabel="High"
                                color="bg-violet-400"
                            />
                        </div>

                        <div>
                            <div className="mb-1.5 flex items-center justify-between">
                                <span className="text-xs font-medium text-slate-600">Valence (Mood Tone)</span>
                                <span className="text-xs text-slate-400">{pct(insights.avgValence)}</span>
                            </div>
                            <Meter
                                value={insights.avgValence}
                                leftLabel="Negative"
                                rightLabel="Positive"
                                color="bg-cyan-400"
                            />
                        </div>

                        {insights.avgAcousticDistressProxy !== null && (
                            <div>
                                <div className="mb-1.5 flex items-center justify-between">
                                    <span className="text-xs font-medium text-slate-600">Acoustic Distress</span>
                                    <span className="text-xs text-slate-400">{pct(insights.avgAcousticDistressProxy)}</span>
                                </div>
                                <Meter
                                    value={insights.avgAcousticDistressProxy}
                                    leftLabel="Calm"
                                    rightLabel="Distressed"
                                    color="bg-rose-400"
                                />
                            </div>
                        )}
                    </div>

                    {insights.recentEmotions.length > 0 && (
                        <div>
                            <p className="mb-2 text-[10px] font-medium uppercase tracking-wide text-slate-400">
                                Recent Voice Emotions
                            </p>
                            <div className="flex flex-wrap gap-1.5">
                                {insights.recentEmotions.slice(0, 6).map((item, i) => (
                                    <span
                                        key={i}
                                        className="rounded-full border border-violet-100 bg-violet-50 px-2 py-0.5 text-[10px] font-medium capitalize text-violet-700"
                                    >
                                        {item.emotion ?? 'unknown'}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}
