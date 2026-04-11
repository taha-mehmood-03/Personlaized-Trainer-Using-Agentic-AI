'use client'

import React, { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/components/providers/AuthProvider'

import { loginUser } from '@/actions/auth'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const router = useRouter()
  const { login } = useAuth()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    try {
      const user = await loginUser(email, password)
      
      if (user && user.id) {
        // success! Update Context, write cookie, and redirect
        login(user.id)
        router.push('/dashboard')
      } else {
        setError('Invalid email or password.')
        setLoading(false)
      }
    } catch (err) {
      setError('An error occurred during login. Please try again.')
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-slate-900">Welcome back</h3>
        <p className="text-sm text-slate-500">Sign in to your account</p>
      </div>

      {error && (
        <div className="p-3 text-sm text-red-600 bg-red-50 rounded-lg">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Email</label>
          <Input 
            type="email" 
            autoComplete="email" 
            value={email} 
            onChange={e => setEmail(e.target.value)} 
            required 
            placeholder="you@example.com" 
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Password</label>
          <Input 
            type="password" 
            autoComplete="current-password" 
            value={password} 
            onChange={e => setPassword(e.target.value)} 
            required 
          />
        </div>
        <div className="flex items-center justify-between">
          <div className="flex items-center">
            <input id="remember-me" name="remember-me" type="checkbox" className="h-4 w-4 rounded border-slate-300 text-purple-600 focus:ring-purple-600" />
            <label htmlFor="remember-me" className="ml-2 block text-sm text-slate-900">Remember me</label>
          </div>
          <div className="text-sm leading-6">
            <a href="#" className="font-semibold text-purple-600 hover:text-purple-500">Forgot password?</a>
          </div>
        </div>

        <Button type="submit" variant="primary" className="w-full" disabled={loading}>
          {loading ? 'Signing in...' : 'Sign in'}
        </Button>
      </form>

      <p className="text-center text-sm text-slate-500">
        Don&apos;t have an account?{' '}
        <Link href="/signup" className="font-semibold text-purple-600 hover:text-purple-500">
          Sign up
        </Link>
      </p>
    </div>
  )
}
