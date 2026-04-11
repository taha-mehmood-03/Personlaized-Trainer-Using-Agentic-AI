'use client'

import { useState, useCallback } from 'react'
import { Session, Message, Technique } from '@/types'
import { getSessions, deleteSession, renameSession } from '@/actions/chat'

// Manage sidebar sessions and selection state
export function useChat(userId: string, initialSessions: Session[]) {
    const [sessions, setSessions] = useState<Session[]>(initialSessions)
    const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
    const [loadingSessions, setLoadingSessions] = useState(false)

    const refreshSessions = useCallback(async () => {
        setLoadingSessions(true)
        const updated = await getSessions(userId)
        setSessions(updated)
        setLoadingSessions(false)
    }, [userId])

    const startNewSession = useCallback(() => {
        setCurrentSessionId(null)
    }, [])

    const selectSession = useCallback((id: string) => {
        setCurrentSessionId(id)
    }, [])

    const removeSession = useCallback(
        async (id: string) => {
            await deleteSession(id)
            setSessions((prev) => prev.filter((s) => s.id !== id))
            if (currentSessionId === id) startNewSession()
        },
        [currentSessionId, startNewSession]
    )

    const updateSessionName = useCallback(async (id: string, title: string) => {
        await renameSession(id, title)
        setSessions((prev) =>
            prev.map((s) => (s.id === id ? { ...s, title } : s))
        )
    }, [])

    return {
        sessions,
        currentSessionId,
        loadingSessions,
        refreshSessions,
        startNewSession,
        selectSession,
        removeSession,
        updateSessionName,
        setCurrentSessionId, // Used internally to set after first creation
    }
}
