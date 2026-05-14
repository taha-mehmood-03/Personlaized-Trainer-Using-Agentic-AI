'use client'

import React, { useEffect, useState } from 'react'
import Link from 'next/link'
import { StatCard } from '@/components/dashboard/StatCard'
import { MoodChart } from '@/components/dashboard/MoodChart'
import { EmotionDistribution } from '@/components/dashboard/EmotionDistribution'
import { TopTechniques } from '@/components/dashboard/TopTechniques'
import { SessionHistoryTable } from '@/components/dashboard/SessionHistoryTable'
import { PsychologicalProfileCard } from '@/components/dashboard/PsychologicalProfileCard'
import { useSession } from 'next-auth/react'
import { useDashboard } from '@/hooks/useDashboard'
import {
    LayoutGrid,
    History,
    Lightbulb,
    Flame,
    TrendingUp,
    Smile,
    Dumbbell,
    AlertCircle,
} from 'lucide-react'

const NAV_LINKS = [
    { href: '/dashboard', label: 'Dashboard', icon: LayoutGrid },
    { href: '/chat', label: 'Sessions', icon: History },
    { href: '/chat', label: 'Techniques', icon: Lightbulb },
]

const STAT_SKELETON = Array.from({ length: 4 })

export default function DashboardPage() {
    const { data: session } = useSession()
    const userId = session?.user?.id ?? null
    const { stats, loading, error, fetchStats } = useDashboard(userId)

    useEffect(() => {
        if (userId) fetchStats()
    }, [fetchStats, userId])

    return (
        <div className="flex h-full">
            {/* Inner sidebar nav */}
            <nav className="hidden lg:flex flex-col gap-1 w-44 shrink-0 border-r border-slate-100 pr-4 py-2">
                {NAV_LINKS.map(({ href, label, icon: Icon }) => (
                    <Link
                        key={label}
                        href={href}
                        className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm font-medium text-slate-600 hover:bg-purple-50 hover:text-purple-700 transition-colors"
                    >
                        <Icon className="w-4 h-4" />
                        {label}
                    </Link>
                ))}
            </nav>

            {/* Main content */}
            <div className="flex-1 min-w-0 overflow-y-auto space-y-6 pb-10 lg:pl-6">
                {/* Header */}
                <div>
                    <h1 className="text-2xl font-black text-slate-900 tracking-tight">
                        Your Wellness Journey
                    </h1>
                    <p className="text-slate-500 mt-1">
                        Personalized mental health insights and progress.
                    </p>
                </div>

                {error && (
                    <div className="flex items-center gap-2 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">
                        <AlertCircle className="w-4 h-4 shrink-0" />
                        {error}
                    </div>
                )}

                {/* KPI cards */}
                {loading || !stats ? (
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                        {STAT_SKELETON.map((_, i) => (
                            <div key={i} className="h-28 bg-slate-100 rounded-2xl animate-pulse" />
                        ))}
                    </div>
                ) : (
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                        <StatCard
                            title="Sessions This Week"
                            value={stats.sessionsThisWeek}
                            icon={<History className="w-4 h-4" />}
                            sub={`${stats.totalSessions} total`}
                            gradient="from-purple-50 to-indigo-50"
                            color="text-purple-600"
                        />
                        <StatCard
                            title="Dominant Emotion"
                            value={<span className="capitalize">{stats.topEmotion}</span>}
                            icon={<Smile className="w-4 h-4" />}
                            gradient="from-amber-50 to-orange-50"
                            color="text-amber-600"
                        />
                        <StatCard
                            title="Mood Trend"
                            value={`${stats.avgMood}%`}
                            icon={<TrendingUp className="w-4 h-4" />}
                            trend={stats.moodTrend}
                            gradient="from-teal-50 to-cyan-50"
                            color="text-teal-600"
                        />
                        <StatCard
                            title="Techniques Tried"
                            value={stats.techniquesTried}
                            icon={<Dumbbell className="w-4 h-4" />}
                            sub={`${stats.streak}d streak 🔥`}
                            gradient="from-rose-50 to-pink-50"
                            color="text-rose-600"
                        />
                    </div>
                )}

                {/* Charts row */}
                {loading || !stats ? (
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                        <div className="h-64 bg-slate-100 rounded-2xl animate-pulse" />
                        <div className="h-64 bg-slate-100 rounded-2xl animate-pulse" />
                    </div>
                ) : (
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                        <MoodChart data={stats.moodTimeline} />
                        <EmotionDistribution data={stats.emotionDistribution} />
                    </div>
                )}

                {/* Techniques + Profile row */}
                {loading || !stats ? (
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                        <div className="h-64 bg-slate-100 rounded-2xl animate-pulse" />
                        <div className="h-64 bg-slate-100 rounded-2xl animate-pulse" />
                    </div>
                ) : (
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                        <TopTechniques data={stats.topTechniques} />
                        <PsychologicalProfileCard profile={stats.psychologicalProfile} />
                    </div>
                )}

                {/* Session history */}
                {!loading && stats && (
                    <SessionHistoryTable sessions={stats.recentSessions} />
                )}
                {loading && (
                    <div className="h-48 bg-slate-100 rounded-2xl animate-pulse" />
                )}

                <p className="text-center text-xs text-slate-400 pt-4">
                    © 2024 SentiMind Mental Health. Your data is encrypted and private.
                </p>
            </div>
        </div>
    )
}
