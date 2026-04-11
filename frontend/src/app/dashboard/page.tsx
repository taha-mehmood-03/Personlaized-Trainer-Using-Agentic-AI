'use client'

import React, { useEffect } from 'react'
import { StatCard } from '@/components/dashboard/StatCard'
import { useAuth } from '@/components/providers/AuthProvider'
import { useDashboard } from '@/hooks/useDashboard'

export default function DashboardPage() {
  const { userId } = useAuth()
  const { stats, loading, fetchStats } = useDashboard(userId || 'anonymous')

  useEffect(() => {
    fetchStats()
  }, [fetchStats])

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Your Wellness Dashboard</h1>
        <p className="text-slate-500">Track your progress and emotional journey.</p>
      </div>

      {loading || !stats ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[1,2,3,4].map(i => <div key={i} className="h-32 bg-slate-100 rounded-xl animate-pulse" />)}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard title="Total Sessions" value={stats.totalSessions} />
          <StatCard title="Average Mood" value={`${stats.avgMood}%`} />
          <StatCard title="Current Streak" value={`${stats.streak} days`} />
          <StatCard title="Top Emotion" value={<span className="capitalize">{stats.topEmotion}</span>} />
        </div>
      )}

      {/* Placeholder for future charts */}
      <div className="h-64 bg-white border border-slate-200 rounded-xl flex items-center justify-center shadow-sm">
        <p className="text-slate-400 font-medium">Mood Chart (Coming Soon)</p>
      </div>
    </div>
  )
}
