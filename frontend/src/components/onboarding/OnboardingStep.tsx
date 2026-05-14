'use client'

import React from 'react'
import { Button } from '@/components/ui/button'
import { ArrowRight } from 'lucide-react'

interface OnboardingStepProps {
    step: number
    totalSteps: number
    title: string
    subtitle: string
    onNext: () => void
    nextLabel?: string
    nextDisabled?: boolean
    children: React.ReactNode
}

/** Reusable step wrapper with logo, progress bar, and next button for onboarding flow. */
export const OnboardingStep = ({
    step,
    totalSteps,
    title,
    subtitle,
    onNext,
    nextLabel = 'Continue',
    nextDisabled = false,
    children,
}: OnboardingStepProps) => {
    const progress = (step / totalSteps) * 100

    return (
        <div className="min-h-screen bg-gradient-to-br from-purple-50 via-white to-teal-50 flex items-center justify-center p-4">
            <div className="w-full max-w-md">
                {/* Logo */}
                <div className="flex items-center gap-2 mb-8">
                    <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-purple-500 to-teal-400 flex items-center justify-center shadow-md">
                        <span className="text-white font-black text-xl leading-none">S</span>
                    </div>
                    <span className="font-bold text-slate-800 tracking-tight text-lg">SentiMind</span>
                </div>

                {/* Card */}
                <div className="bg-white rounded-3xl shadow-xl border border-slate-100 p-7 space-y-6 animate-scale-in">
                    {/* Progress bar */}
                    <div className="space-y-1.5">
                        <div className="flex items-center justify-between">
                            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                                Step {step} of {totalSteps}
                            </p>
                            <p className="text-xs text-slate-400">{Math.round(progress)}%</p>
                        </div>
                        <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
                            <div
                                className="h-full rounded-full bg-gradient-to-r from-purple-500 to-teal-400 transition-all duration-700"
                                style={{ width: `${progress}%` }}
                            />
                        </div>
                    </div>

                    {/* Title */}
                    <div>
                        <h1 className="text-2xl font-black text-slate-900 leading-tight">{title}</h1>
                        <p className="text-sm text-slate-500 mt-1.5">{subtitle}</p>
                    </div>

                    {/* Content */}
                    {children}

                    {/* CTA */}
                    <Button
                        variant="primary"
                        onClick={onNext}
                        disabled={nextDisabled}
                        className="w-full h-13 text-base"
                    >
                        {nextLabel}
                        <ArrowRight className="w-4 h-4 ml-2" />
                    </Button>
                </div>
            </div>
        </div>
    )
}
