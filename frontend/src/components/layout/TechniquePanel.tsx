'use client'

import React, { useState } from 'react'
import { Technique } from '@/types'
import { Star, Check, ChevronRight, ChevronLeft, Flag, Sparkles } from 'lucide-react'

interface TechniquePanelProps {
  technique?: Technique | null
  alternativeTechniques?: Technique[]
  userId: string
}

// ─── Motivational quotes ──────────────────────────────────────────────────────
const QUOTES = [
  { text: 'The greatest glory in living lies not in never falling, but in rising every time we fall.', author: 'Nelson Mandela' },
  { text: 'You don\'t have to control your thoughts. You just have to stop letting them control you.', author: 'Dan Millman' },
  { text: 'Mental health is not a destination, but a process.', author: 'Noam Shpancer' },
  { text: 'You are not your illness. You have an individual story to tell.', author: 'Julian Seifter' },
  { text: 'There is hope, even when your brain tells you there isn\'t.', author: 'John Green' },
]

// ─── Category maps ─────────────────────────────────────────────────────────────
const CATEGORY_ICON: Record<string, string> = {
  breathing: '🌬️', meditation: '🧘', mindfulness: '🌿',
  cbt: '🧠', dbt: '⚖️', journaling: '📝',
  grounding: '🌍', 'behavioral activation': '⚡', general: '✨',
  visualization: '🌅',
}
const CATEGORY_COLOR: Record<string, string> = {
  breathing: 'from-cyan-400 to-blue-500',
  meditation: 'from-purple-400 to-indigo-500',
  mindfulness: 'from-green-400 to-teal-500',
  grounding: 'from-orange-400 to-red-500',
  cbt: 'from-indigo-400 to-purple-500',
  journaling: 'from-blue-400 to-cyan-500',
  dbt: 'from-blue-500 to-indigo-600',
  'behavioral activation': 'from-green-500 to-emerald-600',
  visualization: 'from-yellow-400 to-orange-400',
  general: 'from-purple-400 to-teal-500',
}

