'use client'

import React from 'react'
import { TrendingUp, TrendingDown, Minus, CheckCircle2, XCircle, BarChart3, CalendarCheck } from 'lucide-react'
import { DashboardImprovementAnalysis } from '@/types'
import { cn } from '@/lib/utils'

interface ImprovementAnalysisPanelProps {
    analysis: DashboardImprovementAnalysis
}

const STATUS_CONFIG = {
    improving: {
        label: 'Improving',
        icon: TrendingUp,
        color: 'text-emerald-600',
        badge: 'bg-emerald-50 text-emerald-700 border-emerald-200',
        bar: 'bg-emerald-500',
    },
    declining: {
        label: 'Needs Attention',
        icon: TrendingDown,
        color: 'text-rose-600',
        badge: 'bg-rose-50 text-rose-700 border-rose-200',
        bar: 'bg-rose-500',
    },
    stable: {
        label: 'Stable',
        icon: Minus,
        color: 'text-sky-600',
        badge: 'bg-sky-50 text-sky-700 border-sky-200',
        bar: 'bg-sky-500',
    },
    insufficient_data: {
        label: 'Not Enough Data',
        icon: Minus,
        color: 'text-slate-500',
        badge: 'bg-slate-50 text-slate-500 border-slate-200',
        bar: 'bg-slate-300',
    },
}

function pct(value?: number): string {
    if (value === undefined || value === null) return '—'
    return `${Math.round(Math.abs(value) * 100)}%`
}

function ScoreStat({ label, value }: { label: string; value?: number }) {
    return (
        <div className="flex flex-col items-center rounded-xl border border-slate-100 bg-slate-50 p-3">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">{label}</p>
            <p className="mt-1 text-xl font-black text-slate-800">
                {value !== undefined ? `${value}%` : '—'}
            </p>
        </div>
    )
}

