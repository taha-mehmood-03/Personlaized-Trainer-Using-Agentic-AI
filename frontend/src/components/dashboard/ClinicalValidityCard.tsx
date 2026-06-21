'use client'

import React, { useState } from 'react'
import { Stethoscope, TrendingDown, TrendingUp, ChevronLeft, ChevronRight } from 'lucide-react'
import { ClinicalAssessmentStats } from '@/types'

const SEVERITY_BADGE: Record<string, string> = {
    MINIMAL:           'bg-emerald-50 text-emerald-700 border-emerald-100',
    MILD:              'bg-yellow-50 text-yellow-700 border-yellow-100',
    MODERATE:          'bg-orange-50 text-orange-700 border-orange-100',
    MODERATELY_SEVERE: 'bg-red-50 text-red-700 border-red-100',
    SEVERE:            'bg-red-100 text-red-900 border-red-200',
}

function severityColor(score: number, max: number): { bar: string; text: string; label: string } {
    const pct = score / max
    if (pct < 0.19) return { bar: 'bg-emerald-500', text: 'text-emerald-700', label: 'Minimal' }
    if (pct < 0.37) return { bar: 'bg-yellow-400',  text: 'text-yellow-700',  label: 'Mild' }
    if (pct < 0.56) return { bar: 'bg-orange-500',  text: 'text-orange-700',  label: 'Moderate' }
    if (pct < 0.74) return { bar: 'bg-red-500',     text: 'text-red-700',     label: 'Mod. Severe' }
    return               { bar: 'bg-red-800',     text: 'text-red-900',     label: 'Severe' }
}

function ScoreBar({ label, score, max }: { label: string; score: number; max: number }) {
    const pct = Math.min(100, Math.round((score / max) * 100))
    const { bar, text, label: sev } = severityColor(score, max)
    return (
        <div>
            <div className="mb-1 flex items-center justify-between">
                <p className="text-xs font-semibold text-slate-500">{label}</p>
                <div className="flex items-center gap-1.5">
                    <span className={`text-lg font-black ${text}`}>{score}</span>
                    <span className="text-xs text-slate-400">/ {max}</span>
                    <span className={`text-[10px] font-semibold ${text}`}>{sev}</span>
                </div>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                <div className={`h-full rounded-full transition-all duration-500 ${bar}`} style={{ width: `${pct}%` }} />
            </div>
        </div>
    )
}

function DeltaBadge({ delta, label }: { delta: number; label: string }) {
    if (delta === 0) return <span className="text-xs text-slate-400">→ no change in {label}</span>
    const improved = delta < 0
    return (
        <span className={`inline-flex items-center gap-1 text-xs font-semibold ${improved ? 'text-emerald-600' : 'text-rose-500'}`}>
            {improved ? <TrendingDown className="h-3.5 w-3.5" /> : <TrendingUp className="h-3.5 w-3.5" />}
            {improved ? `↓ ${Math.abs(delta)} pts` : `↑ ${delta} pts`} in {label} during session
        </span>
    )
}

