'use client'

import React, { useEffect, useState } from 'react'

type Phase = 'in' | 'hold' | 'out' | 'idle'

const RHYTHM: { phase: Phase; label: string; duration: number; color: string }[] = [
    { phase: 'in', label: 'Breathe In', duration: 4000, color: 'from-teal-400 to-cyan-500' },
    { phase: 'hold', label: 'Hold', duration: 4000, color: 'from-cyan-400 to-blue-500' },
    { phase: 'out', label: 'Breathe Out', duration: 6000, color: 'from-blue-400 to-purple-500' },
]

interface BreathingGuideProps {
    autoStart?: boolean
}

/** Animated 4-4-6 breathing guide with pulsing circle and phase labels. */
export function BreathingGuide({ autoStart = false }: BreathingGuideProps) {
    const [phaseIdx, setPhaseIdx] = useState(0)
    const [running, setRunning] = useState(autoStart)
    const [progress, setProgress] = useState(0)

    useEffect(() => {
        if (!running) return

        const current = RHYTHM[phaseIdx]
        const start = Date.now()
        let raf: number

        const tick = () => {
            const elapsed = Date.now() - start
            const pct = Math.min(elapsed / current.duration, 1)
            setProgress(pct)

            if (pct < 1) {
                raf = requestAnimationFrame(tick)
            } else {
                setProgress(0)
                setPhaseIdx((prev) => (prev + 1) % RHYTHM.length)
            }
        }

        raf = requestAnimationFrame(tick)
        return () => cancelAnimationFrame(raf)
    }, [running, phaseIdx])

    const current = RHYTHM[phaseIdx]
    const scale = current.phase === 'in' ? 1 + progress * 0.4 : current.phase === 'out' ? 1.4 - progress * 0.4 : 1.4

    return (
        <div className="flex flex-col items-center gap-6 py-4">
            {/* Breathing circle */}
            <div className="relative flex items-center justify-center">
                <div
                    className={`w-32 h-32 rounded-full bg-gradient-to-br ${running ? current.color : 'from-slate-200 to-slate-300'} shadow-lg transition-all`}
                    style={{
                        transform: `scale(${running ? scale : 1})`,
                        transition: running ? 'transform 0.1s linear' : 'transform 0.3s ease',
                    }}
                />
                <div className="absolute inset-0 flex items-center justify-center">
                    <p className="text-white font-bold text-sm drop-shadow-md">
                        {running ? current.label : 'Ready'}
                    </p>
                </div>
            </div>

            {/* Phase indicators */}
            <div className="flex items-center gap-4 text-xs font-semibold">
                {RHYTHM.map((r, i) => (
                    <div key={r.phase} className={`flex flex-col items-center gap-1 transition-all ${running && i === phaseIdx ? 'text-purple-700' : 'text-slate-400'}`}>
                        <div className={`w-2 h-2 rounded-full ${running && i === phaseIdx ? 'bg-purple-500' : 'bg-slate-200'}`} />
                        <span>{r.label}</span>
                        <span className="font-normal">{r.duration / 1000}s</span>
                    </div>
                ))}
            </div>

            {/* Control */}
            <button
                onClick={() => setRunning((r) => !r)}
                className={`px-6 py-2 rounded-xl text-sm font-bold transition-all ${
                    running
                        ? 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                        : 'bg-gradient-to-r from-purple-600 to-teal-500 text-white shadow-md hover:shadow-lg'
                }`}
            >
                {running ? 'Pause' : 'Start Breathing'}
            </button>

            <p className="text-xs text-slate-400 text-center">
                Follow the rhythm to calm your nervous system
            </p>
        </div>
    )
}
