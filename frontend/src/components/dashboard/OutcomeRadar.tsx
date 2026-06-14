import React from 'react'
import { DashboardStats } from '@/types'

interface OutcomeRadarProps {
    stats: DashboardStats
}

const clamp = (value: number) => Math.min(100, Math.max(0, value))

export function OutcomeRadar({ stats }: OutcomeRadarProps) {
    const outcomes = stats.longTermOutcomes
    const data = [
        { metric: 'Mood', value: clamp(outcomes.averageMoodScore), tone: 'bg-cyan-700' },
        { metric: 'Stability', value: clamp(100 - outcomes.emotionalVolatility), tone: 'bg-sky-600' },
        { metric: 'Resilience', value: clamp(outcomes.resilienceScore), tone: 'bg-emerald-600' },
        { metric: 'Technique Fit', value: clamp(outcomes.techniqueEffectiveness), tone: 'bg-cyan-600' },
        { metric: 'Readiness', value: clamp(outcomes.interventionReadiness), tone: 'bg-amber-600' },
    ]

    return (
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-start justify-between gap-4">
                <div>
                    <h2 className="text-sm font-bold text-slate-800">Long-Term Outcomes</h2>
                    <p className="mt-1 text-xs capitalize text-slate-500">
                        {outcomes.moodTrendLabel} trend, {outcomes.moodTrendDelta > 0 ? '+' : ''}
                        {outcomes.moodTrendDelta} mood delta
                    </p>
                </div>
                <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">
                    {outcomes.interventionReadiness}% ready
                </span>
            </div>

            <div className="mt-5 space-y-4">
                {data.map((item) => (
                    <div key={item.metric}>
                        <div className="flex items-center justify-between text-xs">
                            <span className="font-medium text-slate-600">{item.metric}</span>
                            <span className="font-semibold text-slate-500">{item.value}%</span>
                        </div>
                        <div className="mt-2 h-3 overflow-hidden rounded-full bg-slate-100">
                            <div className={`h-full rounded-full ${item.tone}`} style={{ width: `${item.value}%` }} />
                        </div>
                    </div>
                ))}
            </div>
        </section>
    )
}
