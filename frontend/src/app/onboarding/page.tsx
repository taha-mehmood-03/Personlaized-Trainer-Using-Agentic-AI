'use client'

import React, { useState } from 'react'
import { useRouter } from 'next/navigation'
import { OnboardingStep } from '@/components/onboarding/OnboardingStep'
import { MoodPicker } from '@/components/onboarding/MoodPicker'
import { GoalSelector } from '@/components/onboarding/GoalSelector'
import { ToggleSetting } from '@/components/profile/ToggleSetting'
import { useSession } from 'next-auth/react'
import { api } from '@/lib/api'
import { OnboardingData, MoodLevel } from '@/types'

export default function OnboardingPage() {
    const router = useRouter()
    const { data: session } = useSession()
    const userId = session?.user?.id ?? null

    const [step, setStep] = useState(1)
    const [data, setData] = useState<OnboardingData>({
        mood: null,
        goals: [],
        notificationsEnabled: true,
    })
    const [saving, setSaving] = useState(false)

    const handleFinish = async () => {
        setSaving(true)
        try {
            // Persist onboarding answers to the API
            await api.post('/user/onboarding', {
                user_id: userId,
                initial_mood: data.mood,
                goals: data.goals,
                notifications_enabled: data.notificationsEnabled,
            })
        } catch {
            // Non-critical — continue to chat regardless
        } finally {
            setSaving(false)
            router.push('/chat')
        }
    }

    if (step === 1) {
        return (
            <OnboardingStep
                step={1}
                totalSteps={3}
                title="How are you feeling lately?"
                subtitle="This helps us personalize your experience and provide better insights."
                onNext={() => setStep(2)}
                nextDisabled={!data.mood}
            >
                <MoodPicker
                    selected={data.mood}
                    onChange={(mood: MoodLevel) => setData((d) => ({ ...d, mood }))}
                />
            </OnboardingStep>
        )
    }

    if (step === 2) {
        return (
            <OnboardingStep
                step={2}
                totalSteps={3}
                title="What are your wellness goals?"
                subtitle="Select all that apply. We'll tailor your experience to match."
                onNext={() => setStep(3)}
                nextDisabled={data.goals.length === 0}
            >
                <GoalSelector
                    selected={data.goals}
                    onChange={(goals) => setData((d) => ({ ...d, goals }))}
                />
            </OnboardingStep>
        )
    }

    return (
        <OnboardingStep
            step={3}
            totalSteps={3}
            title="Stay on track"
            subtitle="SentiMind can gently remind you to check in each day."
            onNext={handleFinish}
            nextLabel={saving ? 'Setting up...' : 'Start Chatting'}
            nextDisabled={saving}
        >
            <div className="bg-slate-50 rounded-2xl p-5 space-y-1 border border-slate-100">
                <ToggleSetting
                    label="Daily Check-in Reminders"
                    description="Get a gentle nudge to reflect each day"
                    checked={data.notificationsEnabled}
                    onChange={(v) => setData((d) => ({ ...d, notificationsEnabled: v }))}
                />
            </div>

            <div className="text-center space-y-2 pt-2">
                <p className="text-xs text-slate-400">
                    By continuing you agree to our{' '}
                    <a href="#" className="underline text-purple-500">Terms of Service</a>{' '}
                    and{' '}
                    <a href="#" className="underline text-purple-500">Privacy Policy</a>.
                </p>
                <p className="text-xs text-slate-400">
                    🔒 Your data is encrypted and never shared.
                </p>
            </div>
        </OnboardingStep>
    )
}
