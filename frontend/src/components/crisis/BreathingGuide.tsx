import React from 'react'

export function BreathingGuide() {
  return (
    <div className="p-4 bg-teal-50 rounded-xl border border-teal-100">
      <p className="text-sm font-semibold text-teal-800 mb-2">4-7-8 Breathing</p>
      <div className="flex justify-between text-xs text-teal-600">
        <span>Breathe in (4s)</span>
        <span>Hold (7s)</span>
        <span>Exhale (8s)</span>
      </div>
    </div>
  )
}
