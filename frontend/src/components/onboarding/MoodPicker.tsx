'use client'

import React from 'react'
import { CloudRain, Frown, Meh, Smile, SunMedium, type LucideIcon } from 'lucide-react'
import { MoodLevel } from '@/types'

interface MoodOption {
    value: MoodLevel
    icon: LucideIcon
    label: string
    detail: string
    tone: string
    active: string
}

const MOODS: MoodOption[] = [
    {
        value: 'great',
        icon: SunMedium,
        label: 'Great',
        detail: 'Energized and steady',
        tone: 'border-emerald-200 bg-emerald-50 text-emerald-800',
        active: 'ring-2 ring-emerald-500 border-emerald-400',
    },
    {
        value: 'good',
        icon: Smile,
        label: 'Good',
        detail: 'Mostly okay today',
        tone: 'border-cyan-200 bg-cyan-50 text-cyan-800',
        active: 'ring-2 ring-cyan-500 border-cyan-400',
    },
    {
        value: 'okay',
        icon: Meh,
        label: 'Okay',
        detail: 'Neutral or mixed',
        tone: 'border-amber-200 bg-amber-50 text-amber-800',
        active: 'ring-2 ring-amber-500 border-amber-400',
    },
    {
        value: 'low',
        icon: Frown,
        label: 'Low',
        detail: 'Heavy or drained',
        tone: 'border-orange-200 bg-orange-50 text-orange-800',
        active: 'ring-2 ring-orange-500 border-orange-400',
    },
    {
        value: 'awful',
        icon: CloudRain,
        label: 'Awful',
        detail: 'Really struggling',
        tone: 'border-rose-200 bg-rose-50 text-rose-800',
        active: 'ring-2 ring-rose-500 border-rose-400',
    },
]

interface MoodPickerProps {
    selected: MoodLevel | null
    onChange: (mood: MoodLevel) => void
}

export const MoodPicker = ({ selected, onChange }: MoodPickerProps) => (
    <div className="grid w-full grid-cols-1 gap-3 sm:grid-cols-2">
        {MOODS.map((mood) => {
            const Icon = mood.icon
            const active = selected === mood.value
            return (
                <button
                    key={mood.value}
                    type="button"
                    onClick={() => onChange(mood.value)}
                    className={`rounded-2xl border p-4 text-left transition-all active:scale-[0.98] ${mood.tone} ${
                        active ? mood.active : 'hover:border-slate-300'
                    }`}
                >
                    <div className="flex items-start justify-between gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/80">
                            <Icon className="h-5 w-5" />
                        </div>
                        {active && (
                            <span className="rounded-full bg-white px-2 py-1 text-[11px] font-black">
                                Selected
                            </span>
                        )}
                    </div>
                    <p className="mt-4 text-base font-black">{mood.label}</p>
                    <p className="mt-1 text-xs font-semibold opacity-75">{mood.detail}</p>
                </button>
            )
        })}
    </div>
)
