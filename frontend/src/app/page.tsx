import React from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import {
    Sparkles,
    Heart,
    ShieldCheck,
    Mic,
    BarChart3,
    MessageCircleHeart,
    Phone,
} from 'lucide-react'

const FEATURES = [
    {
        icon: <Mic className="w-6 h-6" />,
        color: 'bg-purple-100 text-purple-600',
        title: 'Emotion Detection',
        body: 'Advanced analysis that understands how you really feel beneath the words.',
    },
    {
        icon: <MessageCircleHeart className="w-6 h-6" />,
        color: 'bg-teal-100 text-teal-600',
        title: 'Personalized Support',
        body: 'Dynamic conversation that adapts to your unique mental state in real-time.',
    },
    {
        icon: <ShieldCheck className="w-6 h-6" />,
        color: 'bg-rose-100 text-rose-600',
        title: 'Crisis Safe',
        body: 'Equipped with safeguards to watch out for your immediate physical safety.',
    },
    {
        icon: <BarChart3 className="w-6 h-6" />,
        color: 'bg-amber-100 text-amber-600',
        title: 'Tracks Progress',
        body: 'Visualize your mood journey over weeks and months with intuitive charts.',
    },
]

const HOW_IT_WORKS = [
    {
        step: '01',
        title: 'Tell us how you feel',
        body: 'Start a conversation whenever you need it. No judgments, just listening.',
    },
    {
        step: '02',
        title: 'SentiMind listens',
        body: 'Our AI processes your input with empathy and clinical-grade understanding.',
    },
    {
        step: '03',
        title: 'Get personalized support',
        body: 'Receive mindfulness exercises, cognitive reframing, and mood-boosting tasks.',
    },
]

const TESTIMONIALS = [
    {
        quote:
            'SentiMind has been a lifesaver during my late-night anxiety attacks. Having someone to talk to at 3 AM makes all the difference.',
        author: 'Sarah K.',
        role: 'Software Engineer',
        avatar: 'SK',
        color: 'from-purple-500 to-teal-400',
    },
    {
        quote:
            'The progress tracking feature helped me realize my triggers were related to work stress. It\'s like having a therapist in my pocket.',
        author: 'Marcus T.',
        role: 'Product Manager',
        avatar: 'MT',
        color: 'from-teal-500 to-cyan-400',
    },
    {
        quote:
            "I was skeptical about AI, but the empathy SentiMind shows is remarkable. It doesn't give generic advice; it truly adapts to me.",
        author: 'Aisha R.',
        role: 'Graduate Student',
        avatar: 'AR',
        color: 'from-rose-500 to-orange-400',
    },
]

const FOOTER_LINKS = {
    Product: ['Chatbot', 'Journaling', 'Mood Tracker', 'Enterprise'],
    Resources: ['Help Center', 'Crisis Hotline', 'Wellness Blog', 'Research'],
    Company: ['About Us', 'Privacy Policy', 'Terms of Service', 'Ethics'],
}