export function ImprovementAnalysisPanel({ analysis }: ImprovementAnalysisPanelProps) {
    if (analysis.status === 'insufficient_data') {
        return (
            <section className="rounded-xl border border-dashed border-slate-300 bg-gradient-to-br from-slate-50 to-slate-100 p-6 text-center shadow-sm">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-indigo-50 text-indigo-500 border border-indigo-100 shadow-sm">
                    <CalendarCheck className="h-6 w-6" />
                </div>
                <h3 className="mt-4 text-sm font-bold text-slate-800">Warm-up & Onboarding Phase</h3>
                <p className="mx-auto mt-2 max-w-md text-xs text-slate-600 leading-relaxed">
                    {analysis.summary || "More mood records are needed before the dashboard can explain a reliable improvement trend."}
                </p>
                <div className="mx-auto mt-5 max-w-xs rounded-xl bg-white p-4 border border-slate-200/60 shadow-sm text-left">
                    <div className="flex items-center justify-between text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                        <span>Calibration Progress</span>
                        <span className="text-indigo-600">Active</span>
                    </div>
                    <div className="mt-2 h-1.5 w-full rounded-full bg-slate-100 overflow-hidden">
                        <div className="h-full bg-indigo-500 rounded-full animate-pulse" style={{ width: '33%' }} />
                    </div>
                    <p className="mt-2.5 text-[10px] text-slate-400 leading-relaxed">
                        To build a highly accurate baseline, the AI trainer needs at least 21 days of active check-ins and 4 mood entries.
                    </p>
                </div>
            </section>
        )
    }

    const config = STATUS_CONFIG[analysis.status]
    const Icon = config.icon
    const composite = analysis.compositeScore !== undefined ? Math.round(analysis.compositeScore * 100) : null
    const sos = analysis.sessionOutcomeStats

    // Direction context for intensityDelta: negative = less distress (good)
    const intensityDecreased = analysis.intensityDelta < -0.001
    const intensityIncreased = analysis.intensityDelta > 0.001
    const intensityLabel = intensityDecreased
        ? `↓ ${pct(analysis.intensityDelta)} less distress`
        : intensityIncreased
        ? `↑ ${pct(analysis.intensityDelta)} more distress`
        : 'No change'
    const intensityColor = intensityDecreased
        ? 'text-emerald-600'
        : intensityIncreased
        ? 'text-rose-600'
        : 'text-slate-500'

    // Score delta direction
    const scoreDeltaLabel = analysis.scoreDelta > 0
        ? `+${analysis.scoreDelta.toFixed(1)} pts`
        : analysis.scoreDelta < 0
        ? `${analysis.scoreDelta.toFixed(1)} pts`
        : 'No change'
    const scoreDeltaColor = analysis.scoreDelta > 0
        ? 'text-emerald-600'
        : analysis.scoreDelta < 0
        ? 'text-rose-600'
        : 'text-slate-500'

    return (
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            {/* Header */}
            <div className="flex items-start justify-between gap-4">
                <div>
                    <h2 className="text-sm font-bold text-slate-800">Improvement Analysis</h2>
                    <p className="mt-1 text-xs text-slate-500">Multi-signal wellness trend</p>
                </div>
                <span className={cn('flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold', config.badge)}>
                    <Icon className="h-3.5 w-3.5" />
                    {config.label}
                </span>
            </div>

            {/* Composite score bar */}
            {composite !== null && (
                <div className="mt-4">
                    <div className="flex items-center justify-between text-xs">
                        <span className="font-semibold text-slate-500">Composite Wellness Score</span>
                        <span className={cn('font-black text-sm', config.color)}>{composite}%</span>
                    </div>
                    <div className="mt-1.5 h-2.5 overflow-hidden rounded-full bg-slate-100">
                        <div
                            className={cn('h-full rounded-full transition-all duration-700', config.bar)}
                            style={{ width: `${composite}%` }}
                        />
                    </div>
                    <p className="mt-1 text-[11px] text-slate-400">
                        Based on mood score (40%), distress intensity (20%), technique outcomes (20%), session outcomes (20%)
                    </p>
                </div>
            )}

            {/* Summary */}
            <p className="mt-4 text-sm leading-relaxed text-slate-600">{analysis.summary}</p>

            {/* Stats Grid — all on the same % scale */}
            <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
                <ScoreStat label="Early mood" value={analysis.earlyAverageScore} />
                <ScoreStat label="Recent mood" value={analysis.recentAverageScore} />
                <div className="flex flex-col items-center rounded-xl border border-slate-100 bg-slate-50 p-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Mood shift</p>
                    <p className={cn('mt-1 text-xl font-black', scoreDeltaColor)}>{scoreDeltaLabel}</p>
                </div>
                <div className="flex flex-col items-center rounded-xl border border-slate-100 bg-slate-50 p-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Distress</p>
                    <p className={cn('mt-1 text-sm font-bold', intensityColor)}>{intensityLabel}</p>
                </div>
            </div>

            {/* Session outcome stats */}
            {sos && sos.total >= 2 && (
                <div className="mt-4 flex items-center gap-3 rounded-xl border border-slate-100 bg-slate-50 p-3">
                    <CalendarCheck className="h-4 w-4 shrink-0 text-slate-500" />
                    <div className="min-w-0 flex-1 text-xs text-slate-600">
                        <span className="font-semibold">Session outcomes:</span>{' '}
                        <span className="text-emerald-600 font-semibold">{sos.positive} positive</span>
                        {sos.neutral > 0 && <span className="text-slate-500">, {sos.neutral} neutral</span>}
                        {sos.negative > 0 && <span className="text-rose-600">, {sos.negative} difficult</span>}
                        <span className="text-slate-400"> out of {sos.total} sessions</span>
                    </div>
                    <div className="flex items-center gap-1 text-xs font-semibold text-slate-500">
                        <BarChart3 className="h-3.5 w-3.5" />
                        {Math.round((sos.positive / sos.total) * 100)}%
                    </div>
                </div>
            )}

            {/* Contributing Factors */}
            {analysis.contributingFactors.length > 0 && (
                <div className="mt-4">
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">Contributing factors</p>
                    <ul className="mt-2 space-y-1.5">
                        {analysis.contributingFactors.map((factor, idx) => (
                            <li key={idx} className="flex items-start gap-2 text-xs text-slate-600">
                                <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />
                                {factor}
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            {/* Blockers */}
            {analysis.blockers.length > 0 && (
                <div className="mt-4">
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">Blockers</p>
                    <ul className="mt-2 space-y-1.5">
                        {analysis.blockers.map((blocker, idx) => (
                            <li key={idx} className="flex items-start gap-2 text-xs text-slate-600">
                                <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-rose-400" />
                                {blocker}
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </section>
    )
}
