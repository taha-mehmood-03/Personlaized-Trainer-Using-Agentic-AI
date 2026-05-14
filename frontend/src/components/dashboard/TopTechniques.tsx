'use client'

import React from 'react'
import { TopTechniqueEntry } from '@/types'

const CATEGORY_ICON: Record<string, string> = {
    breathing: '🌬️',
    meditation: '🧘',
    mindfulness: '🌿',
    cbt: '🧠',
    dbt: '⚖️',
    journaling: '📝',
    grounding: '🌍',
    'behavioral activation': '⚡',
    general: '✨',
    visualization: '🌅',
}

interface TopTechniquesProps {
    data: TopTechniqueEntry[]
}

/** Ranked list of most-used wellness techniques. */
export const TopTechniques = ({ data }: TopTechniquesProps) => {
    const max = Math.max(...data.map((t) => t.usageCount), 1)

    return (
        <div className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm">
            <h3 className="text-sm font-bold text-slate-700 mb-4">Top Techniques</h3>
            <ol className="space-y-3">
                {data.slice(0, 5).map((item, idx) => {
                    const pct = Math.round((item.usageCount / max) * 100)
                    const icon = CATEGORY_ICON[item.category.toLowerCase()] ?? '✨'
                    return (
                        <li key={item.name} className="flex items-center gap-3">
                            <span className="w-5 h-5 text-center text-xs font-bold text-slate-400 shrink-0">
                                {idx + 1}
                            </span>
                            <span className="text-lg shrink-0">{icon}</span>
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center justify-between mb-0.5">
                                    <p className="text-sm font-semibold text-slate-700 truncate">{item.name}</p>
                                    <p className="text-xs text-slate-400 ml-2 shrink-0">×{item.usageCount}</p>
                                </div>
                                <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
                                    <div
                                        className="h-full rounded-full bg-gradient-to-r from-purple-500 to-teal-400 transition-all duration-700"
                                        style={{ width: `${pct}%` }}
                                    />
                                </div>
                            </div>
                        </li>
                    )
                })}
            </ol>
        </div>
    )
}
