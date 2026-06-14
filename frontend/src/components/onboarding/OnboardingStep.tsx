'use client'

import React from 'react'
import Link from 'next/link'
import { Activity, ArrowLeft, ArrowRight, CheckCircle2, ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface SupportingItem {
    label: string
    value: string
}

interface OnboardingStepProps {
    step: number
    totalSteps: number
    title: string
    subtitle: string
    onNext: () => void
    onBack?: () => void
    nextLabel?: string
    nextDisabled?: boolean
    children: React.ReactNode
    supportingItems?: SupportingItem[]
}

const BASELINE_ITEMS = [
    'Initial mood baseline',
    'Goal-aware support path',
    'Dashboard personalization',
]

export const OnboardingStep = ({
    step,
    totalSteps,
    title,
    subtitle,
    onNext,
    onBack,
    nextLabel = 'Continue',
    nextDisabled = false,
    children,
    supportingItems = [],
}: OnboardingStepProps) => {
    const progress = Math.round((step / totalSteps) * 100)

    return (
        <main className="min-h-screen bg-[linear-gradient(135deg,#f8fafc_0%,#ecfeff_45%,#f0fdf4_100%)] px-4 py-6 sm:px-6">
            <div className="mx-auto grid min-h-[calc(100vh-3rem)] max-w-6xl gap-6 lg:grid-cols-[0.85fr_1.15fr] lg:items-stretch">
                <aside className="hidden rounded-3xl border border-slate-200 bg-slate-950 p-6 text-white shadow-xl shadow-slate-200/60 lg:flex lg:flex-col">
                    <Link href="/" className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white text-slate-950">
                            <Activity className="h-5 w-5" />
                        </div>
                        <div>
                            <p className="font-black tracking-tight">SentiMind</p>
                            <p className="text-xs font-medium text-cyan-100">Onboarding workspace</p>
                        </div>
                    </Link>

                    <div className="flex flex-1 flex-col justify-center py-10">
                        <span className="inline-flex w-fit items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs font-semibold text-cyan-100">
                            <ShieldCheck className="h-3.5 w-3.5" />
                            Private setup
                        </span>
                        <h1 className="mt-6 text-4xl font-black leading-tight tracking-tight">
                            Tune SentiMind before your first real conversation.
                        </h1>
                        <p className="mt-4 text-sm leading-6 text-slate-300">
                            These choices help the agent start with better context, while the long-term dashboard improves as sessions continue.
                        </p>

                        <div className="mt-8 space-y-3">
                            {BASELINE_ITEMS.map((item) => (
                                <div key={item} className="flex items-center gap-3 rounded-2xl bg-white/10 px-4 py-3">
                                    <CheckCircle2 className="h-4 w-4 text-emerald-300" />
                                    <span className="text-sm font-semibold">{item}</span>
                                </div>
                            ))}
                        </div>
                    </div>

                    <div className="rounded-2xl border border-white/10 bg-white/10 p-4">
                        <div className="mb-3 flex items-center justify-between text-xs font-semibold text-slate-300">
                            <span>Setup progress</span>
                            <span>{progress}%</span>
                        </div>
                        <div className="h-2 overflow-hidden rounded-full bg-white/10">
                            <div className="h-full rounded-full bg-cyan-300 transition-all duration-700" style={{ width: `${progress}%` }} />
                        </div>
                    </div>
                </aside>

                <section className="flex min-h-full items-center justify-center">
                    <div className="w-full max-w-2xl">
                        <div className="mb-5 flex items-center justify-between lg:hidden">
                            <Link href="/" className="flex items-center gap-3">
                                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-950 text-white">
                                    <Activity className="h-5 w-5" />
                                </div>
                                <div>
                                    <p className="font-black tracking-tight text-slate-900">SentiMind</p>
                                    <p className="text-xs text-slate-500">Onboarding</p>
                                </div>
                            </Link>
                            <span className="rounded-full bg-white px-3 py-1 text-xs font-bold text-slate-600 shadow-sm">
                                {progress}%
                            </span>
                        </div>

                        <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-xl shadow-slate-200/70 sm:p-7">
                            <div className="space-y-2">
                                <div className="flex items-center justify-between">
                                    <p className="text-xs font-black uppercase tracking-[0.12em] text-cyan-700">
                                        Step {step} of {totalSteps}
                                    </p>
                                    <p className="text-xs font-bold text-slate-400">{progress}% complete</p>
                                </div>
                                <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                                    <div className="h-full rounded-full bg-slate-950 transition-all duration-700" style={{ width: `${progress}%` }} />
                                </div>
                            </div>

                            <div className="mt-7">
                                <h2 className="text-2xl font-black leading-tight tracking-tight text-slate-950 sm:text-3xl">
                                    {title}
                                </h2>
                                <p className="mt-2 text-sm leading-6 text-slate-600">{subtitle}</p>
                            </div>

                            {supportingItems.length > 0 && (
                                <div className="mt-5 grid grid-cols-1 gap-2 sm:grid-cols-3">
                                    {supportingItems.map((item) => (
                                        <div key={item.label} className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                                            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-400">
                                                {item.label}
                                            </p>
                                            <p className="mt-1 text-sm font-black text-slate-900">{item.value}</p>
                                        </div>
                                    ))}
                                </div>
                            )}

                            <div className="mt-6">{children}</div>

                            <div className="mt-7 flex gap-3">
                                {onBack && (
                                    <Button
                                        type="button"
                                        variant="outline"
                                        onClick={onBack}
                                        className="h-12 rounded-xl px-4"
                                    >
                                        <ArrowLeft className="mr-2 h-4 w-4" />
                                        Back
                                    </Button>
                                )}
                                <Button
                                    type="button"
                                    onClick={onNext}
                                    disabled={nextDisabled}
                                    className="h-12 flex-1 rounded-xl bg-slate-950 text-white hover:bg-slate-800"
                                >
                                    {nextLabel}
                                    <ArrowRight className="ml-2 h-4 w-4" />
                                </Button>
                            </div>
                        </div>
                    </div>
                </section>
            </div>
        </main>
    )
}
