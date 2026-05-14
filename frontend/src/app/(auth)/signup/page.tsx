'use client'

import React, { useState } from 'react'
import Link from 'next/link'
import { signIn } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Eye, EyeOff, CheckCircle } from 'lucide-react'

function PasswordStrength({ password }: { password: string }) {
    const checks = [
        { label: '8+ characters', pass: password.length >= 8 },
        { label: 'Uppercase letter', pass: /[A-Z]/.test(password) },
        { label: 'Number', pass: /[0-9]/.test(password) },
    ]
    const score = checks.filter((c) => c.pass).length
    const barColors = ['bg-red-400', 'bg-amber-400', 'bg-teal-500']
    if (!password) return null
    return (
        <div className="mt-2 space-y-1.5">
            <div className="flex gap-1">
                {[0, 1, 2].map((i) => (
                    <div
                        key={i}
                        className={`h-1 flex-1 rounded-full transition-all ${i < score ? barColors[score - 1] : 'bg-slate-100'}`}
                    />
                ))}
            </div>
            <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                {checks.map((c) => (
                    <span
                        key={c.label}
                        className={`text-xs flex items-center gap-1 ${c.pass ? 'text-teal-600' : 'text-slate-400'}`}
                    >
                        <CheckCircle className="w-3 h-3" />
                        {c.label}
                    </span>
                ))}
            </div>
        </div>
    )
}

export default function SignupPage() {
    const [name, setName] = useState('')
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [showPass, setShowPass] = useState(false)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState('')
    const router = useRouter()

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        setLoading(true)
        setError('')

        // Signup via the credentials provider with mode=signup
        // NextAuth calls authorize() which hits /api/auth/signup on the FastAPI backend
        const result = await signIn('credentials', {
            email,
            password,
            name,
            mode: 'signup',
            redirect: false,
        })

        if (result?.ok) {
            router.push('/onboarding')
        } else {
            setError(
                result?.error === 'CredentialsSignin'
                    ? 'This email may already be registered. Try logging in instead.'
                    : 'Failed to create account. Please try again.'
            )
            setLoading(false)
        }
    }

    return (
        <div className="space-y-5">
            <div>
                <h3 className="text-xl font-bold text-slate-900">Create your account</h3>
                <p className="text-sm text-slate-500 mt-1">Start your wellness journey today — it&apos;s free</p>
            </div>

            {error && (
                <div className="p-3 text-sm text-red-700 bg-red-50 border border-red-200 rounded-xl">
                    {error}
                </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                    <label htmlFor="signup-name" className="block text-sm font-semibold text-slate-700 mb-1.5">
                        Full name
                    </label>
                    <Input
                        id="signup-name"
                        type="text"
                        autoComplete="name"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        required
                        placeholder="Alex Johnson"
                    />
                </div>

                <div>
                    <label htmlFor="signup-email" className="block text-sm font-semibold text-slate-700 mb-1.5">
                        Email address
                    </label>
                    <Input
                        id="signup-email"
                        type="email"
                        autoComplete="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        required
                        placeholder="you@example.com"
                    />
                </div>

                <div>
                    <label htmlFor="signup-password" className="block text-sm font-semibold text-slate-700 mb-1.5">
                        Password
                    </label>
                    <div className="relative">
                        <Input
                            id="signup-password"
                            type={showPass ? 'text' : 'password'}
                            autoComplete="new-password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            required
                            className="pr-10"
                        />
                        <button
                            type="button"
                            onClick={() => setShowPass((v) => !v)}
                            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                            tabIndex={-1}
                            aria-label="Toggle password visibility"
                        >
                            {showPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                        </button>
                    </div>
                    <PasswordStrength password={password} />
                </div>

                <Button type="submit" variant="primary" className="w-full h-11 mt-2" disabled={loading}>
                    {loading ? 'Creating account…' : 'Create account'}
                </Button>
            </form>

            <p className="text-center text-sm text-slate-500">
                Already have an account?{' '}
                <Link href="/login" className="font-semibold text-purple-600 hover:text-purple-500">
                    Sign in
                </Link>
            </p>
        </div>
    )
}
