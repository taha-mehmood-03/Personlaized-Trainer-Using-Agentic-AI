import React from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Sparkles, Heart, ShieldCheck, Mic } from 'lucide-react'

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Navbar */}
      <header className="px-6 py-4 flex items-center justify-between border-b border-slate-200 bg-white/80 backdrop-blur-md sticky top-0 z-50">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-purple-500 to-teal-400 flex items-center justify-center shadow-sm">
            <span className="text-white font-bold text-lg leading-none">S</span>
          </div>
          <span className="font-bold text-slate-800 tracking-tight text-xl">SentiMind</span>
        </div>
        <div className="flex items-center gap-4">
          <Link href="/login" className="text-sm font-semibold text-slate-600 hover:text-slate-900 transition-colors">
            Log in
          </Link>
          <Button asChild variant="primary" size="sm">
            <Link href="/signup">Get Started</Link>
          </Button>
        </div>
      </header>

      {/* Hero Section */}
      <main className="flex-1 flex flex-col items-center justify-center text-center px-4 py-20 pb-10">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-purple-50 border border-purple-100 text-purple-600 text-xs font-bold mb-8 uppercase tracking-widest shadow-sm">
          <Sparkles className="w-3 h-3" />
          The Future of Mental Wellness
        </div>
        
        <h1 className="text-5xl md:text-7xl font-black text-slate-900 tracking-tighter max-w-4xl leading-[1.1] mb-6">
          Your personal AI companion for <span className="text-transparent bg-clip-text bg-gradient-to-r from-purple-600 to-teal-500">emotional support.</span>
        </h1>
        
        <p className="text-lg md:text-xl text-slate-500 max-w-2xl mb-10 leading-relaxed font-medium">
          Whether you&apos;re dealing with stress, anxiety, or simply need someone to talk to, SentiMind is here 24/7 to listen, understand, and guide you through evidence-based healing exercises.
        </p>

        <div className="flex flex-col sm:flex-row gap-4 items-center justify-center">
          <Button asChild variant="primary" size="lg" className="w-full sm:w-auto">
            <Link href="/signup">Start Your Journey For Free</Link>
          </Button>
          <Button asChild variant="outline" size="lg" className="w-full sm:w-auto bg-white">
            <Link href="/chat">Try Demo Anonymous Mode</Link>
          </Button>
        </div>

        {/* Features grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-5xl mx-auto mt-24 text-left">
          <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
            <div className="w-12 h-12 bg-purple-100 text-purple-600 rounded-xl flex items-center justify-center mb-4">
              <Mic className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-bold text-slate-900 mb-2">Voice Emotion Recognition</h3>
            <p className="text-slate-500 text-sm">We don&apos;t just listen to your words; we analyze the tone of your voice to provide deeply empathetic responses.</p>
          </div>
          <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
            <div className="w-12 h-12 bg-teal-100 text-teal-600 rounded-xl flex items-center justify-center mb-4">
              <ShieldCheck className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-bold text-slate-900 mb-2">Private & Secure</h3>
            <p className="text-slate-500 text-sm">Your emotional data and conversations are strictly confidential and protected by enterprise-grade encryption.</p>
          </div>
          <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
            <div className="w-12 h-12 bg-rose-100 text-rose-600 rounded-xl flex items-center justify-center mb-4">
              <Heart className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-bold text-slate-900 mb-2">Evidence-Based Healing</h3>
            <p className="text-slate-500 text-sm">Get matched with specific CBT and mindfulness exercises automatically based on the emotions you express.</p>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200 bg-white py-8 text-center mt-auto">
        <p className="text-slate-400 text-sm font-medium">
          © {new Date().getFullYear()} SentiMind AI. Not a replacement for professional clinical help.
        </p>
      </footer>
    </div>
  )
}
