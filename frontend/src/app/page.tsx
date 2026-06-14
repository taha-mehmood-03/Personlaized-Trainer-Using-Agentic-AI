import React from 'react'
import Link from 'next/link'
import {
    Activity,
    ArrowRight,
    BarChart3,
    Brain,
    Clock3,
    HeartPulse,
    MessageSquareText,
    Phone,
    ShieldCheck,
    Sparkles,
} from 'lucide-react'
import { Button } from '@/components/ui/button'

const CAPABILITIES = [
    {
        icon: MessageSquareText,
        title: 'Context-aware chat',
        body: 'Short replies, follow-ups, technique feedback, and memory questions stay tied to the active session.',
    },
    {
        icon: BarChart3,
        title: 'Long-term analytics',
        body: 'Mood snapshots, symptoms, context signals, technique outcomes, and session trends become visible over time.',
    },
    {
        icon: ShieldCheck,
        title: 'Crisis resources',
        body: 'Urgent language keeps support resources visible instead of hiding them behind normal coaching flows.',
    },
    {
        icon: Brain,
        title: 'Personalized pacing',
        body: 'The agent gathers enough context before suggesting techniques, then learns from what helped.',
    },
]

const PIPELINE_STEPS = [
    { label: 'Gate', detail: 'Route safely', value: '< 1s' },
    { label: 'Understand', detail: 'Use context', value: 'multi-turn' },
    { label: 'Respond', detail: 'One next step', value: 'warm' },
    { label: 'Persist', detail: 'Update analytics', value: 'background' },
]

const CHAT_LINES = [
    { speaker: 'User', text: 'My final presentation is coming up and I feel tense.' },
    { speaker: 'SentiMind', text: 'That sounds like a lot of pressure. What part feels most uncertain right now?' },
    { speaker: 'User', text: 'The questions after the presentation.' },
]

const DASHBOARD_ROWS = [
    { label: 'Mood stability', value: '72%', width: 'w-[72%]', color: 'bg-emerald-500' },
    { label: 'Technique fit', value: '81%', width: 'w-[81%]', color: 'bg-cyan-500' },
    { label: 'Session continuity', value: '94%', width: 'w-[94%]', color: 'bg-slate-900' },
]

const FOOTER_LINKS = [
    { label: 'Dashboard', href: '/dashboard' },
    { label: 'Chat', href: '/chat' },
    { label: 'Crisis resources', href: '/crisis' },
    { label: 'Profile', href: '/profile' },
]

