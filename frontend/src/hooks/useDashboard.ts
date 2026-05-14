'use client'

import { useState, useCallback } from 'react'
import { getUserStats } from '@/actions/dashboard'
import { DashboardStats } from '@/types'

interface UseDashboardReturn {
    stats: DashboardStats | null
    loading: boolean
    error: string | null
    fetchStats: () => Promise<void>
}

export function useDashboard(userId: string | null): UseDashboardReturn {
    const [stats, setStats] = useState<DashboardStats | null>(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const fetchStats = useCallback(async () => {
        if (!userId) {
            setError('Sign in to view your dashboard.')
            return
        }

        setLoading(true)
        setError(null)

        try {
            const data = await getUserStats(userId)
            if (data) {
                setStats(data)
            } else {
                setError('Could not load your stats. Start chatting to generate insights!')
            }
        } catch (err) {
            console.error('[useDashboard] fetchStats error:', err)
            setError('Failed to connect to the server. Please check your connection.')
        } finally {
            setLoading(false)
        }
    }, [userId])

    return { stats, loading, error, fetchStats }
}
