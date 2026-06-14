import React from 'react'
import { EmotionSlice, SubEmotionSlice } from '@/types'

const colors: Record<string, string> = {
    joy: 'bg-emerald-500',
    sadness: 'bg-indigo-500',
    anxiety: 'bg-amber-500',
    anger: 'bg-red-500',
    fear: 'bg-cyan-600',
    disgust: 'bg-slate-500',
    neutral: 'bg-slate-400',
    surprise: 'bg-cyan-500',
    guilt: 'bg-orange-500',
}

interface EmotionDistributionProps {
    data: EmotionSlice[]
    subEmotions?: SubEmotionSlice[]
}

export const EmotionDistribution = ({ data, subEmotions = [] }: EmotionDistributionProps) => {
    const total = data.reduce((sum, item) => sum + item.count, 0)

    return (
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-start justify-between gap-4">
                <div>
                    <h2 className="text-sm font-bold text-slate-800">Emotion Mix</h2>
                    <p className="mt-1 text-xs text-slate-500">Distribution across the selected dashboard window</p>
                </div>
                <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">
                    {total} logs
                </span>
            </div>

            {data.length ? (
                <div className="mt-5 space-y-3">
                    <div className="flex h-4 overflow-hidden rounded-full bg-slate-100">
                        {data.map((entry) => (
                            <div
                                key={entry.emotion}
                                className={colors[entry.emotion] ?? 'bg-slate-400'}
                                style={{ width: `${entry.percentage}%` }}
                                title={`${entry.emotion}: ${entry.percentage}%`}
                            />
                        ))}
                    </div>
                    {data.slice(0, 7).map((entry) => (
                        <div key={entry.emotion}>
                            <div className="flex items-center justify-between gap-3 text-xs">
                                <span className="flex min-w-0 items-center gap-2 capitalize text-slate-700">
                                    <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${colors[entry.emotion] ?? 'bg-slate-400'}`} />
                                    {entry.emotion}
                                </span>
                                <span className="shrink-0 font-semibold text-slate-500">{entry.count} - {entry.percentage}%</span>
                            </div>
                        </div>
                    ))}
                </div>
            ) : (
                <div className="mt-4 flex h-48 items-center justify-center rounded-xl border border-dashed border-slate-200 bg-slate-50 text-sm text-slate-500">
                    Emotion distribution will appear after mood logs.
                </div>
            )}

            {subEmotions.length > 0 && (
                <div className="mt-4 border-t border-slate-100 pt-3">
                    <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
                        Top sub-emotions
                    </p>
                    <div className="mt-2 flex flex-wrap gap-2">
                        {subEmotions.slice(0, 6).map((item) => (
                            <span
                                key={item.subEmotion}
                                className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold capitalize text-slate-600"
                            >
                                {item.subEmotion.replaceAll('_', ' ')} - {item.percentage}%
                            </span>
                        ))}
                    </div>
                </div>
            )}
        </section>
    )
}
