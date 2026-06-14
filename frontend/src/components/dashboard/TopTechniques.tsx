import React from 'react'
import { TopTechniqueEntry } from '@/types'
import { cn } from '@/lib/utils'

interface TopTechniquesProps {
    data: TopTechniqueEntry[]
    preferredCategories?: string[]
}

function categoryInitial(category: string) {
    return category.trim().slice(0, 2).toUpperCase() || 'TX'
}

function effectivenessColor(value: number | null | undefined): string {
    if (value === null || value === undefined) return 'text-slate-400 bg-slate-50'
    if (value >= 60) return 'text-emerald-700 bg-emerald-50'
    if (value >= 30) return 'text-amber-700 bg-amber-50'
    return 'text-rose-700 bg-rose-50'
}

export const TopTechniques = ({ data, preferredCategories = [] }: TopTechniquesProps) => {
    // Composite score bar: use compositeScore if available, else usageCount-based
    const maxComposite = Math.max(...data.map((t) => t.compositeScore ?? t.usageCount), 1)

    return (
        <section className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
            <div className="flex items-start justify-between gap-4">
                <div>
                    <h2 className="text-sm font-bold text-slate-800">Technique Personalization</h2>
                    <p className="text-xs text-slate-500 mt-1">Ranked by usage × effectiveness composite</p>
                </div>
                <span className="rounded-full bg-cyan-50 px-2.5 py-1 text-xs font-semibold text-cyan-700">
                    {preferredCategories.length} preferred
                </span>
            </div>

            {data.length ? (
                <ol className="mt-4 space-y-4">
                    {data.slice(0, 5).map((item, idx) => {
                        const compositeVal = item.compositeScore ?? item.usageCount
                        const barPct = Math.round((compositeVal / maxComposite) * 100)
                        const hasEffectiveness = item.meanEffectiveness !== null && item.meanEffectiveness !== undefined

                        return (
                            <li key={`${item.name}-${idx}`} className="flex items-start gap-3">
                                <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-900 text-xs font-bold text-white">
                                    {idx + 1}
                                </span>
                                <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-[11px] font-black text-slate-600">
                                    {categoryInitial(item.category)}
                                </span>
                                <div className="min-w-0 flex-1">
                                    <div className="flex flex-wrap items-center justify-between gap-2">
                                        <p className="truncate text-sm font-semibold text-slate-800">{item.name}</p>
                                        <div className="flex items-center gap-2">
                                            {hasEffectiveness && (
                                                <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-semibold', effectivenessColor(item.meanEffectiveness))}>
                                                    {item.meanEffectiveness}% effective
                                                </span>
                                            )}
                                            <p className="shrink-0 text-xs text-slate-400">{item.usageCount} uses</p>
                                        </div>
                                    </div>
                                    {/* Composite bar */}
                                    <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
                                        <div
                                            className="h-full rounded-full bg-slate-900 transition-all duration-700"
                                            style={{ width: `${barPct}%` }}
                                        />
                                    </div>
                                    {hasEffectiveness && (
                                        <p className="mt-1 text-[10px] text-slate-400">
                                            Rank score: {(item.compositeScore ?? 0).toFixed(2)}
                                        </p>
                                    )}
                                </div>
                            </li>
                        )
                    })}
                </ol>
            ) : (
                <div className="mt-4 flex h-44 items-center justify-center rounded-xl border border-dashed border-slate-200 bg-slate-50 text-sm text-slate-500">
                    Technique preferences will appear after feedback.
                </div>
            )}
        </section>
    )
}
