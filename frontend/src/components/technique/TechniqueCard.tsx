'use client'

import { useState, useEffect } from 'react'
import { Sparkles, Star, Check, ChevronRight, ChevronLeft, Flag, Loader, AlertCircle } from 'lucide-react'
import { Technique } from '@/types'
import { submitTechniqueRating } from '@/actions/technique'

interface TechniqueCardProps {
  technique: Technique | null
  userId: string
  compact?: boolean
}

// ─── Category icon map ──────────────────────────────────────────────────────
const CATEGORY_ICON: Record<string, string> = {
  breathing: '🌬️', meditation: '🧘', mindfulness: '🌿',
  cbt: '🧠', dbt: '⚖️', journaling: '📝',
  grounding: '🌍', 'behavioral activation': '⚡', visualization: '🌅',
}

const CATEGORY_COLOR: Record<string, string> = {
  breathing: 'from-cyan-400 to-blue-500',
  meditation: 'from-cyan-700 to-slate-900',
  mindfulness: 'from-emerald-400 to-cyan-600',
  grounding: 'from-orange-400 to-red-500',
  cbt: 'from-slate-700 to-cyan-800',
  journaling: 'from-blue-400 to-cyan-500',
  dbt: 'from-blue-500 to-cyan-700',
  'behavioral activation': 'from-emerald-500 to-green-600',
  visualization: 'from-yellow-400 to-orange-400',
}

// ─── Step wizard sub-component ──────────────────────────────────────────────
function StepWizard({ steps, onComplete }: { steps: string[]; onComplete: () => void }) {
  const [step, setStep] = useState(0)
  const [done, setDone] = useState(false)

  const handleNext = () => {
    if (step < steps.length - 1) { setStep(s => s + 1) }
    else { setDone(true); onComplete() }
  }

  return (
    <div className="mt-4 space-y-3">
      {/* Progress */}
      <div className="flex items-center justify-between text-[11px] text-gray-400">
        <span>Step {step + 1} of {steps.length}</span>
        <div className="h-1 flex-1 mx-3 bg-gray-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-emerald-400 to-cyan-500 rounded-full transition-all duration-500"
            style={{ width: `${((step + 1) / steps.length) * 100}%` }}
          />
        </div>
        <span className="text-cyan-700 font-semibold">Interactive</span>
      </div>

      {/* Step card */}
      <div className="bg-white border border-gray-200 rounded-xl p-4 relative overflow-hidden min-h-[80px] flex items-center gap-3 shadow-sm">
        <div className="absolute right-2 bottom-0 text-[80px] font-black text-gray-50 select-none pointer-events-none leading-none">
          {step + 1}
        </div>
        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-slate-950 to-cyan-700 text-white flex items-center justify-center text-sm font-bold shrink-0 z-10">
          {step + 1}
        </div>
        <p className="text-sm text-gray-800 leading-relaxed z-10">{steps[step]}</p>
      </div>

      {/* Controls */}
      <div className="flex justify-between">
        <button
          onClick={() => setStep(s => Math.max(0, s - 1))}
          disabled={step === 0}
          className="flex items-center gap-1 px-3 py-2 text-xs font-medium text-gray-600 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
        >
          <ChevronLeft className="w-3.5 h-3.5" /> Previous
        </button>

        <button
          onClick={handleNext}
          disabled={done}
          className={`flex items-center gap-1 px-4 py-2 text-xs font-bold rounded-lg transition-all ${
            done
              ? 'bg-green-100 text-green-700 cursor-default'
              : step < steps.length - 1
                ? 'bg-gray-900 text-white hover:bg-gray-700'
                : 'bg-gradient-to-r from-cyan-700 to-emerald-600 text-white hover:shadow-md'
          }`}
        >
          {done ? <><Check className="w-3.5 h-3.5" />Completed!</>
            : step < steps.length - 1 ? <>Next Step <ChevronRight className="w-3.5 h-3.5" /></>
            : <><Flag className="w-3.5 h-3.5" />I&apos;m Done</>}
        </button>
      </div>
    </div>
  )
}

