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
        try {
            const updated = await getSessions(userId)
            setSessions(updated)
        } finally {
            setLoadingSessions(false)
        }
    }, [userId])

    const startNewSession = useCallback(() => {
        setCurrentSessionId(null)
    }, [])

    const selectSession = useCallback((id: string) => {
        setCurrentSessionId(id)
    }, [])

    const removeSession = useCallback(
        async (id: string) => {
            // Optimistic update — remove immediately from UI
            const previousSessions = sessions
            setSessions((prev) => prev.filter((s) => s.id !== id))

            // If we're deleting the active session, clear it
            if (currentSessionId === id) {
                startNewSession()
            }

            // Persist to backend
            const success = await deleteSession(id)
            if (!success) {
                // Rollback on failure
                console.error('[useChat] Session delete failed — rolling back UI')
                setSessions(previousSessions)
                if (currentSessionId === id) {
                    setCurrentSessionId(id)
                }
            }
        },
        [currentSessionId, sessions, startNewSession]
    )

    const updateSessionName = useCallback(async (id: string, title: string) => {
        // Optimistic rename
        setSessions((prev) =>
            prev.map((s) => (s.id === id ? { ...s, title } : s))
        )
        const success = await renameSession(id, title)
        if (!success) {
            // Rollback — re-fetch sessions
            console.error('[useChat] Session rename failed — refreshing sessions')
            await refreshSessions()
        }
    }, [refreshSessions])

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
