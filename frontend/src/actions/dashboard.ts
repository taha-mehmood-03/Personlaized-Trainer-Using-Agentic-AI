'use server'

import { api } from '@/lib/api'
import { DashboardStats } from '@/types'

// ─── Dashboard Actions ──────────────────────────────────────────────────────

export async function getUserStats(userId: string): Promise<DashboardStats | null> {
    // Stub for dashboard implementation
    return {
        totalSessions: 12,
        avgMood: 75,
        streak: 3,
        topEmotion: 'joy',
    }
}
