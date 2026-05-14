'use client'

import React from 'react'
import { PsychologicalProfile as Profile } from '@/types'
import { Sparkles } from 'lucide-react'

interface PsychologicalProfileProps {
    profile: Profile
}

const ANXIETY_COLOR = { Low: 'text-emerald-600', Moderate: 'text-amber-600', High: 'text-red-600' }
const ANXIETY_BG = { Low: 'bg-emerald-50', Moderate: 'bg-amber-50', High: 'bg-red-50' }

/** Card displaying the user's psychological profile and an AI-generated insight. */
export const PsychologicalProfileCard = ({ profile }: PsychologicalProfileProps) => {
    return (
        <div className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm space-y-4">
            <h3 className="text-sm font-bold text-slate-700">Psychological Profile</h3>

            <div className="grid grid-cols-3 gap-3">
                {/* Coping Style */}
                <div className="bg-purple-50 rounded-xl p-3 text-center">
                    <p className="text-[10px] font-semibold text-purple-500 uppercase tracking-wider">Coping Style</p>
                    <p className="text-base font-bold text-purple-800 mt-1">{profile.copingStyle}</p>
                </div>

                {/* Anxiety Baseline */}
                <div className={`rounded-xl p-3 text-center ${ANXIETY_BG[profile.anxietyBaseline]}`}>
                    <p className={`text-[10px] font-semibold uppercase tracking-wider ${ANXIETY_COLOR[profile.anxietyBaseline]}`}>
                        Anxiety Base
                    </p>
                    <p className={`text-base font-bold mt-1 ${ANXIETY_COLOR[profile.anxietyBaseline]}`}>
                        {profile.anxietyBaseline}
                    </p>
                </div>

                {/* Resilience */}
                <div className="bg-teal-50 rounded-xl p-3 text-center">
                    <p className="text-[10px] font-semibold text-teal-500 uppercase tracking-wider">Resilience</p>
                    <p className="text-base font-bold text-teal-800 mt-1">{profile.resilience}%</p>
                </div>
            </div>

            {/* Resilience bar */}
            <div>
                <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
                    <div
                        className="h-full rounded-full bg-gradient-to-r from-teal-400 to-purple-500 transition-all duration-1000"
                        style={{ width: `${profile.resilience}%` }}
                    />
                </div>
            </div>

            {/* AI Insight */}
            <div className="flex items-start gap-3 bg-gradient-to-r from-purple-50 to-teal-50 rounded-xl p-4 border border-purple-100">
                <Sparkles className="w-4 h-4 text-purple-500 mt-0.5 shrink-0" />
                <div>
                    <p className="text-[10px] font-bold text-purple-500 uppercase tracking-wider mb-1">AI Insight</p>
                    <p className="text-sm text-slate-700 leading-relaxed">{profile.aiInsight}</p>
                </div>
            </div>
        </div>
    )
}
