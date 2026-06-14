import { type NextAuthOptions, type User as NextAuthUser } from 'next-auth'
import CredentialsProvider from 'next-auth/providers/credentials'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api'
const CONSENT_VERSION = '2026-05-24'
const PRIVACY_NOTICE_VERSION = '2026-05-24'
const TERMS_VERSION = '2026-05-24'

/**
 * Centralized NextAuth options.
 * Import this in server actions that need getServerSession().
 */
export const authOptions: NextAuthOptions = {
    providers: [
        CredentialsProvider({
            id: 'credentials',
            name: 'SentiMind',
            credentials: {
                email:    { label: 'Email',    type: 'email' },
                password: { label: 'Password', type: 'password' },
                name:     { label: 'Name',     type: 'text' },
                mode:     { label: 'Mode',     type: 'text' }, // 'login' | 'signup'
                consentAccepted: { label: 'Consent Accepted', type: 'text' },
                consentVersion: { label: 'Consent Version', type: 'text' },
                privacyNoticeVersion: { label: 'Privacy Notice Version', type: 'text' },
                termsVersion: { label: 'Terms Version', type: 'text' },
            },

            async authorize(credentials): Promise<NextAuthUser | null> {
                if (!credentials?.email || !credentials?.password) return null

                const mode     = credentials.mode ?? 'login'
                const endpoint = mode === 'signup' ? '/auth/signup' : '/auth/login'

                const body: Record<string, string> = {
                    email:    credentials.email,
                    password: credentials.password,
                }
                if (mode === 'signup' && credentials.name) {
                    body.name = credentials.name
                }
                if (mode === 'signup') {
                    body.consent_accepted = credentials.consentAccepted === 'true' ? 'true' : 'false'
                    body.consent_version = credentials.consentVersion || CONSENT_VERSION
                    body.privacy_notice_version = credentials.privacyNoticeVersion || PRIVACY_NOTICE_VERSION
                    body.terms_version = credentials.termsVersion || TERMS_VERSION
                }

                try {
                    const res = await fetch(`${API_BASE}${endpoint}`, {
                        method:  'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body:    JSON.stringify(body),
                        cache:   'no-store',
                    })

                    if (!res.ok) return null

                    const data = await res.json() as {
                        status:   string
                        user_id?: string
                        name?:    string
                        email?:   string
                    }

                    if (data.status !== 'success' || !data.user_id) return null

                    return {
                        id:    data.user_id,
                        name:  data.name  ?? credentials.email.split('@')[0],
                        email: data.email ?? credentials.email,
                    }
                } catch (err) {
                    console.error('[NextAuth] authorize error:', err)
                    return null
                }
            },
        }),
    ],

    callbacks: {
        /** Persist user_id into JWT token */
        async jwt({ token, user }) {
            if (user) {
                token.id    = user.id
                token.name  = user.name
                token.email = user.email
            }
            return token
        },

        /** Expose id on session.user so client code can read it */
        async session({ session, token }) {
            if (token) {
                session.user.id    = token.id
                session.user.name  = token.name  ?? null
                session.user.email = token.email ?? null
            }
            return session
        },
    },

    pages: {
        signIn: '/login',
        error:  '/login',
    },

    session: {
        strategy: 'jwt',
        maxAge:   30 * 24 * 60 * 60, // 30 days
    },

    secret: process.env.NEXTAUTH_SECRET,
}
