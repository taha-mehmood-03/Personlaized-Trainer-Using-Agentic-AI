import React from 'react'
import { Brain, Gauge, Layers, Sparkles } from 'lucide-react'
import { PsychologicalProfile as Profile } from '@/types'

interface PsychologicalProfileProps {
    profile: Profile
}

const baselineTone = {
    Low: 'bg-emerald-50 text-emerald-700',
    Moderate: 'bg-amber-50 text-amber-700',
    High: 'bg-rose-50 text-rose-700',
}

function label(value: string) {
    return value.replaceAll('_', ' ')
}

function Meter({ label, value }: { label: string; value: number }) {
    return (
        <div>
            <div className="flex items-center justify-between text-xs">
                <span className="font-medium text-slate-600">{label}</span>
                <span className="text-slate-500">{value}%</span>
            </div>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
                <div className="h-full rounded-full bg-slate-900" style={{ width: `${value}%` }} />
            </div>
        </div>
    )
}

export const PsychologicalProfileCard = ({ profile }: PsychologicalProfileProps) => {
    return (
        <section className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
            <div className="flex items-start justify-between gap-4">
                <div>
                    <h2 className="text-sm font-bold text-slate-800">Personalization Profile</h2>
                    <p className="text-xs text-slate-500 mt-1">Updated from mood, context, and technique feedback</p>
                </div>
                <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${baselineTone[profile.anxietyBaseline]}`}>
                    {profile.anxietyBaseline} distress
                </span>
            </div>

            <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div className="rounded-xl bg-slate-50 p-4">
                    <Brain className="h-4 w-4 text-slate-500" />
                    <p className="mt-3 text-xs font-medium text-slate-500">Coping style</p>
                    <p className="mt-1 text-lg font-black text-slate-900">{profile.copingStyle}</p>
                </div>
                <div className="rounded-xl bg-slate-50 p-4">
                    <Gauge className="h-4 w-4 text-slate-500" />
                    <p className="mt-3 text-xs font-medium text-slate-500">Resilience</p>
                    <p className="mt-1 text-lg font-black text-slate-900">{profile.resilience}%</p>
                </div>
                <div className="rounded-xl bg-slate-50 p-4">
                    <Layers className="h-4 w-4 text-slate-500" />
                    <p className="mt-3 text-xs font-medium text-slate-500">Distress baseline</p>
                    <p className="mt-1 text-lg font-black capitalize text-slate-900">
                        {profile.distressBaseline ?? 0}%
                    </p>
                </div>
            </div>

            <div className="mt-5 space-y-4">
                <Meter label="Technique acceptance" value={profile.techniqueAcceptanceRate ?? 0} />
                <Meter label="Reflection depth" value={profile.reflectionDepth ?? 0} />
                <Meter label="Social pressure signal" value={profile.socialDependency ?? 0} />
            </div>

            {(profile.emotionalTriggers?.length || profile.topDistortions?.length) ? (
                <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div>
                        <p className="text-xs font-semibold uppercase text-slate-400">Triggers</p>
                        <div className="mt-2 flex flex-wrap gap-2">
                            {(profile.emotionalTriggers ?? []).slice(0, 4).map((item) => (
                                <span key={item} className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700">
                                    {item}
                                </span>
                            ))}
                        </div>
                    </div>
                    <div>
                        <p className="text-xs font-semibold uppercase text-slate-400">Thought patterns</p>
                        <div className="mt-2 flex flex-wrap gap-2">
                            {(profile.topDistortions ?? []).slice(0, 4).map((item) => (
                                <span key={item} className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700">
                                    {item}
                                </span>
                            ))}
                        </div>
                    </div>
                </div>
            ) : null}

            {(profile.topPrimarySubEmotions?.length || profile.topSymptoms?.length || profile.topSecondaryEmotions?.length) ? (
                <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div>
                        <p className="text-xs font-semibold uppercase text-slate-400">Sub-emotions</p>
                        <div className="mt-2 flex flex-wrap gap-2">
                            {(profile.topPrimarySubEmotions ?? []).slice(0, 4).map((item) => (
                                <span key={item} className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium capitalize text-slate-700">
                                    {label(item)}
                                </span>
                            ))}
                        </div>
                    </div>
                    <div>
                        <p className="text-xs font-semibold uppercase text-slate-400">Secondary</p>
                        <div className="mt-2 flex flex-wrap gap-2">
                            {(profile.topSecondaryEmotions ?? []).slice(0, 4).map((item) => (
                                <span key={item} className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium capitalize text-slate-700">
                                    {label(item)}
                                </span>
                            ))}
                        </div>
                    </div>
                    <div>
                        <p className="text-xs font-semibold uppercase text-slate-400">Symptoms</p>
                        <div className="mt-2 flex flex-wrap gap-2">
                            {(profile.topSymptoms ?? []).slice(0, 4).map((item) => (
                                <span key={item} className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium capitalize text-slate-700">
                                    {label(item)}
                                </span>
                            ))}
                        </div>
                    </div>
                </div>
            ) : null}

            <div className="mt-5 flex items-start gap-3 rounded-xl border border-slate-100 bg-slate-50 p-4">
                <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-slate-700" />
                <p className="text-sm leading-6 text-slate-700">{profile.aiInsight}</p>
            </div>
        </section>
    )
}
