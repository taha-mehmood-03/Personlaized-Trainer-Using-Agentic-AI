import React from 'react'
import { DashboardTechniqueOutcome } from '@/types'

interface TechniqueOutcomeChartProps {
    outcomes: DashboardTechniqueOutcome[]
}

function label(value?: string | null) {
    return value ? value.replaceAll('_', ' ') : ''
}

export function TechniqueOutcomeChart({ outcomes }: TechniqueOutcomeChartProps) {
    const data = outcomes.slice(0, 6)

    return (
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-start justify-between gap-4">
                <div>
                    <h2 className="text-sm font-bold text-slate-800">Technique Outcomes</h2>
                    <p className="mt-1 text-xs text-slate-500">Before/after intensity and measured effectiveness</p>
                </div>
                <span className="rounded-full bg-sky-50 px-2.5 py-1 text-xs font-semibold text-sky-700">
                    {outcomes.length} records
                </span>
            </div>

            {data.length ? (
                <div className="mt-5 space-y-4">
                    {data.map((item) => (
                        <article key={`${item.techniqueName}-${item.createdAt}`} className="rounded-xl border border-slate-100 bg-slate-50 p-3">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                                <div className="min-w-0">
                                    <p className="truncate text-sm font-bold text-slate-800">{item.techniqueName}</p>
                                    <p className="mt-1 text-xs capitalize text-slate-500">
                                        {label(item.subEmotionBefore) || 'before'} to {label(item.subEmotionAfter) || 'after'}
                                    </p>
                                </div>
                                <span className="rounded-full bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-700">
                                    {item.effectiveness}% effective
                                </span>
                            </div>
                            <div className="mt-3 grid grid-cols-[4.5rem_1fr_2.5rem] items-center gap-2 text-xs">
                                <span className="text-slate-500">Before</span>
                                <div className="h-2.5 overflow-hidden rounded-full bg-white">
                                    <div className="h-full rounded-full bg-rose-400" style={{ width: `${item.intensityBefore}%` }} />
                                </div>
                                <span className="text-right font-semibold text-slate-500">{item.intensityBefore}%</span>
                                <span className="text-slate-500">After</span>
                                <div className="h-2.5 overflow-hidden rounded-full bg-white">
                                    <div className="h-full rounded-full bg-sky-400" style={{ width: `${item.intensityAfter}%` }} />
                                </div>
                                <span className="text-right font-semibold text-slate-500">{item.intensityAfter}%</span>
                            </div>
                        </article>
                    ))}
                </div>
            ) : (
                <div className="mt-4 flex h-48 items-center justify-center rounded-xl border border-dashed border-slate-200 bg-slate-50 text-sm text-slate-500">
                    No technique outcome records yet.
                </div>
            )}
        </section>
    )
}
