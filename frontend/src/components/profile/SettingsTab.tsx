'use client'

import React from 'react'
import { cn } from '@/lib/utils'

interface SettingsTabProps {
    label: string
    icon: React.ReactNode
    active?: boolean
    onClick: () => void
}

/** Vertical tab button for the profile/settings sidebar nav. */
export const SettingsTab = ({ label, icon, active, onClick }: SettingsTabProps) => (
    <button
        onClick={onClick}
        className={cn(
            'w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-colors text-left',
            active
                ? 'bg-purple-600 text-white shadow-sm'
                : 'text-slate-600 hover:bg-slate-100'
        )}
    >
        <span className={cn('w-4 h-4 shrink-0', active ? 'text-white' : 'text-slate-400')}>
            {icon}
        </span>
        {label}
    </button>
)
