'use client'

import React, { useState } from 'react'
import Link from 'next/link'
import { signIn } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import {
    AlertCircle,
    ArrowRight,
    CheckCircle2,
    Eye,
    EyeOff,
    LockKeyhole,
    Mail,
    ShieldCheck,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

const LOGIN_READY_ITEMS = ['Saved sessions', 'Mood dashboard', 'Technique preferences']

export function LoginClient() {
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [showPass, setShowPass] = useState(false)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState('')
    const router = useRouter()

    const handleSubmit = async (event: React.FormEvent) => {
        event.preventDefault()
        setLoading(true)
        setError('')

        try {
            const result = await signIn('credentials', {
                email,
                password,
                mode: 'login',
                redirect: false,
            })

            if (result?.ok) {
                router.push('/dashboard')
                return
            }

            setError('Invalid email or password. Please try again.')
            setLoading(false)
        } catch {
            setError('Could not sign in right now. Please try again.')
            setLoading(false)
        }
    }

    return (
        <div className="space-y-6">
            <div>
                <span className="inline-flex items-center gap-2 rounded-full border border-cyan-100 bg-cyan-50 px-3 py-1 text-xs font-semibold text-cyan-700">
                    <ShieldCheck className="h-3.5 w-3.5" />
                    Welcome back
                </span>
                <h1 className="mt-4 text-2xl font-black tracking-tight text-slate-950">
                    Sign in to your wellness dashboard
                </h1>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                    Continue your conversations, review patterns, and keep your personalized support history in sync.
                </p>
            </div>

            <div className="grid grid-cols-3 gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-2">
                {LOGIN_READY_ITEMS.map((item) => (
                    <div key={item} className="rounded-xl bg-white px-2 py-3 text-center shadow-sm">
                        <CheckCircle2 className="mx-auto h-4 w-4 text-emerald-600" />
                        <p className="mt-1 text-[11px] font-bold leading-4 text-slate-600">{item}</p>
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
                    <label htmlFor="login-email" className="mb-1.5 block text-sm font-bold text-slate-700">
                        Email address
                    </label>
                    <div className="relative">
                        <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                        <Input
                            id="login-email"
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
                    <label htmlFor="login-password" className="mb-1.5 block text-sm font-bold text-slate-700">
                        Password
                    </label>
                    <div className="relative">
                        <LockKeyhole className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                        <Input
                            id="login-password"
                            type={showPass ? 'text' : 'password'}
                            autoComplete="current-password"
                            value={password}
                            onChange={(event) => setPassword(event.target.value)}
                            required
                            placeholder="Enter your password"
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
                </div>

                <Button type="submit" className="h-12 w-full gap-2 rounded-xl bg-slate-950 shadow-lg shadow-slate-200 hover:bg-slate-800" disabled={loading}>
                    {loading ? 'Signing in...' : 'Sign in'}
                    {!loading && <ArrowRight className="h-4 w-4" />}
                </Button>
            </form>

            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <div className="flex items-start gap-2">
                    <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
                    <p className="text-xs leading-5 text-slate-600">
                        Your account unlocks saved sessions, long-term dashboard signals, and personalized technique preferences.
                    </p>
                </div>
            </div>

            <p className="text-center text-sm text-slate-500">
                New to SentiMind?{' '}
                <Link href="/signup" className="font-bold text-slate-900 hover:underline">
                    Create an account
                </Link>
            </p>
        </div>
    )
}
