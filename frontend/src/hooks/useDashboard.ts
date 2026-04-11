'use client'

import { useState, useCallback } from 'react'
import { DashboardStats } from '@/types'
import { getUserStats } from '@/actions/dashboard'

export function useDashboard(userId: string) {
    const [stats, setStats] = useState<DashboardStats | null>(null)
    const [loading, setLoading] = useState(false)

    const fetchStats = useCallback(async () => {
        setLoading(true)
        const data = await getUserStats(userId)
        setStats(data)
        setLoading(false)
    }, [userId])

    return {
        stats,
        loading,
        fetchStats,
    }
}
