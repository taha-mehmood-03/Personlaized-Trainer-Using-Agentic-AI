'use client'

import React, { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'

export default function OnboardingPage() {
  const router = useRouter()
  const [step, setStep] = useState(1)

  const handleNext = () => {
    if (step < 3) {
      setStep(step + 1)
    } else {
      router.push('/chat')
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-white rounded-2xl shadow-sm border border-slate-200 p-8 text-center space-y-6">
        
        {step === 1 && (
          <div className="animate-fade-in space-y-4">
            <h2 className="text-2xl font-bold text-slate-900">Welcome to SentiMind</h2>
            <p className="text-slate-500">Your personal AI companion for mental wellness. We are here to listen, without judgment.</p>
          </div>
        )}

        {step === 2 && (
          <div className="animate-fade-in space-y-4">
            <h2 className="text-2xl font-bold text-slate-900">Voice Enabled</h2>
            <p className="text-slate-500">SentiMind can analyze the emotional tone of your voice to provide deeper, more empathetic responses.</p>
          </div>
        )}

        {step === 3 && (
          <div className="animate-fade-in space-y-4">
            <h2 className="text-2xl font-bold text-slate-900">Safe Space</h2>
            <p className="text-slate-500">Your conversations are private. Whenever you are ready, let&apos;s begin.</p>
          </div>
        )}

        {/* Progress dots */}
        <div className="flex justify-center gap-2 pt-4">
          {[1,2,3].map(i => (
            <div key={i} className={`w-2 h-2 rounded-full transition-all ${step === i ? 'bg-purple-600 w-6' : 'bg-slate-200'}`} />
          ))}
        </div>

        <Button onClick={handleNext} variant="primary" className="w-full h-12 text-base">
          {step === 3 ? 'Start Chatting' : 'Next'}
        </Button>
      </div>
    </div>
  )
}
