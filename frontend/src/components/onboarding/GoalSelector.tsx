'use client'

import React from 'react'

interface Goal {
    id: string
    label: string
    emoji: string
}

const GOALS: Goal[] = [
    { id: 'anxiety', label: 'Manage Anxiety', emoji: '🧘' },
    { id: 'stress', label: 'Reduce Stress', emoji: '🌿' },
    { id: 'sleep', label: 'Better Sleep', emoji: '🌙' },
    { id: 'mood', label: 'Improve Mood', emoji: '☀️' },
    { id: 'focus', label: 'Increase Focus', emoji: '🎯' },
    { id: 'relationships', label: 'Relationships', emoji: '💛' },
    { id: 'grief', label: 'Process Grief', emoji: '🕊️' },
    { id: 'confidence', label: 'Build Confidence', emoji: '🌟' },
]

interface GoalSelectorProps {
    selected: string[]
    onChange: (goals: string[]) => void
}

/** Multi-select chip grid for onboarding wellness goals. */
export const GoalSelector = ({ selected, onChange }: GoalSelectorProps) => {
    const toggle = (id: string) => {
        onChange(
            selected.includes(id) ? selected.filter((g) => g !== id) : [...selected, id]
        )
    }

    return (
        <div className="grid grid-cols-2 gap-3 w-full">
            {GOALS.map((goal) => {
                const active = selected.includes(goal.id)
                return (
                    <button
                        key={goal.id}
                        onClick={() => toggle(goal.id)}
                        className={`
                            flex items-center gap-3 px-4 py-3 rounded-2xl border-2 text-left
                            transition-all duration-200 active:scale-[0.97]
                            ${
                                active
                                    ? 'bg-purple-600 border-purple-600 text-white shadow-md shadow-purple-200'
                                    : 'bg-white border-slate-200 text-slate-700 hover:border-purple-300'
                            }
                        `}
                    >
                        <span className="text-xl">{goal.emoji}</span>
                        <span className="text-sm font-semibold">{goal.label}</span>
                    </button>
                )
            })}
        </div>
    )
}
