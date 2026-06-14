'use client'

import React, { useEffect, useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight, Check, Clock, Flag, ListChecks, Sparkles, Star } from 'lucide-react'
import { Technique } from '@/types'
import { submitTechniqueRating } from '@/actions/technique'

interface TechniquePanelProps {
  technique?: Technique | null
  alternativeTechniques?: Technique[]
  userId: string
  sessionId?: string | null
}

const CATEGORY_GRADIENT: Record<string, string> = {
  breathing: 'from-cyan-500 to-blue-600',
  meditation: 'from-cyan-700 to-slate-900',
  mindfulness: 'from-emerald-500 to-cyan-700',
  grounding: 'from-amber-500 to-orange-600',
  cbt: 'from-slate-700 to-cyan-800',
  journaling: 'from-sky-500 to-cyan-600',
  dbt: 'from-blue-500 to-cyan-700',
  'behavioral activation': 'from-emerald-500 to-green-600',
  visualization: 'from-yellow-500 to-orange-500',
  general: 'from-slate-700 to-slate-900',
}

function StepWizard({ steps, onComplete, initialDone = false }: { steps: string[]; onComplete: () => void; initialDone?: boolean }) {
  const [step, setStep] = useState(initialDone && steps.length ? steps.length - 1 : 0)
  const [done, setDone] = useState(initialDone)

  const progress = steps.length ? Math.round(((step + 1) / steps.length) * 100) : 0

  const next = () => {
    if (step < steps.length - 1) {
      setStep((value) => value + 1)
      return
    }
    setDone(true)
    onComplete()
  }

  useEffect(() => {
    setDone(initialDone)
    setStep(initialDone && steps.length ? steps.length - 1 : 0)
  }, [initialDone, steps.length])

  if (!steps.length) {
    return (
      <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
        No guided steps are attached to this technique yet.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-xs text-slate-500">
        <span>Step {step + 1} of {steps.length}</span>
        <span>{progress}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-100">
        <div className="h-full rounded-full bg-slate-900 transition-all" style={{ width: `${progress}%` }} />
      </div>
      <div className="min-h-[112px] rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-3 flex h-8 w-8 items-center justify-center rounded-lg bg-slate-900 text-xs font-black text-white">
          {step + 1}
        </div>
        <p className="text-sm leading-6 text-slate-700">{steps[step]}</p>
      </div>
      <div className="flex items-center justify-between gap-2">
        <button
          onClick={() => setStep((value) => Math.max(0, value - 1))}
          disabled={step === 0}
          className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          Back
        </button>
        <button
          onClick={next}
          disabled={done}
          className="inline-flex items-center gap-1 rounded-xl bg-slate-900 px-3 py-2 text-xs font-bold text-white transition-colors hover:bg-slate-800 disabled:bg-emerald-600"
        >
          {done ? (
            <>
              <Check className="h-3.5 w-3.5" />
              Done
            </>
          ) : step < steps.length - 1 ? (
            <>
              Next
              <ChevronRight className="h-3.5 w-3.5" />
            </>
          ) : (
            <>
              Finish
              <Flag className="h-3.5 w-3.5" />
            </>
          )}
        </button>
      </div>
    </div>
  )
}

function StarRating({
  userId,
  techniqueId,
  wizardCompleted,
  initialRating = 0,
  sessionId,
}: {
  userId: string
  techniqueId: string
  wizardCompleted: boolean
  initialRating?: number
  sessionId?: string | null
}) {
  const [rating, setRating] = useState(initialRating)
  const [hover, setHover] = useState(0)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    setRating(initialRating)
  }, [initialRating])

  const handleClick = async (value: number) => {
    if (!wizardCompleted) return
    setRating(value)
    try {
      await submitTechniqueRating({
        user_id: userId,
        technique_id: techniqueId,
        rating: value,
        completed: wizardCompleted,
        session_id: sessionId,
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } catch {
      setSaved(false)
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <p className="text-xs font-bold uppercase tracking-wider text-slate-400">Rate impact</p>
      <div className={`mt-3 flex items-center gap-1.5 ${wizardCompleted ? '' : 'opacity-40'}`}>
        {[1, 2, 3, 4, 5].map((value) => (
          <button
            key={value}
            onClick={() => handleClick(value)}
            onMouseEnter={() => setHover(value)}
            onMouseLeave={() => setHover(0)}
            disabled={!wizardCompleted}
            className="transition-transform hover:scale-110 disabled:cursor-not-allowed"
          >
            <Star
              className={`h-5 w-5 ${
                value <= (hover || rating) ? 'fill-amber-400 text-amber-400' : 'text-slate-200'
              }`}
            />
          </button>
        ))}
        {saved && <span className="ml-2 text-xs font-semibold text-emerald-600">Saved</span>}
      </div>
      {!wizardCompleted && (
        <p className="mt-2 text-xs text-slate-500">Complete the guided steps before rating.</p>
      )}
    </div>
  )
}

export function TechniquePanel({ technique, alternativeTechniques = [], userId, sessionId }: TechniquePanelProps) {
  const allTechniques = useMemo(
    () => (technique ? [technique, ...alternativeTechniques] : []),
    [technique, alternativeTechniques]
  )
  const [selectedIdx, setSelectedIdx] = useState(0)
  const [wizardCompleted, setWizardCompleted] = useState(false)

  const active = allTechniques[selectedIdx] ?? null
  const catKey = active?.category?.toLowerCase() ?? 'general'
  const gradient = CATEGORY_GRADIENT[catKey] ?? CATEGORY_GRADIENT.general

  useEffect(() => {
    setSelectedIdx(0)
    setWizardCompleted(technique?.user_completed ?? false)
  }, [technique?.id, sessionId])

  return (
    <aside className="hidden w-80 shrink-0 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm xl:flex xl:flex-col">
      <div className="border-b border-slate-100 p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-slate-400">Resources</p>
            <h2 className="mt-1 text-base font-black text-slate-900">Technique Panel</h2>
          </div>
          <Sparkles className="h-5 w-5 text-slate-400" />
        </div>
      </div>

      <div className="custom-scrollbar flex-1 overflow-y-auto p-4">
        {active ? (
          <div className="space-y-4">
            <div className={`rounded-2xl bg-gradient-to-br ${gradient} p-5 text-white shadow-sm`}>
              <p className="text-[11px] font-bold uppercase tracking-wider text-white/70">Active support</p>
              <h3 className="mt-2 text-lg font-black leading-tight">{active.name}</h3>
              <p className="mt-2 text-sm leading-6 text-white/85">{active.brief}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                <span className="inline-flex items-center gap-1 rounded-full bg-white/15 px-2.5 py-1 text-xs font-semibold">
                  <Clock className="h-3.5 w-3.5" />
                  {active.duration_minutes} min
                </span>
                <span className="rounded-full bg-white/15 px-2.5 py-1 text-xs font-semibold capitalize">
                  {active.difficulty ?? 'easy'}
                </span>
                <span className="rounded-full bg-white/15 px-2.5 py-1 text-xs font-semibold capitalize">
                  {active.category}
                </span>
              </div>
            </div>

            {allTechniques.length > 1 && (
              <div className="grid grid-cols-2 gap-2">
                {allTechniques.map((item, index) => (
                  <button
                    key={item.id}
                    onClick={() => {
                      setSelectedIdx(index)
                      setWizardCompleted(item.user_completed ?? false)
                    }}
                    className={`rounded-xl border px-3 py-2 text-left text-xs font-semibold transition-colors ${
                      index === selectedIdx
                        ? 'border-slate-900 bg-slate-900 text-white'
                        : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                    }`}
                  >
                    {item.name}
                  </button>
                ))}
              </div>
            )}

            {active.description && (
              <p className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-600">
                {active.description}
              </p>
            )}

            <div>
              <div className="mb-3 flex items-center gap-2">
                <ListChecks className="h-4 w-4 text-slate-500" />
                <p className="text-sm font-bold text-slate-800">Guided steps</p>
              </div>
              <StepWizard
                key={`${active.id}-${sessionId}`}
                steps={active.steps ?? []}
                onComplete={async () => {
                  setWizardCompleted(true)
                  try {
                    await submitTechniqueRating({
                      user_id: userId,
                      technique_id: active.id,
                      completed: true,
                      session_id: sessionId,
                    })
                  } catch (err) {
                    console.error('Failed to submit automatic technique completion:', err)
                  }
                }}
                initialDone={active.user_completed ?? false}
              />
            </div>

            {active.why_it_works && (
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <p className="text-xs font-bold uppercase tracking-wider text-slate-400">Why it can help</p>
                <p className="mt-2 text-sm leading-6 text-slate-600">{active.why_it_works}</p>
              </div>
            )}

            <StarRating key={`${active.id}-${sessionId}`} userId={userId} techniqueId={active.id} wizardCompleted={wizardCompleted} initialRating={active.user_rating ?? 0} sessionId={sessionId} />
          </div>
        ) : (
          <div className="flex h-full min-h-[420px] flex-col items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-6 text-center">
            <Sparkles className="h-8 w-8 text-slate-400" />
            <h3 className="mt-4 text-sm font-black text-slate-800">No active technique</h3>
            <p className="mt-2 text-sm leading-6 text-slate-500">
              This panel will show exercise steps only when the conversation reaches the right support stage.
            </p>
          </div>
        )}
      </div>
    </aside>
  )
}
