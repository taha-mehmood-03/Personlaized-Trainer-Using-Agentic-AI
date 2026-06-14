'use client'

import React from 'react'
import {
    Brain,
    CheckCircle2,
    HeartHandshake,
    Moon,
    Shield,
    Sparkles,
    Target,
    TrendingDown,
    Zap,
    type LucideIcon,
} from 'lucide-react'

interface Goal {
    id: string
    label: string
    detail: string
    icon: LucideIcon
}

const GOALS: Goal[] = [
    { id: 'anxiety', label: 'Manage anxiety', detail: 'Pressure, worry, spirals', icon: Brain },
    { id: 'stress', label: 'Reduce stress', detail: 'Workload and overwhelm', icon: TrendingDown },
    { id: 'sleep', label: 'Better sleep', detail: 'Wind-down and routine', icon: Moon },
    { id: 'mood', label: 'Improve mood', detail: 'Low energy and sadness', icon: Sparkles },
    { id: 'focus', label: 'Increase focus', detail: 'Attention and motivation', icon: Target },
    { id: 'relationships', label: 'Relationships', detail: 'Conflict and connection', icon: HeartHandshake },
    { id: 'grief', label: 'Process grief', detail: 'Loss and adjustment', icon: Shield },
    { id: 'confidence', label: 'Build confidence', detail: 'Self-trust and courage', icon: Zap },
]

interface GoalSelectorProps {
    selected: string[]
    onChange: (goals: string[]) => void
}

export const GoalSelector = ({ selected, onChange }: GoalSelectorProps) => {
    const toggle = (id: string) => {
        onChange(
            selected.includes(id) ? selected.filter((goal) => goal !== id) : [...selected, id]
        )
    }

    return (
        <div className="grid w-full grid-cols-1 gap-3 sm:grid-cols-2">
            {GOALS.map((goal) => {
                const Icon = goal.icon
                const active = selected.includes(goal.id)
                return (
                    <button
                        key={goal.id}
                        type="button"
                        onClick={() => toggle(goal.id)}
                        className={`rounded-2xl border p-4 text-left transition-all active:scale-[0.98] ${
                            active
                                ? 'border-slate-950 bg-slate-950 text-white shadow-lg shadow-slate-200'
                                : 'border-slate-200 bg-slate-50 text-slate-800 hover:border-cyan-300 hover:bg-white'
                        }`}
                    >
                        <div className="flex items-start justify-between gap-3">
                            <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${
                                active ? 'bg-white/10 text-cyan-100' : 'bg-white text-slate-700'
                            }`}>
                                <Icon className="h-5 w-5" />
                            </div>
                            {active && <CheckCircle2 className="h-5 w-5 text-emerald-300" />}
                        </div>
                        <p className="mt-4 text-sm font-black">{goal.label}</p>
                        <p className={`mt-1 text-xs leading-5 ${active ? 'text-slate-300' : 'text-slate-500'}`}>
                            {goal.detail}
                        </p>
                    </button>
                )
            })}
        </div>
    )
}