function HeroMockup() {
    return (
        <div className="mx-auto mt-10 max-w-6xl rounded-[1.75rem] border border-white/10 bg-white/10 p-3 shadow-2xl shadow-cyan-950/40 backdrop-blur-md">
            <div className="grid gap-3 lg:grid-cols-[1.05fr_0.95fr]">
                <div className="rounded-2xl bg-white p-4 text-slate-950">
                    <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                        <div>
                            <p className="text-xs font-black uppercase tracking-[0.1em] text-cyan-700">Live conversation</p>
                            <p className="mt-1 text-sm font-black">Presentation anxiety</p>
                        </div>
                        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-950 text-white">
                            <MessageSquareText className="h-5 w-5" />
                        </div>
                    </div>

                    <div className="mt-4 space-y-3">
                        {CHAT_LINES.map((line) => (
                            <div key={`${line.speaker}-${line.text}`} className="rounded-2xl border border-slate-100 bg-slate-50 p-3">
                                <p className="text-[11px] font-black uppercase tracking-[0.08em] text-slate-400">
                                    {line.speaker}
                                </p>
                                <p className="mt-1 text-sm leading-6 text-slate-700">{line.text}</p>
                            </div>
                        ))}
                    </div>

                    <div className="mt-4 grid grid-cols-2 gap-2">
                        <div className="rounded-2xl bg-cyan-50 p-3">
                            <p className="text-[11px] font-bold uppercase tracking-[0.08em] text-cyan-700">Stage</p>
                            <p className="mt-1 text-sm font-black text-cyan-950">Understanding</p>
                        </div>
                        <div className="rounded-2xl bg-emerald-50 p-3">
                            <p className="text-[11px] font-bold uppercase tracking-[0.08em] text-emerald-700">Technique</p>
                            <p className="mt-1 text-sm font-black text-emerald-950">Not yet</p>
                        </div>
                    </div>
                </div>

                <div className="grid gap-3">
                    <div className="rounded-2xl bg-white p-4 text-slate-950">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-xs font-black uppercase tracking-[0.1em] text-emerald-700">Dashboard signals</p>
                                <p className="mt-1 text-sm font-black">30-day wellness view</p>
                            </div>
                            <HeartPulse className="h-5 w-5 text-rose-500" />
                        </div>
                        <div className="mt-4 space-y-4">
                            {DASHBOARD_ROWS.map((row) => (
                                <div key={row.label}>
                                    <div className="mb-1 flex items-center justify-between text-xs font-bold text-slate-600">
                                        <span>{row.label}</span>
                                        <span>{row.value}</span>
                                    </div>
                                    <div className="h-2.5 overflow-hidden rounded-full bg-slate-100">
                                        <div className={`h-full rounded-full ${row.color} ${row.width}`} />
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-2">
                        {PIPELINE_STEPS.map((item) => (
                            <div key={item.label} className="rounded-2xl bg-slate-950 p-4 text-white">
                                <p className="text-[11px] font-black uppercase tracking-[0.1em] text-cyan-200">{item.label}</p>
                                <p className="mt-2 text-sm font-black">{item.detail}</p>
                                <p className="mt-1 text-xs font-semibold text-slate-300">{item.value}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    )
}

export default function LandingPage() {
    return (
        <main className="min-h-screen bg-slate-50 text-slate-900">
            <header className="sticky top-0 z-50 border-b border-slate-200 bg-white/90 px-4 py-3 backdrop-blur-md sm:px-6">
                <div className="mx-auto flex max-w-7xl items-center justify-between">
                    <Link href="/" className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-950 text-white">
                            <Activity className="h-5 w-5" />
                        </div>
                        <div>
                            <p className="text-base font-black tracking-tight text-slate-950">SentiMind</p>
                            <p className="text-xs font-medium text-slate-500">Personalized trainer</p>
                        </div>
                    </Link>

                    <nav className="hidden items-center gap-7 text-sm font-semibold text-slate-600 md:flex">
                        <a href="#system" className="transition-colors hover:text-slate-950">System</a>
                        <a href="#analytics" className="transition-colors hover:text-slate-950">Analytics</a>
                        <a href="#resources" className="transition-colors hover:text-slate-950">Resources</a>
                    </nav>

                    <div className="flex items-center gap-2">
                        <Button asChild variant="ghost" size="sm">
                            <Link href="/login">Log in</Link>
                        </Button>
                        <Button asChild size="sm" className="bg-slate-950 text-white hover:bg-slate-800">
                            <Link href="/signup">Get started</Link>
                        </Button>
                    </div>
                </div>
            </header>

            <section className="relative overflow-hidden bg-slate-950 px-4 pb-10 pt-16 text-white sm:px-6 sm:pt-20">
                <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(255,255,255,0.05)_1px,transparent_1px),linear-gradient(0deg,rgba(255,255,255,0.05)_1px,transparent_1px)] bg-[size:72px_72px]" />
                <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-cyan-950/50 to-transparent" />

                <div className="relative mx-auto max-w-7xl">
                    <div className="mx-auto max-w-4xl text-center">
                        <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs font-semibold text-cyan-100 backdrop-blur-md">
                            <Sparkles className="h-3.5 w-3.5" />
                            Low-latency mental wellness agent
                        </span>
                        <h1 className="mt-7 text-5xl font-black leading-[1.02] tracking-tight sm:text-6xl lg:text-7xl">
                            SentiMind
                        </h1>
                        <p className="mx-auto mt-5 max-w-3xl text-base font-medium leading-7 text-slate-200 sm:text-lg">
                            A context-aware therapeutic companion that listens first, remembers the session, tracks detailed mood signals, and learns which support actually helps each user.
                        </p>
                        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
                            <Button asChild size="lg" className="h-12 w-full rounded-xl bg-white px-7 text-slate-950 shadow-xl shadow-cyan-950/30 hover:bg-cyan-50 sm:w-auto">
                                <Link href="/signup">
                                    Create account
                                    <ArrowRight className="ml-2 h-4 w-4" />
                                </Link>
                            </Button>
                            <Button asChild variant="outline" size="lg" className="h-12 w-full rounded-xl border-white/20 bg-white/10 px-7 text-white backdrop-blur-md hover:bg-white/15 sm:w-auto">
                                <Link href="/chat">Open chat</Link>
                            </Button>
                        </div>
                    </div>

                    <HeroMockup />
                </div>
            </section>

            <section id="system" className="border-b border-slate-200 bg-white px-4 py-16 sm:px-6">
                <div className="mx-auto max-w-7xl">
                    <div className="grid gap-8 lg:grid-cols-[0.9fr_1.1fr] lg:items-end">
                        <div>
                            <p className="text-xs font-black uppercase tracking-[0.12em] text-cyan-700">System</p>
                            <h2 className="mt-3 text-3xl font-black tracking-tight text-slate-950 sm:text-4xl">
                                Built for multi-turn support, not one-turn advice.
                            </h2>
                        </div>
                        <p className="text-base leading-7 text-slate-600">
                            The experience is tuned around continuity, therapeutic pacing, and background personalization, so the user-facing response stays fast.
                        </p>
                    </div>

                    <div className="mt-10 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
                        {CAPABILITIES.map(({ icon: Icon, title, body }) => (
                            <article key={title} className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-slate-950 text-white">
                                    <Icon className="h-5 w-5" />
                                </div>
                                <h3 className="mt-5 text-base font-black text-slate-950">{title}</h3>
                                <p className="mt-2 text-sm leading-6 text-slate-600">{body}</p>
                            </article>
                        ))}
                    </div>
                </div>
            </section>

            <section id="analytics" className="bg-slate-50 px-4 py-16 sm:px-6">
                <div className="mx-auto grid max-w-7xl gap-8 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
                    <div>
                        <p className="text-xs font-black uppercase tracking-[0.12em] text-emerald-700">Analytics</p>
                        <h2 className="mt-3 text-3xl font-black tracking-tight text-slate-950 sm:text-4xl">
                            Long-term outcomes become part of the product.
                        </h2>
                        <p className="mt-4 text-base leading-7 text-slate-600">
                            Sessions feed mood statistics, technique preferences, outcome tracking, and profile insights without blocking the chat response.
                        </p>
                        <div className="mt-6 grid grid-cols-2 gap-3">
                            {[
                                ['Mood trend', '30 days'],
                                ['Technique fit', 'per user'],
                                ['Signal depth', 'symptoms'],
                                ['Data quality', 'visible'],
                            ].map(([label, value]) => (
                                <div key={label} className="rounded-2xl border border-slate-200 bg-white p-4">
                                    <p className="text-xs font-semibold text-slate-500">{label}</p>
                                    <p className="mt-1 text-lg font-black text-slate-950">{value}</p>
                                </div>
                            ))}
                        </div>
                    </div>

                    <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-xl shadow-slate-200/70">
                        <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                            <div>
                                <p className="text-sm font-black text-slate-950">Dashboard preview</p>
                                <p className="text-xs text-slate-500">Personalized wellness signals</p>
                            </div>
                            <Clock3 className="h-5 w-5 text-cyan-600" />
                        </div>
                        <div className="mt-5 grid grid-cols-3 gap-3">
                            {['Stable', '8 sessions', '3 techniques'].map((item) => (
                                <div key={item} className="rounded-2xl bg-slate-50 p-4 text-center">
                                    <p className="text-sm font-black text-slate-950">{item}</p>
                                    <p className="mt-1 text-[11px] font-semibold text-slate-500">current</p>
                                </div>
                            ))}
                        </div>
                        <div className="mt-5 space-y-4">
                            {DASHBOARD_ROWS.map((row) => (
                                <div key={row.label}>
                                    <div className="mb-1 flex items-center justify-between text-sm font-semibold text-slate-700">
                                        <span>{row.label}</span>
                                        <span>{row.value}</span>
                                    </div>
                                    <div className="h-3 overflow-hidden rounded-full bg-slate-100">
                                        <div className={`h-full rounded-full ${row.color} ${row.width}`} />
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </section>

            <section id="resources" className="bg-white px-4 py-14 sm:px-6">
                <div className="mx-auto flex max-w-7xl flex-col gap-5 rounded-3xl border border-rose-100 bg-rose-50 p-6 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex gap-4">
                        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-rose-600 text-white">
                            <Phone className="h-5 w-5" />
                        </div>
                        <div>
                            <h2 className="text-xl font-black text-rose-950">Crisis support stays visible.</h2>
                            <p className="mt-1 text-sm leading-6 text-rose-800">
                                If someone is in immediate danger, call local emergency services or Pakistan emergency support at 0311-7786264.
                            </p>
                        </div>
                    </div>
                    <Button asChild className="bg-rose-600 hover:bg-rose-700">
                        <Link href="/crisis">Open resources</Link>
                    </Button>
                </div>
            </section>

            <footer className="border-t border-slate-200 bg-slate-950 px-4 py-10 text-white sm:px-6">
                <div className="mx-auto flex max-w-7xl flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                        <div className="flex items-center gap-3">
                            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-white text-slate-950">
                                <Activity className="h-4 w-4" />
                            </div>
                            <span className="text-lg font-black">SentiMind</span>
                        </div>
                        <p className="mt-3 text-sm text-slate-400">Supportive wellness software, not emergency medical care.</p>
                    </div>
                    <div className="flex flex-wrap gap-4 text-sm font-semibold text-slate-300">
                        {FOOTER_LINKS.map((link) => (
                            <Link key={link.href} href={link.href} className="hover:text-white">
                                {link.label}
                            </Link>
                        ))}
                    </div>
                    <p className="text-xs text-slate-500">Copyright {new Date().getFullYear()} SentiMind AI.</p>
                </div>
            </footer>
        </main>
    )
}
