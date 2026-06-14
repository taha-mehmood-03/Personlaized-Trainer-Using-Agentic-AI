import React from 'react'
import { CheckCircle2, CircleDot, Siren } from 'lucide-react'
import { DashboardSuggestion } from '@/types'

interface SuggestionPanelProps {
    suggestions: DashboardSuggestion[]
}

const priorityStyle = {
    high: {
        icon: Siren,
        badge: 'bg-rose-50 text-rose-700 border-rose-100',
        dot: 'bg-rose-500',
    },
    medium: {
        icon: CircleDot,
        badge: 'bg-amber-50 text-amber-700 border-amber-100',
        dot: 'bg-amber-500',
    },
    low: {
        icon: CheckCircle2,
        badge: 'bg-emerald-50 text-emerald-700 border-emerald-100',
        dot: 'bg-emerald-500',
    },
}

export function SuggestionPanel({ suggestions }: SuggestionPanelProps) {
    const items = suggestions.length
        ? suggestions
        : [
              {
                  priority: 'low' as const,
                  area: 'tracking',
                  title: 'Analytics are stable',
                  action: 'Keep collecting check-ins, mood snapshots, and technique feedback.',
              },
          ]

    return (
        <section className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
            <div className="flex items-start justify-between gap-4">
                <div>
                    <h2 className="text-sm font-bold text-slate-800">Personalized Suggestions</h2>
                    <p className="text-xs text-slate-500 mt-1">Ranked from current long-term signals</p>
                </div>
                <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">
                    {items.length}
                </span>
            </div>

            <div className="mt-4 space-y-3">
                {items.slice(0, 5).map((item, index) => {
                    const style = priorityStyle[item.priority]
                    const Icon = style.icon
                    return (
                        <article key={`${item.title}-${index}`} className="rounded-xl border border-slate-100 p-4">
                            <div className="flex items-start gap-3">
                                <div className="mt-0.5 rounded-lg bg-slate-50 p-2">
                                    <Icon className="h-4 w-4 text-slate-700" />
                                </div>
                                <div className="min-w-0 flex-1">
                                    <div className="flex flex-wrap items-center gap-2">
                                        <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${style.badge}`}>
                                            <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
                                            {item.priority}
                                        </span>
                                        <span className="text-[11px] font-semibold uppercase text-slate-400">
                                            {item.area}
                                        </span>
                                    </div>
                                    <h3 className="mt-2 text-sm font-bold text-slate-800">{item.title}</h3>
                                    <p className="mt-1 text-sm leading-6 text-slate-600">{item.action}</p>
                                </div>
                            </div>
                        </article>
                    )
                })}
            </div>
        </section>
    )
}
