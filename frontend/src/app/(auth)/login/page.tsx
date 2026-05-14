'use client'

import React, { useState } from 'react'
import Link from 'next/link'
import { signIn } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Eye, EyeOff } from 'lucide-react'

export default function LoginPage() {
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

        // NextAuth built-in signIn with credentials provider
        const result = await signIn('credentials', {
            email,
            password,
            mode: 'login',
            redirect: false, // handle redirect manually so we can show errors
        })

        if (result?.ok) {
            router.push('/dashboard')
        } else {
            setError('Invalid email or password. Please try again.')
            setLoading(false)
        }
    }

    return (
        <div className="space-y-5">
            <div>
                <h3 className="text-xl font-bold text-slate-900">Welcome back</h3>
                <p className="text-sm text-slate-500 mt-1">Sign in to your SentiMind account</p>
            </div>

            {error && (
                <div className="p-3 text-sm text-red-700 bg-red-50 border border-red-200 rounded-xl">
                    {error}
                </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                    <label htmlFor="login-email" className="block text-sm font-semibold text-slate-700 mb-1.5">
                        Email address
                    </label>
                    <Input
                        id="login-email"
                        type="email"
                        autoComplete="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        required
                        placeholder="you@example.com"
                    />
                </div>

                <div>
                    <label htmlFor="login-password" className="block text-sm font-semibold text-slate-700 mb-1.5">
                        Password
                    </label>
                    <div className="relative">
                        <Input
                            id="login-password"
                            type={showPass ? 'text' : 'password'}
                            autoComplete="current-password"
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
                </div>

                <div className="flex items-center justify-between text-sm">
                    <label className="flex items-center gap-2 cursor-pointer select-none">
                        <input
                            id="remember-me"
                            type="checkbox"
                            className="h-4 w-4 rounded border-slate-300 text-purple-600 focus:ring-purple-500"
                        />
                        <span className="text-slate-600">Remember me</span>
                    </label>
                    <a href="#" className="font-semibold text-purple-600 hover:text-purple-500">
                        Forgot password?
                    </a>
                </div>

                <Button type="submit" variant="primary" className="w-full h-11" disabled={loading}>
                    {loading ? 'Signing in…' : 'Sign in'}
                </Button>
            </form>

            <p className="text-center text-sm text-slate-500">
                Don&apos;t have an account?{' '}
                <Link href="/signup" className="font-semibold text-purple-600 hover:text-purple-500">
                    Create one
                </Link>
            </p>
        </div>
    )
}
