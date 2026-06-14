'use client'

import React, { useMemo, useState } from 'react'
import Link from 'next/link'
import { signIn } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import {
    AlertCircle,
    ArrowRight,
    BarChart3,
    CheckCircle2,
    Eye,
    EyeOff,
    LockKeyhole,
    Mail,
    ShieldCheck,
    UserRound,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

const ACCOUNT_SETUP_ITEMS = [
    { label: 'Profile', body: 'Name and secure login' },
    { label: 'Preferences', body: 'Personalized support path' },
    { label: 'Analytics', body: 'Mood and outcome history' },
]

const CONSENT_VERSION = '2026-05-24'
const PRIVACY_NOTICE_VERSION = '2026-05-24'
const TERMS_VERSION = '2026-05-24'

function PasswordStrength({ password }: { password: string }) {
    const checks = useMemo(
        () => [
            { label: '8+ characters', pass: password.length >= 8 },
            { label: 'Uppercase letter', pass: /[A-Z]/.test(password) },
            { label: 'Number', pass: /[0-9]/.test(password) },
        ],
        [password]
    )
    const score = checks.filter((check) => check.pass).length

    if (!password) return null

    const label = score === 3 ? 'Strong' : score === 2 ? 'Good' : 'Weak'
    const color = score === 3 ? 'bg-emerald-500' : score === 2 ? 'bg-amber-500' : 'bg-rose-500'

    return (
        <div className="mt-3 space-y-2">
            <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-slate-500">Password strength</span>
                <span className="font-bold text-slate-700">{label}</span>
            </div>
            <div className="grid grid-cols-3 gap-1">
                {[0, 1, 2].map((index) => (
                    <div
                        key={index}
                        className={`h-1.5 rounded-full transition-colors ${index < score ? color : 'bg-slate-100'}`}
                    />
                ))}
            </div>
            <div className="flex flex-wrap gap-2">
                {checks.map((check) => (
                    <span
                        key={check.label}
                        className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-[11px] font-semibold ${
                            check.pass ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'
                        }`}
                    >
                        <CheckCircle2 className="h-3 w-3" />
                        {check.label}
                    </span>
                ))}
            </div>
        </div>
    )
}

export function SignupClient() {
    const [name, setName] = useState('')
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [showPass, setShowPass] = useState(false)
    const [consentAccepted, setConsentAccepted] = useState(false)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState('')
    const router = useRouter()

    const handleSubmit = async (event: React.FormEvent) => {
        event.preventDefault()
        setLoading(true)
        setError('')

        const strongEnough = password.length >= 8 && /[A-Z]/.test(password) && /[0-9]/.test(password)
        if (!strongEnough) {
            setError('Use at least 8 characters with an uppercase letter and a number.')
            setLoading(false)
            return
        }

        try {
            const result = await signIn('credentials', {
                email,
                password,
                name,
                mode: 'signup',
                consentAccepted: consentAccepted ? 'true' : 'false',
                consentVersion: CONSENT_VERSION,
                privacyNoticeVersion: PRIVACY_NOTICE_VERSION,
                termsVersion: TERMS_VERSION,
                redirect: false,
            })

            if (result?.ok) {
                router.push('/onboarding')
                return
            }

            setError(
                result?.error === 'CredentialsSignin'
                    ? 'This email may already be registered. Try logging in instead.'
                    : 'Failed to create account. Please try again.'
            )
            setLoading(false)
        } catch {
            setError('Could not create your account right now. Please try again.')
            setLoading(false)
        }
    }

    return (
        <div className="space-y-6">
            <div>
                <span className="inline-flex items-center gap-2 rounded-full border border-emerald-100 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
                    <BarChart3 className="h-3.5 w-3.5" />
                    Create workspace
                </span>
                <h1 className="mt-4 text-2xl font-black tracking-tight text-slate-950">
                    Start with a secure wellness account
                </h1>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                    Save your sessions, track outcomes over time, and let SentiMind personalize support from real feedback.
                </p>
            </div>

            <div className="grid grid-cols-3 gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-2">
                {ACCOUNT_SETUP_ITEMS.map((item, index) => (
                    <div key={item.label} className="rounded-xl bg-white p-3 shadow-sm">
                        <div className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-950 text-[11px] font-black text-white">
                            {index + 1}
                        </div>
                        <p className="mt-2 text-xs font-black text-slate-900">{item.label}</p>
                        <p className="mt-1 text-[11px] leading-4 text-slate-500">{item.body}</p>
                    </div>
                ))}
            </div>

            {error && (
                <div className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
                    <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                    {error}
                </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                    <label htmlFor="signup-name" className="mb-1.5 block text-sm font-bold text-slate-700">
                        Full name
                    </label>
                    <div className="relative">
                        <UserRound className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                        <Input
                            id="signup-name"
                            type="text"
                            autoComplete="name"
                            value={name}
                            onChange={(event) => setName(event.target.value)}
                            required
                            placeholder="Alex Johnson"
                            className="h-12 border-slate-200 bg-slate-50 pl-10 focus-visible:bg-white"
                        />
                    </div>
                </div>

                <div>
                    <label htmlFor="signup-email" className="mb-1.5 block text-sm font-bold text-slate-700">
                        Email address
                    </label>
                    <div className="relative">
                        <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                        <Input
                            id="signup-email"
                            type="email"
                            autoComplete="email"
                            value={email}
                            onChange={(event) => setEmail(event.target.value)}
                            required
                            placeholder="you@example.com"
                            className="h-12 border-slate-200 bg-slate-50 pl-10 focus-visible:bg-white"
                        />
                    </div>
                </div>

                <div>
                    <label htmlFor="signup-password" className="mb-1.5 block text-sm font-bold text-slate-700">
                        Password
                    </label>
                    <div className="relative">
                        <LockKeyhole className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                        <Input
                            id="signup-password"
                            type={showPass ? 'text' : 'password'}
                            autoComplete="new-password"
                            value={password}
                            onChange={(event) => setPassword(event.target.value)}
                            required
                            placeholder="Create a password"
                            className="h-12 border-slate-200 bg-slate-50 pl-10 pr-11 focus-visible:bg-white"
                        />
                        <button
                            type="button"
                            onClick={() => setShowPass((value) => !value)}
                            className="absolute right-3 top-1/2 -translate-y-1/2 rounded-lg p-1 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
                            aria-label="Toggle password visibility"
                        >
                            {showPass ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                        </button>
                    </div>
                    <PasswordStrength password={password} />
                </div>

                {/* GDPR Art. 7 — Explicit affirmative consent */}
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                    <label htmlFor="gdpr-consent" className="flex cursor-pointer items-start gap-3">
                        <input
                            id="gdpr-consent"
                            type="checkbox"
                            checked={consentAccepted}
                            onChange={(e) => setConsentAccepted(e.target.checked)}
                            className="mt-0.5 h-4 w-4 flex-shrink-0 cursor-pointer accent-slate-900"
                            required
                        />
                        <span className="text-xs leading-5 text-slate-600">
                            I agree to the{' '}
                            <Link href="/terms" target="_blank" className="font-semibold text-slate-900 underline underline-offset-2 hover:text-slate-700">
                                Terms of Service
                            </Link>
                            {' '}and{' '}
                            <Link href="/privacy" target="_blank" className="font-semibold text-slate-900 underline underline-offset-2 hover:text-slate-700">
                                Privacy Policy
                            </Link>
                            , and consent to the processing of my data for account management. I can withdraw consent at any time from my profile settings.
                        </span>
                    </label>
                </div>

                <Button 
                    type="submit" 
                    className="h-12 w-full gap-2 rounded-xl bg-slate-950 shadow-lg shadow-slate-200 hover:bg-slate-800 disabled:opacity-50" 
                    disabled={loading || !consentAccepted}
                >
                    {loading ? 'Creating account...' : 'Create account'}
                    {!loading && <ArrowRight className="h-4 w-4" />}
                </Button>
            </form>

            <div className="grid grid-cols-1 gap-2 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
                <div className="flex items-start gap-2">
                    <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
                    <span>Creates your profile, preferences, and statistics record automatically.</span>
                </div>
                <div className="flex items-start gap-2">
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
                    <span>Your dashboard improves as mood logs and technique feedback accumulate.</span>
                </div>
            </div>

            <p className="text-center text-sm text-slate-500">
                Already have an account?{' '}
                <Link href="/login" className="font-bold text-slate-900 hover:underline">
                    Sign in
                </Link>
            </p>
        </div>
    )
}
