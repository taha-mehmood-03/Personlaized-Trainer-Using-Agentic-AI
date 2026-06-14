import React from 'react'
import Link from 'next/link'
import {
    Activity,
    BarChart3,
    Brain,
    CheckCircle2,
    LockKeyhole,
    MessageSquareText,
    ShieldCheck,
    Sparkles,
} from 'lucide-react'

const TRUST_ITEMS = [
    {
        icon: MessageSquareText,
        title: 'Context-aware conversations',
        body: 'Your recent session context helps the agent understand follow-ups instead of restarting every turn.',
    },
    {
        icon: BarChart3,
        title: 'Long-term analytics',
        body: 'Mood, symptoms, context signals, and technique outcomes are tracked for your dashboard.',
    },
    {
        icon: ShieldCheck,
        title: 'Crisis resources',
        body: 'Urgent language keeps support resources visible instead of hiding them behind normal coaching flows.',
    },
]

const SYSTEM_SIGNALS = [
    { label: 'Context continuity', value: 'Active', tone: 'text-emerald-700 bg-emerald-50 border-emerald-100' },
    { label: 'Detailed signals', value: 'Mood + context', tone: 'text-amber-700 bg-amber-50 border-amber-100' },
    { label: 'Analytics refresh', value: 'Background', tone: 'text-cyan-700 bg-cyan-50 border-cyan-100' },
]

export default function AuthLayout({ children }: { children: React.ReactNode }) {
    return (
        <main className="min-h-screen bg-[linear-gradient(135deg,#f8fafc_0%,#ecfeff_48%,#f0fdf4_100%)]">
            <div className="grid min-h-screen grid-cols-1 lg:grid-cols-[1.05fr_0.95fr]">
                <section className="relative hidden overflow-hidden border-r border-slate-200 bg-white p-8 lg:flex lg:flex-col">
                    <div className="pointer-events-none absolute inset-y-0 right-0 w-40 bg-cyan-50/70" />
                    <div className="pointer-events-none absolute bottom-0 left-0 h-32 w-full bg-gradient-to-t from-emerald-50/70 to-transparent" />

                    <div className="flex items-center justify-between">
                        <Link href="/" className="flex items-center gap-3">
                            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-950 text-white shadow-sm">
                                <Activity className="h-5 w-5" />
                            </div>
                            <div>
                                <p className="font-black tracking-tight text-slate-900">SentiMind</p>
                                <p className="text-xs font-medium text-slate-500">Personalized trainer</p>
                            </div>
                        </Link>
                        <Link
                            href="/chat"
                            className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 shadow-sm transition-colors hover:bg-slate-50"
                        >
                            Open chat
                        </Link>
                    </div>

                    <div className="relative flex flex-1 flex-col justify-center py-12">
                        <div className="max-w-2xl">
                            <span className="inline-flex items-center gap-2 rounded-full border border-emerald-100 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
                                <Sparkles className="h-3.5 w-3.5" />
                                Secure wellness workspace
                            </span>
                            <h1 className="mt-6 text-5xl font-black leading-tight tracking-tight text-slate-950">
                                A calmer support system that remembers the session.
                            </h1>
                            <p className="mt-5 text-base leading-7 text-slate-600">
                                SentiMind keeps the response path fast while moving memory, analytics, and personalization into the background.
                            </p>
                        </div>

                        <div className="mt-8 grid max-w-2xl grid-cols-3 gap-2">
                            {SYSTEM_SIGNALS.map((signal) => (
                                <div key={signal.label} className={`rounded-xl border p-3 ${signal.tone}`}>
                                    <p className="text-[11px] font-semibold uppercase tracking-[0.08em] opacity-80">
                                        {signal.label}
                                    </p>
                                    <p className="mt-1 text-sm font-black">{signal.value}</p>
                                </div>
                            ))}
                        </div>

                        <div className="mt-8 grid max-w-2xl gap-3">
                            {TRUST_ITEMS.map(({ icon: Icon, title, body }) => (
                                <article key={title} className="rounded-2xl border border-slate-200 bg-white/90 p-4 shadow-sm">
                                    <div className="flex gap-3">
                                        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-950 text-white shadow-sm">
                                            <Icon className="h-4 w-4" />
                                        </div>
                                        <div>
                                            <h2 className="text-sm font-black text-slate-900">{title}</h2>
                                            <p className="mt-1 text-sm leading-6 text-slate-600">{body}</p>
                                        </div>
                                    </div>
                                </article>
                            ))}
                        </div>
                    </div>

                    <div className="relative grid grid-cols-[1fr_0.78fr] gap-3">
                        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                            <div className="flex items-center gap-2 text-sm font-bold text-slate-800">
                                <LockKeyhole className="h-4 w-4 text-slate-500" />
                                Private by design
                            </div>
                            <p className="mt-2 text-xs leading-5 text-slate-500">
                                Mental wellness data should feel protected, understandable, and useful. Your dashboard only becomes richer as you choose to engage.
                            </p>
                        </div>

                        <div className="rounded-2xl border border-cyan-100 bg-cyan-50 p-4">
                            <div className="flex items-center gap-2 text-sm font-bold text-cyan-900">
                                <Brain className="h-4 w-4 text-cyan-700" />
                                Low-latency path
                            </div>
                            <div className="mt-3 space-y-2 text-xs font-semibold text-cyan-800">
                                {['Gate', 'Plan', 'Respond'].map((step) => (
                                    <div key={step} className="flex items-center gap-2">
                                        <CheckCircle2 className="h-3.5 w-3.5" />
                                        <span>{step}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                </section>

                <section className="flex min-h-screen items-center justify-center px-4 py-8 sm:px-6">
                    <div className="w-full max-w-md">
                        <div className="mb-6 flex items-center justify-between lg:hidden">
                            <Link href="/" className="flex items-center gap-3">
                                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-950 text-white">
                                    <Activity className="h-5 w-5" />
                                </div>
                                <div>
                                    <p className="font-black tracking-tight text-slate-900">SentiMind</p>
                                    <p className="text-xs text-slate-500">Wellness workspace</p>
                                </div>
                            </Link>
                            <Link href="/chat" className="text-sm font-semibold text-slate-600">
                                Chat
                            </Link>
                        </div>

                        <div className="rounded-2xl border border-slate-200 bg-white/95 p-5 shadow-xl shadow-slate-200/60 sm:p-6">
                            {children}
                        </div>

                        <p className="mt-5 text-center text-xs leading-5 text-slate-400">
                            By continuing, you agree to use SentiMind as supportive wellness software, not emergency medical care.
                        </p>
                    </div>
                </section>
            </div>
        </main>
    )
}
