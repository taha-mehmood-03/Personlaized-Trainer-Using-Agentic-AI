'use client'

import React from 'react'
import { DashboardStats } from '@/types'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { cn } from '@/lib/utils'

interface StatCardProps {
    title: string
    value: React.ReactNode
    /** Optional icon to show top-left */
    icon?: React.ReactNode
    /** Optional subtext below value */
    sub?: string
    /** Trend indicator */
    trend?: 'up' | 'down' | 'stable'
    /** Highlight color class e.g. 'text-purple-600' */
    color?: string
    /** Background gradient class e.g. 'from-purple-50 to-teal-50' */
    gradient?: string
}

/** Stat summary card with optional icon, trend arrow, and subtext. */
export const StatCard = ({
    title,
    value,
    icon,
    sub,
    trend,
    color = 'text-purple-600',
    gradient = 'from-white to-white',
}: StatCardProps) => {
    const TrendIcon =
        trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : Minus

    const trendColor =
        trend === 'up'
            ? 'text-emerald-500'
            : trend === 'down'
            ? 'text-rose-500'
            : 'text-slate-400'

    return (
        <div
            className={cn(
                'relative p-5 bg-gradient-to-br border border-slate-100 rounded-2xl shadow-sm overflow-hidden group hover:shadow-md transition-shadow',
                gradient
            )}
        >
            <div className="flex items-start justify-between">
                {icon && (
                    <div className={cn('p-2 rounded-xl bg-white shadow-sm border border-slate-100', color)}>
                        {icon}
                    </div>
                )}
                {trend && (
                    <TrendIcon className={cn('w-4 h-4 ml-auto', trendColor)} />
                )}
            </div>

            <div className="mt-3">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{title}</p>
                <p className={cn('text-2xl font-black mt-1 text-slate-900')}>{value}</p>
                {sub && <p className="text-xs text-slate-400 mt-1">{sub}</p>}
            </div>
        </div>
    )
}