export default function LandingPage() {
    return (
        <div className="min-h-screen bg-white flex flex-col">
            {/* ── NAVBAR ── */}
            <header className="px-6 py-4 flex items-center justify-between border-b border-slate-100 bg-white/90 backdrop-blur-md sticky top-0 z-50">
                <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-purple-500 to-teal-400 flex items-center justify-center shadow-sm">
                        <span className="text-white font-bold text-lg leading-none">S</span>
                    </div>
                    <span className="font-bold text-slate-800 tracking-tight text-xl">SentiMind</span>
                </div>
                <nav className="hidden md:flex items-center gap-8 text-sm font-medium text-slate-600">
                    <a href="#features" className="hover:text-purple-600 transition-colors">Features</a>
                    <a href="#how-it-works" className="hover:text-purple-600 transition-colors">How It Works</a>
                    <a href="#testimonials" className="hover:text-purple-600 transition-colors">Testimonials</a>
                </nav>
                <div className="flex items-center gap-3">
                    <Link href="/login" className="text-sm font-semibold text-slate-600 hover:text-slate-900 transition-colors">
                        Log in
                    </Link>
                    <Button asChild variant="primary" size="sm">
                        <Link href="/signup">Get Started</Link>
                    </Button>
                </div>
            </header>

            {/* ── HERO ── */}
            <section className="flex-1 flex flex-col items-center justify-center text-center px-4 pt-24 pb-20 bg-gradient-to-b from-slate-50 via-white to-white">
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-purple-50 border border-purple-100 text-purple-600 text-xs font-bold mb-8 uppercase tracking-widest shadow-sm animate-fade-in">
                    <Sparkles className="w-3 h-3" />
                    The Future of Mental Wellness
                </div>

                <h1 className="text-5xl md:text-7xl font-black text-slate-900 tracking-tighter max-w-4xl leading-[1.05] mb-6 animate-slide-up">
                    An AI-powered mental wellness companion that{' '}
                    <span className="text-transparent bg-clip-text bg-gradient-to-r from-purple-600 to-teal-500">
                        listens, understands, and supports.
                    </span>
                </h1>

                <p className="text-lg md:text-xl text-slate-500 max-w-2xl mb-10 leading-relaxed font-medium animate-slide-up">
                    Join 10,000+ users finding peace today. Available 24/7, no judgment, no appointments.
                </p>

                <div className="flex flex-col sm:flex-row gap-4 items-center justify-center animate-slide-up">
                    <Button asChild variant="primary" size="lg" className="w-full sm:w-auto shadow-xl shadow-purple-200">
                        <Link href="/signup">Start Your Journey — It&apos;s Free</Link>
                    </Button>
                    <Button asChild variant="outline" size="lg" className="w-full sm:w-auto bg-white">
                        <Link href="/chat">Try Demo (Anonymous Mode)</Link>
                    </Button>
                </div>
            </section>

            {/* ── FEATURES ── */}
            <section id="features" className="py-24 px-4 bg-slate-50">
                <div className="max-w-6xl mx-auto">
                    <div className="text-center mb-14">
                        <p className="text-xs font-bold text-purple-600 uppercase tracking-widest mb-3">Features</p>
                        <h2 className="text-3xl md:text-4xl font-black text-slate-900 tracking-tight">
                            Our AI understands the nuances of human emotion
                        </h2>
                        <p className="text-slate-500 mt-3 max-w-xl mx-auto">
                            Built to provide the best possible psychological support, in real-time.
                        </p>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
                        {FEATURES.map((f) => (
                            <div
                                key={f.title}
                                className="bg-white p-6 rounded-2xl border border-slate-100 shadow-sm hover:shadow-md transition-shadow group"
                            >
                                <div className={`w-12 h-12 ${f.color} rounded-xl flex items-center justify-center mb-4 group-hover:scale-110 transition-transform`}>
                                    {f.icon}
                                </div>
                                <h3 className="text-base font-bold text-slate-900 mb-2">{f.title}</h3>
                                <p className="text-slate-500 text-sm leading-relaxed">{f.body}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ── HOW IT WORKS ── */}
            <section id="how-it-works" className="py-24 px-4 bg-white">
                <div className="max-w-4xl mx-auto">
                    <div className="text-center mb-14">
                        <p className="text-xs font-bold text-teal-600 uppercase tracking-widest mb-3">How It Works</p>
                        <h2 className="text-3xl md:text-4xl font-black text-slate-900 tracking-tight">
                            Simple. Empathetic. Effective.
                        </h2>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                        {HOW_IT_WORKS.map((item, idx) => (
                            <div key={item.step} className="relative flex flex-col items-center text-center">
                                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-purple-500 to-teal-400 flex items-center justify-center shadow-lg mb-5">
                                    <span className="text-white font-black text-lg">{item.step}</span>
                                </div>
                                {idx < HOW_IT_WORKS.length - 1 && (
                                    <div className="hidden md:block absolute top-7 left-[calc(50%+2rem)] right-[-50%] h-px bg-gradient-to-r from-purple-200 to-teal-200" />
                                )}
                                <h3 className="text-lg font-bold text-slate-900 mb-2">{item.title}</h3>
                                <p className="text-slate-500 text-sm leading-relaxed">{item.body}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ── TESTIMONIALS ── */}
            <section id="testimonials" className="py-24 px-4 bg-gradient-to-b from-purple-50 to-white">
                <div className="max-w-5xl mx-auto">
                    <div className="text-center mb-14">
                        <p className="text-xs font-bold text-purple-600 uppercase tracking-widest mb-3">Testimonials</p>
                        <h2 className="text-3xl md:text-4xl font-black text-slate-900 tracking-tight">
                            &ldquo;Finally, an AI that actually gets me.&rdquo;
                        </h2>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        {TESTIMONIALS.map((t) => (
                            <div
                                key={t.author}
                                className="bg-white rounded-2xl border border-slate-100 shadow-sm p-6 hover:shadow-md transition-shadow"
                            >
                                <p className="text-slate-600 text-sm leading-relaxed mb-5 italic">&ldquo;{t.quote}&rdquo;</p>
                                <div className="flex items-center gap-3">
                                    <div className={`w-9 h-9 rounded-full bg-gradient-to-br ${t.color} flex items-center justify-center shrink-0`}>
                                        <span className="text-white text-xs font-bold">{t.avatar}</span>
                                    </div>
                                    <div>
                                        <p className="text-sm font-bold text-slate-900">{t.author}</p>
                                        <p className="text-xs text-slate-500">{t.role}</p>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ── CRISIS STRIP ── */}
            <div className="bg-red-600 text-white px-4 py-3.5 flex items-center justify-center gap-3 flex-wrap text-sm font-medium">
                <Phone className="w-4 h-4 shrink-0" />
                <span>
                    In crisis? Call <strong>0311-7786264</strong> immediately. You are not alone.
                </span>
                <Link
                    href="/crisis"
                    className="underline font-bold hover:text-red-100 transition-colors whitespace-nowrap"
                >
                    See more resources →
                </Link>
            </div>

            {/* ── FOOTER ── */}
            <footer className="bg-slate-900 text-slate-400 pt-16 pb-8 px-6">
                <div className="max-w-6xl mx-auto">
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-10 mb-12">
                        {/* Brand */}
                        <div className="md:col-span-1">
                            <div className="flex items-center gap-2 mb-4">
                                <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-purple-500 to-teal-400 flex items-center justify-center">
                                    <span className="text-white font-bold text-lg leading-none">S</span>
                                </div>
                                <span className="font-bold text-white tracking-tight text-xl">SentiMind</span>
                            </div>
                            <p className="text-sm leading-relaxed">
                                Empowering minds through empathetic AI. Available whenever you need a friend who understands.
                            </p>
                        </div>

                        {/* Links */}
                        {Object.entries(FOOTER_LINKS).map(([section, links]) => (
                            <div key={section}>
                                <h4 className="text-white font-bold text-sm mb-4">{section}</h4>
                                <ul className="space-y-2.5">
                                    {links.map((link) => (
                                        <li key={link}>
                                            <a href="#" className="text-sm hover:text-white transition-colors">
                                                {link}
                                            </a>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        ))}
                    </div>

                    <div className="border-t border-slate-800 pt-8 flex flex-col sm:flex-row items-center justify-between gap-4">
                        <p className="text-xs">© {new Date().getFullYear()} SentiMind AI. All rights reserved.</p>
                        <p className="text-xs">Not a replacement for professional clinical help.</p>
                    </div>
                </div>
            </footer>
        </div>
    )
}
