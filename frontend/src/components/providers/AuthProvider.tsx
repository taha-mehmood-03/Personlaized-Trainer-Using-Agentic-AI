'use client'

/**
 * Thin wrapper around NextAuth SessionProvider.
 * No custom state — all auth comes from next-auth's built-in session.
 */
import { SessionProvider } from 'next-auth/react'

export function AuthProvider({ children }: { children: React.ReactNode }) {
    return <SessionProvider>{children}</SessionProvider>
}

// Keep useAuth as a deprecated shim so old imports don't break during migration.
// Prefer using `useSession` from 'next-auth/react' directly in new code.
export { useSession as useAuth } from 'next-auth/react'
