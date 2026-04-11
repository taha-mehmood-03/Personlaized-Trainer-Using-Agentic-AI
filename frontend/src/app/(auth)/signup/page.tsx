'use client'

import React, { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/components/providers/AuthProvider'

import { signupUser } from '@/actions/auth'

export default function SignupPage() {
  const [name, setName] = useState('')
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
      const user = await signupUser(email, password)
      
      if (user && user.id) {
        login(user.id)
        router.push('/onboarding')
      } else {
        setError('Failed to create account. This email may already be in use.')
        setLoading(false)
      }
    } catch (err) {
      setError('An error occurred during signup. Please try again.')
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-slate-900">Create an account</h3>
        <p className="text-sm text-slate-500">Start your wellness journey</p>
      </div>

      {error && (
        <div className="p-3 text-sm text-red-600 bg-red-50 rounded-lg">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Name</label>
          <Input 
            type="text" 
            autoComplete="name" 
            value={name} 
            onChange={e => setName(e.target.value)} 
            required 
            placeholder="Jane Doe"
          />
        </div>
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
            autoComplete="new-password" 
            value={password} 
            onChange={e => setPassword(e.target.value)} 
            required 
          />
        </div>

        <Button type="submit" variant="primary" className="w-full mt-6" disabled={loading}>
          {loading ? 'Creating account...' : 'Create account'}
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