export function ClinicalValidityCard({ assessment }: { assessment: ClinicalAssessmentStats }) {
    const [selectedIdx, setSelectedIdx] = useState(assessment.trend.length - 1)

    const session  = assessment.trend[selectedIdx]
    const isLatest = selectedIdx === assessment.trend.length - 1
    const isFirst  = selectedIdx === 0
    const total    = assessment.trend.length

    const severityKey = session?.severity.toUpperCase().replace(' ', '_') ?? 'MINIMAL'
    const badgeClass  = SEVERITY_BADGE[severityKey] ?? 'bg-slate-50 text-slate-600 border-slate-100'

    const dateStr = session?.date
        ? new Date(session.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
        : '—'

    const overallDelta = assessment.latestDelta
    const isImproving  = assessment.improving

    // Did the session show within-session improvement?
    const sessionHelped = session && session.withinPhq9Delta < 0

    if (!session) return null

    return (
        <section className="content-auto rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            {/* Header */}
            <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-cyan-50">
                        <Stethoscope className="h-4 w-4 text-cyan-600" />
                    </div>
                    <div>
                        <h3 className="text-sm font-bold text-slate-900">Clinical Tool Validity</h3>
                        <p className="text-xs text-slate-500">PHQ-9 &amp; GAD-7 — before and after therapy, per session</p>
                    </div>
                </div>
                {overallDelta !== null && total >= 2 && (
                    <div className={`inline-flex items-center gap-1 self-start rounded-full px-3 py-1 text-xs font-semibold sm:self-auto ${isImproving ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'}`}>
                        {isImproving ? <TrendingDown className="h-3.5 w-3.5" /> : <TrendingUp className="h-3.5 w-3.5" />}
                        Overall {isImproving ? 'improving' : 'worsening'} · {Math.abs(overallDelta).toFixed(1)} pts vs. baseline
                    </div>
                )}
            </div>

            {/* Session navigator */}
            <div className="mb-3 flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-4 py-2.5">
                <button
                    onClick={() => setSelectedIdx(i => Math.max(0, i - 1))}
                    disabled={isFirst}
                    className="flex h-7 w-7 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-white hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-30"
                >
                    <ChevronLeft className="h-4 w-4" />
                </button>
                <div className="text-center">
                    <p className="text-xs font-bold text-slate-900">
                        {session.sessionTitle}
                        {isLatest && <span className="ml-2 rounded-full bg-cyan-100 px-2 py-0.5 text-[9px] font-bold text-cyan-700">latest</span>}
                        {isFirst  && <span className="ml-2 rounded-full bg-slate-200 px-2 py-0.5 text-[9px] font-bold text-slate-500">baseline</span>}
                    </p>
                    <p className="text-[11px] text-slate-400">{selectedIdx + 1} of {total} · {dateStr}</p>
                </div>
                <button
                    onClick={() => setSelectedIdx(i => Math.min(total - 1, i + 1))}
                    disabled={isLatest}
                    className="flex h-7 w-7 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-white hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-30"
                >
                    <ChevronRight className="h-4 w-4" />
                </button>
            </div>

            {/* Dot trail */}
            {total > 1 && (
                <div className="mb-4 flex items-center justify-center gap-1.5">
                    {assessment.trend.map((_, i) => (
                        <button
                            key={i}
                            onClick={() => setSelectedIdx(i)}
                            className={`h-2 rounded-full transition-all ${i === selectedIdx ? 'w-5 bg-cyan-500' : 'w-2 bg-slate-200 hover:bg-slate-300'}`}
                            title={`Session ${i + 1}`}
                        />
                    ))}
                </div>
            )}

            {/* Before / After scores */}
            <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                {/* Before therapy */}
                <div className="rounded-lg border border-slate-100 bg-slate-50 p-4">
                    <p className="mb-3 text-[10px] font-bold uppercase tracking-wider text-slate-400">Before Therapy</p>
                    <div className="space-y-3">
                        <ScoreBar label="PHQ-9  Depression" score={session.startPhq9} max={27} />
                        <ScoreBar label="GAD-7  Anxiety"    score={session.startGad7} max={21} />
                    </div>
                </div>

                {/* After therapy */}
                {session.logCount > 1 ? (
                    <div className={`rounded-lg border p-4 ${sessionHelped ? 'border-emerald-100 bg-emerald-50/30' : 'border-slate-100 bg-slate-50'}`}>
                        <div className="mb-3 flex items-center justify-between">
                            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">After Therapy</p>
                            <span className="text-[9px] text-slate-400">{session.logCount} checkpoints</span>
                        </div>
                        <div className="space-y-3">
                            <ScoreBar label="PHQ-9  Depression" score={session.endPhq9} max={27} />
                            <ScoreBar label="GAD-7  Anxiety"    score={session.endGad7} max={21} />
                        </div>
                    </div>
                ) : (
                    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-slate-200 bg-slate-50/50 p-4 text-center">
                        <p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">After Therapy</p>
                        <p className="text-xs leading-relaxed text-slate-400">
                            Score will appear here after you send a message describing how you feel following your exercise.
                        </p>
                    </div>
                )}
            </div>

            {/* Within-session change */}
            <div className="mb-4 flex flex-wrap items-center gap-4 rounded-lg border border-slate-100 bg-slate-50 px-4 py-3">
                <div className="space-y-1">
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Within-Session Change</p>
                    {session.logCount > 1 ? (
                        <div className="flex flex-wrap gap-3">
                            <DeltaBadge delta={session.withinPhq9Delta} label="PHQ-9" />
                            <DeltaBadge delta={session.withinGad7Delta} label="GAD-7" />
                        </div>
                    ) : (
                        <p className="text-xs text-slate-400">Awaiting follow-up assessment after therapy.</p>
                    )}
                </div>
                <div className="ml-auto flex items-center gap-2">
                    <span className="text-xs font-semibold text-slate-400">Severity</span>
                    <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold capitalize ${badgeClass}`}>
                        {session.severity.toLowerCase().replace('_', ' ')}
                    </span>
                    {session.confidence > 0 && (
                        <span className="text-xs text-slate-400">{Math.round(session.confidence * 100)}% conf.</span>
                    )}
                </div>
            </div>

            {/* Indicators */}
            {session.indicators.length > 0 && (
                <div className="rounded-lg border border-slate-100 bg-slate-50 px-4 py-3">
                    <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                        Clinical Indicators — this session
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                        {session.indicators.map(ind => (
                            <span key={ind} className="rounded-full border border-slate-100 bg-white px-2.5 py-1 text-[10px] font-medium capitalize text-slate-600 shadow-sm">
                                {ind.replaceAll('_', ' ')}
                            </span>
                        ))}
                    </div>
                </div>
            )}

            <p className="mt-3 text-[10px] text-slate-400">
                Scores are inferred from natural conversation using PHQ-9 and GAD-7 rubrics. "Before" = first assessment in session; "After" = latest assessment after therapy was provided. Negative delta = symptom reduction.
            </p>
        </section>
    )
}