// ─── Interactive step wizard ────────────────────────────────────────────────
function StepWizard({ steps, onComplete }: { steps: string[]; onComplete: () => void }) {
  const [step, setStep] = useState(0)
  const [done, setDone] = useState(false)

  const handleNext = () => {
    if (step < steps.length - 1) {
      setStep(s => s + 1)
    } else {
      setDone(true)
      onComplete()
    }
  }

  return (
    <div className="mt-3 space-y-3">
      {/* Progress */}
      <div className="flex items-center justify-between text-[11px] text-slate-400">
        <span>Step {step + 1} of {steps.length}</span>
        <div className="h-1 flex-1 mx-3 bg-slate-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-teal-400 to-purple-500 rounded-full transition-all duration-500"
            style={{ width: `${((step + 1) / steps.length) * 100}%` }}
          />
        </div>
        <span className="text-teal-600 font-semibold">Interactive</span>
      </div>

      {/* Step card */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 relative overflow-hidden min-h-[72px] flex items-center gap-3 shadow-sm">
        <div className="absolute right-2 bottom-0 text-[64px] font-black text-slate-50 select-none pointer-events-none leading-none">
          {step + 1}
        </div>
        <div className="w-7 h-7 rounded-full bg-gradient-to-br from-teal-500 to-purple-500 text-white flex items-center justify-center text-xs font-bold shrink-0 z-10">
          {step + 1}
        </div>
        <p className="text-xs text-slate-800 leading-relaxed z-10">{steps[step]}</p>
      </div>

      {/* Nav buttons */}
      <div className="flex justify-between">
        <button
          onClick={() => setStep(s => Math.max(0, s - 1))}
          disabled={step === 0}
          className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-slate-600 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
        >
          <ChevronLeft className="w-3.5 h-3.5" /> Previous
        </button>
        <button
          onClick={handleNext}
          disabled={done}
          className={`flex items-center gap-1 px-3 py-1.5 text-xs font-bold rounded-lg transition-all ${
            done
              ? 'bg-green-100 text-green-700 cursor-default'
              : step < steps.length - 1
                ? 'bg-slate-900 text-white hover:bg-slate-700'
                : 'bg-gradient-to-r from-teal-500 to-emerald-500 text-white hover:shadow-md'
          }`}
        >
          {done
            ? <><Check className="w-3.5 h-3.5" /> Completed!</>
            : step < steps.length - 1
              ? <>Next Step <ChevronRight className="w-3.5 h-3.5" /></>
              : <><Flag className="w-3.5 h-3.5" /> I&apos;m Done</>
          }
        </button>
      </div>
    </div>
  )
}

// ─── Star rating ──────────────────────────────────────────────────────────────
function StarRating({
  userId, techniqueId, wizardCompleted,
}: { userId: string; techniqueId: string; wizardCompleted: boolean }) {
  const [rating, setRating] = useState(0)
  const [hover, setHover] = useState(0)
  const [saved, setSaved] = useState(false)

  const isBlurred = !wizardCompleted // blur until wizard done

  const handleClick = async (s: number) => {
    if (isBlurred) return
    setRating(s)
    try {
      await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api'}/technique/rate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, technique_id: techniqueId, rating: s, completed: wizardCompleted }),
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } catch { }
  }

  return (
    <div className={`pt-3 border-t border-dashed border-slate-200 transition-all duration-500 ${isBlurred ? 'opacity-30 blur-[1px] pointer-events-none' : ''}`}>
      <p className="text-[10px] uppercase font-bold text-slate-400 mb-2 tracking-widest">Rate Impact</p>
      <div className="flex items-center gap-1.5">
        {[1, 2, 3, 4, 5].map(s => (
          <button key={s} onClick={() => handleClick(s)} onMouseEnter={() => setHover(s)} onMouseLeave={() => setHover(0)}>
            <Star className={`w-5 h-5 transition-all ${s <= (hover || rating) ? 'fill-amber-400 text-amber-400' : 'text-slate-200'}`} />
          </button>
        ))}
        {saved && <span className="text-xs text-green-600 ml-1 font-medium">Saved!</span>}
      </div>
    </div>
  )
}

// ─── Progress bars ─────────────────────────────────────────────────────────────
function ProgressBar({ label, value, purple }: { label: string; value: number; purple?: boolean }) {
  return (
    <div>
      <div className="flex justify-between items-center mb-1">
        <span className="text-xs text-slate-600">{label}</span>
        <span className={`text-xs font-bold ${purple ? 'text-purple-600' : 'text-teal-600'}`}>{Math.round(value)}%</span>
      </div>
      <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${purple ? 'bg-gradient-to-r from-purple-400 to-purple-600' : 'bg-gradient-to-r from-green-400 to-teal-500'}`}
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  )
}

// ─── Main panel ────────────────────────────────────────────────────────────────
export function TechniquePanel({ technique, alternativeTechniques = [], userId }: TechniquePanelProps) {
  const allTechniques = technique ? [technique, ...alternativeTechniques] : []
  const [selectedIdx, setSelectedIdx] = useState(0)
  const [wizardCompleted, setWizardCompleted] = useState(false)

  // When a new technique arrives from the stream, reset to first
  React.useEffect(() => {
    setSelectedIdx(0)
    setWizardCompleted(false)
  }, [technique?.id])

  const active = allTechniques[selectedIdx] ?? null
  const catKey = active?.category?.toLowerCase() ?? ''
  const gradient = CATEGORY_COLOR[catKey] ?? 'from-purple-400 to-teal-500'
  const icon = CATEGORY_ICON[catKey] ?? '✨'
  const quote = QUOTES[Math.floor(Date.now() / 86400000) % QUOTES.length]

  return (
    <div className="hidden xl:flex w-72 shrink-0 bg-white border-l border-slate-200 flex-col overflow-y-auto shadow-sm">
      <div className="p-4 space-y-4">
        {/* Header */}
        <div className="flex items-center gap-2">
          <span className="text-teal-500 text-base">✦</span>
          <h2 className="text-sm font-bold text-slate-800">Healing Exercise</h2>
        </div>

        {active ? (
          <>
            {/* Hero gradient card */}
            <div className={`rounded-xl bg-gradient-to-br ${gradient} text-white p-4 text-center relative overflow-hidden`}>
              <div className="absolute -right-4 -top-4 w-16 h-16 bg-white/10 rounded-full" />
              <div className="absolute -left-3 -bottom-4 w-12 h-12 bg-white/10 rounded-full" />
              <div className="w-12 h-12 mx-auto bg-white/20 rounded-xl flex items-center justify-center text-2xl mb-2.5 backdrop-blur-sm border border-white/20">
                {icon}
              </div>
              <h3 className="font-bold text-sm leading-tight">{active.name}</h3>
              <p className="text-[11px] text-white/80 mt-1">{active.brief}</p>
              <div className="flex justify-center gap-1.5 mt-2.5 flex-wrap">
                <span className="px-2 py-0.5 bg-white/20 rounded-full text-[10px] font-semibold">⏱ {active.duration_minutes} min</span>
                <span className="px-2 py-0.5 bg-white/20 rounded-full text-[10px] font-semibold capitalize">{active.difficulty ?? 'Easy'}</span>
                <span className="px-2 py-0.5 bg-white/20 rounded-full text-[10px] font-semibold capitalize">{active.category}</span>
              </div>
            </div>

            {/* Description */}
            {active.description && (
              <p className="text-xs text-slate-500 leading-relaxed">{active.description}</p>
            )}

            {/* Interactive step wizard */}
            {active.steps?.length > 0 && (
              <StepWizard
                key={`${active.id}-wizard`}
                steps={active.steps}
                onComplete={() => setWizardCompleted(true)}
              />
            )}

            {/* Star rating — locked until wizard done */}
            <StarRating userId={userId} techniqueId={active.id} wizardCompleted={wizardCompleted} />

            {/* Alternative exercises */}
            {allTechniques.length > 1 && (
              <>
                <div className="border-t border-slate-100" />
                <div>
                  <p className="text-[10px] uppercase font-bold text-slate-400 mb-2 tracking-widest">Alternative Exercises</p>
                  <div className="flex flex-col gap-1.5">
                    {allTechniques.map((t, i) => (
                      <button
                        key={t.id}
                        onClick={() => { setSelectedIdx(i); setWizardCompleted(false) }}
                        className={`text-left px-3 py-2 rounded-lg text-xs font-medium border transition-all ${
                          i === selectedIdx
                            ? 'bg-purple-50 border-purple-300 text-purple-700'
                            : 'bg-slate-50 border-slate-200 text-slate-600 hover:border-purple-200 hover:bg-purple-50/50'
                        }`}
                      >
                        {i === selectedIdx && <span className="font-bold mr-1">✓</span>}
                        {t.name}
                        <span className="ml-1 opacity-60 text-[10px] capitalize">({t.category})</span>
                      </button>
                    ))}
                  </div>
                </div>
              </>
            )}

            {/* Divider */}
            <div className="border-t border-slate-100" />

            {/* Progress */}
            <div>
              <p className="text-[10px] uppercase font-bold text-slate-400 mb-3 tracking-widest">Your Progress</p>
              <div className="space-y-3">
                <ProgressBar label="Emotional Balance" value={65} purple />
                <ProgressBar label="Resilience Score" value={42} />
              </div>
            </div>
          </>
        ) : (
          <div className="flex flex-col items-center justify-center text-slate-400 text-sm py-10 px-2 text-center gap-2">
            <Sparkles className="w-8 h-8 opacity-25" />
            Tools and techniques will appear here automatically based on your conversation.
          </div>
        )}

        {/* Motivational quote — always visible */}
        <div className="bg-slate-50 rounded-xl p-3 border border-slate-100">
          <p className="text-xs text-slate-600 italic leading-relaxed">"{quote.text}"</p>
          <p className="text-[10px] text-purple-500 font-semibold mt-1.5">— {quote.author}</p>
        </div>
      </div>
    </div>
  )
}
