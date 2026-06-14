import React from 'react'
import { BrainCircuit, ListChecks, MapPinned, Waves } from 'lucide-react'
import { DashboardSignalSlice, SubEmotionSlice } from '@/types'

interface SignalBreakdownProps {
    secondaryEmotions: DashboardSignalSlice[]
    symptoms: DashboardSignalSlice[]
    behaviors: DashboardSignalSlice[]
    contexts: DashboardSignalSlice[]
    subEmotions: SubEmotionSlice[]
}

function label(value: string) {
    return value.replaceAll('_', ' ')
}

function SignalList({
    title,
    icon,
    items,
}: {
    title: string
    icon: React.ReactNode
    items: DashboardSignalSlice[]
}) {
    return (
        <div className="min-w-0">
            <div className="mb-3 flex items-center gap-2">
                <span className="rounded-lg bg-slate-100 p-1.5 text-slate-600">{icon}</span>
                <h3 className="text-xs font-bold uppercase text-slate-500">{title}</h3>
            </div>
            {items.length ? (
                <div className="space-y-3">
                    {items.slice(0, 6).map((item) => (
                        <div key={item.name}>
                            <div className="flex items-center justify-between gap-3 text-xs">
                                <span className="truncate capitalize text-slate-700">{label(item.name)}</span>
                                <span className="shrink-0 font-semibold text-slate-500">{item.count}</span>
                            </div>
                            <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-100">
                                <div className="h-full rounded-full bg-slate-800" style={{ width: `${item.percentage}%` }} />
                            </div>
                        </div>
                    ))}
                </div>
            ) : (
                <p className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-5 text-center text-xs text-slate-500">
                    No signals yet.
                </p>
            )}
        </div>
    )
}

export function SignalBreakdown({
    secondaryEmotions,
    symptoms,
    behaviors,
    contexts,
    subEmotions,
}: SignalBreakdownProps) {
    const primaryAsSignals = subEmotions.map((item) => ({
        name: item.subEmotion,
        count: item.count,
        percentage: item.percentage,
    }))

    return (
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div>
                    <h2 className="text-sm font-bold text-slate-800">Detailed Mood Signals</h2>
                    <p className="mt-1 text-xs text-slate-500">
                        Primary sub-emotions, secondary emotions, symptoms, behaviors, and contexts from saved turns
                    </p>
                </div>
                <span className="w-fit rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">
                    {symptoms.length + secondaryEmotions.length + behaviors.length + contexts.length} tracked
                </span>
            </div>

            <div className="mt-5 grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-5">
                <SignalList title="Primary sub-emotions" icon={<BrainCircuit className="h-3.5 w-3.5" />} items={primaryAsSignals} />
                <SignalList title="Secondary emotions" icon={<Waves className="h-3.5 w-3.5" />} items={secondaryEmotions} />
                <SignalList title="Symptoms" icon={<ListChecks className="h-3.5 w-3.5" />} items={symptoms} />
                <SignalList title="Behaviors" icon={<ListChecks className="h-3.5 w-3.5" />} items={behaviors} />
                <SignalList title="Contexts" icon={<MapPinned className="h-3.5 w-3.5" />} items={contexts} />
            </div>
        </section>
    )
}
