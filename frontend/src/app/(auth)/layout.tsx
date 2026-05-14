import React from 'react'
import Link from 'next/link'

export default function AuthLayout({ children }: { children: React.ReactNode }) {
    return (
        <div className="min-h-screen flex">
            {/* Left branding panel */}
            <div className="hidden lg:flex flex-col justify-between w-1/2 bg-gradient-to-br from-purple-700 via-purple-600 to-teal-500 p-12 text-white">
                {/* Logo */}
                <div className="flex items-center gap-2">
                    <div className="w-9 h-9 rounded-xl bg-white/20 backdrop-blur-sm flex items-center justify-center">
                        <span className="text-white font-black text-xl leading-none">S</span>
                    </div>
                    <span className="font-bold tracking-tight text-xl">SentiMind</span>
                </div>

                {/* Central copy */}
                <div className="space-y-4">
                    <h1 className="text-4xl font-black leading-tight tracking-tight">
                        Your Journey<br />Starts Here.
                    </h1>
                    <p className="text-purple-100 text-base leading-relaxed max-w-sm">
                        A safe space to understand your emotions, build resilience, and find peace — guided by empathetic AI.
                    </p>
                </div>

                {/* Testimonial */}
                <blockquote className="border-l-2 border-white/30 pl-4">
                    <p className="text-sm italic text-purple-100 leading-relaxed">
                        &ldquo;SentiMind helped me recognise patterns in my anxiety I never noticed before. Truly life-changing.&rdquo;
                    </p>
                    <footer className="text-xs text-purple-200 mt-2 font-semibold">— Sarah K., Premium Member</footer>
                </blockquote>
            </div>

            {/* Right form panel */}
            <div className="flex-1 flex flex-col justify-center items-center px-6 py-12 bg-white">
                {/* Mobile logo */}
                <div className="flex lg:hidden items-center gap-2 mb-8">
                    <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-purple-500 to-teal-400 flex items-center justify-center shadow-sm">
                        <span className="text-white font-bold text-lg leading-none">S</span>
                    </div>
                    <span className="font-bold text-slate-800 tracking-tight text-xl">SentiMind</span>
                </div>

                <div className="w-full max-w-sm">
                    <div className="mb-8 text-center">
                        <h2 className="text-2xl font-black text-slate-900">Welcome to SentiMind</h2>
                        <p className="text-sm text-slate-500 mt-1">Join our community focused on mental well-being.</p>
                    </div>

                    {children}

                    <p className="text-center text-xs text-slate-400 mt-6">
                        By continuing you agree to our{' '}
                        <a href="#" className="underline text-purple-500">Terms</a> &amp;{' '}
                        <a href="#" className="underline text-purple-500">Privacy Policy</a>.
                    </p>
                    <p className="text-center text-xs text-slate-400 mt-2">
                        <Link href="/chat" className="font-semibold text-slate-500 hover:text-purple-600 transition-colors">
                            Anonymous mode available — no account needed
                        </Link>
                    </p>
                </div>
            </div>
        </div>
    )
}