// ─── Star rating sub-component ──────────────────────────────────────────────
function StarRating({
  userId,
  technique,
  wizardCompleted,
}: { userId: string; technique: Technique; wizardCompleted: boolean }) {
  const [rating, setRating] = useState(0)
  const [hover, setHover] = useState(0)
  const [feedback, setFeedback] = useState('')
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle')

  const handleSubmit = async () => {
    if (!rating) return
    setStatus('loading')
    const res = await submitTechniqueRating({
      user_id: userId,
      technique_id: technique.id,
      rating,
      feedback: feedback || null,
      completed: wizardCompleted,
    })
    setStatus(res.status === 'success' ? 'success' : 'error')
    if (res.status === 'success') setTimeout(() => setStatus('idle'), 3000)
  }

  const isBlurred = technique.steps?.length > 0 && !wizardCompleted

  return (
    <div className={`mt-4 pt-4 border-t border-dashed border-gray-200 transition-all duration-500 ${isBlurred ? 'opacity-30 blur-[1px] pointer-events-none' : ''}`}>
      <p className="text-xs font-semibold text-gray-500 mb-2">RATE IMPACT</p>
      <div className="flex items-center gap-1 mb-3">
        {[1, 2, 3, 4, 5].map(s => (
          <button
            key={s}
            onClick={() => setRating(s)}
            onMouseEnter={() => setHover(s)}
            onMouseLeave={() => setHover(0)}
            className="transition-transform hover:scale-110 focus:outline-none"
          >
            <Star className={`w-5 h-5 ${s <= (hover || rating) ? 'fill-amber-400 text-amber-400' : 'text-gray-300'}`} />
          </button>
        ))}
      </div>

      {status === 'success' && (
        <p className="text-xs text-green-600 font-semibold flex items-center gap-1 mb-2">
          <Check className="w-3.5 h-3.5" /> Feedback saved!
        </p>
      )}
      {status === 'error' && (
        <p className="text-xs text-red-500 flex items-center gap-1 mb-2">
          <AlertCircle className="w-3.5 h-3.5" /> Failed — try again
        </p>
      )}

      <textarea
        value={feedback}
        onChange={e => setFeedback(e.target.value)}
        placeholder="Optional feedback…"
        rows={2}
        className="w-full text-xs px-3 py-2 border border-gray-200 rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-cyan-300 bg-gray-50"
      />

      <button
        onClick={handleSubmit}
        disabled={!rating || status === 'loading' || status === 'success'}
        className={`w-full mt-2 py-2 text-xs font-bold rounded-lg transition-all ${
          status === 'success' ? 'bg-green-500 text-white'
            : !rating ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
            : 'bg-slate-950 text-white hover:bg-slate-800'
        }`}
      >
        {status === 'loading' ? (
          <span className="flex items-center justify-center gap-1.5">
            <Loader className="w-3.5 h-3.5 animate-spin" /> Saving…
          </span>
        ) : status === 'success' ? 'Submitted ✓' : 'Submit Rating'}
      </button>
    </div>
  )
}

export function TechniqueCard({ technique, userId }: TechniqueCardProps) {
  const [wizardCompleted, setWizardCompleted] = useState(false)

  useEffect(() => {
    setWizardCompleted(technique?.user_completed ?? false)
  }, [technique?.id])

  if (!technique) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-gray-400 text-center px-4">
        <Sparkles className="w-10 h-10 opacity-25 mb-2" />
        <p className="text-sm">Exercises will appear here after your first message</p>
      </div>
    )
  }

  const catKey = technique.category?.toLowerCase() ?? ''
  const gradient = CATEGORY_COLOR[catKey] ?? 'from-slate-700 to-cyan-700'
  const icon = CATEGORY_ICON[catKey] ?? '*'

  return (
    <div key={technique.id} className="space-y-4">
      <div className={`rounded-xl bg-gradient-to-br ${gradient} p-4 text-center text-white`}>
        <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl border border-white/20 bg-white/20 text-3xl shadow-lg backdrop-blur-sm">
          {icon}
        </div>
        <h3 className="text-base font-bold leading-tight">{technique.name}</h3>
        <p className="mt-1 text-xs text-white/80">{technique.brief}</p>
        <div className="mt-3 flex flex-wrap justify-center gap-2">
          <span className="rounded-full bg-white/20 px-2 py-1 text-[11px] font-semibold">
            {technique.duration_minutes} min
          </span>
          <span className="rounded-full bg-white/20 px-2 py-1 text-[11px] font-semibold capitalize">
            {technique.difficulty ?? 'Moderate'}
          </span>
          <span className="rounded-full bg-white/20 px-2 py-1 text-[11px] font-semibold capitalize">
            {technique.category}
          </span>
        </div>
      </div>

      {technique.description && (
        <p className="rounded-xl bg-gray-50 p-3 text-xs leading-relaxed text-gray-600">
          {technique.description}
        </p>
      )}

      {technique.steps?.length > 0 && (
        <StepWizard steps={technique.steps} onComplete={() => setWizardCompleted(true)} />
      )}

      <StarRating userId={userId} technique={technique} wizardCompleted={wizardCompleted} />
    </div>
  )
}
