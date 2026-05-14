'use client'

import React from 'react'
import { MoodLevel } from '@/types'

interface MoodOption {
    value: MoodLevel
    emoji: string
    label: string
    color: string
    bg: string
}

const MOODS: MoodOption[] = [
    { value: 'great', emoji: '😄', label: 'Great', color: 'text-emerald-700', bg: 'bg-emerald-50 border-emerald-200 hover:border-emerald-400' },
    { value: 'good', emoji: '🙂', label: 'Good', color: 'text-teal-700', bg: 'bg-teal-50 border-teal-200 hover:border-teal-400' },
    { value: 'okay', emoji: '😐', label: 'Okay', color: 'text-amber-700', bg: 'bg-amber-50 border-amber-200 hover:border-amber-400' },
    { value: 'low', emoji: '😔', label: 'Low', color: 'text-orange-700', bg: 'bg-orange-50 border-orange-200 hover:border-orange-400' },
    { value: 'awful', emoji: '😞', label: 'Awful', color: 'text-red-700', bg: 'bg-red-50 border-red-200 hover:border-red-400' },
]

interface MoodPickerProps {
    selected: MoodLevel | null
    onChange: (mood: MoodLevel) => void
}

/** Emoji mood selector grid for onboarding step 1. */
export const MoodPicker = ({ selected, onChange }: MoodPickerProps) => (
    <div className="flex flex-col gap-3 w-full">
        {MOODS.map((mood) => (
            <button
                key={mood.value}
                onClick={() => onChange(mood.value)}
                className={`
                    flex items-center gap-4 w-full px-5 py-4 rounded-2xl border-2 text-left
                    transition-all duration-200 active:scale-[0.98]
                    ${mood.bg} ${mood.color}
                    ${selected === mood.value ? 'ring-2 ring-offset-2 ring-purple-500 scale-[1.01]' : ''}
                `}
            >
                <span className="text-3xl">{mood.emoji}</span>
                <span className="text-base font-bold">{mood.label}</span>
                {selected === mood.value && (
                    <span className="ml-auto text-purple-600 font-bold text-lg">✓</span>
                )}
            </button>
        ))}
    </div>
)
