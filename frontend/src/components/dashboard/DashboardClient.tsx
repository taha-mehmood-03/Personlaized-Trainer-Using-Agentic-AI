import React from 'react'
import {
    Activity,
    AlertCircle,
    CalendarDays,
    Clock3,
    Database,
    HeartPulse,
    Sparkles,
    Target,
    TrendingUp,
} from 'lucide-react'
import { StatCard } from '@/components/dashboard/StatCard'
import { MoodChart } from '@/components/dashboard/MoodChart'
import { EmotionDistribution } from '@/components/dashboard/EmotionDistribution'
import { TopTechniques } from '@/components/dashboard/TopTechniques'
import { SessionHistoryTable } from '@/components/dashboard/SessionHistoryTable'
import { PsychologicalProfileCard } from '@/components/dashboard/PsychologicalProfileCard'
import { OutcomeRadar } from '@/components/dashboard/OutcomeRadar'
import { TechniqueOutcomeChart } from '@/components/dashboard/TechniqueOutcomeChart'
import { SuggestionPanel } from '@/components/dashboard/SuggestionPanel'
import { ImprovementAnalysisPanel } from '@/components/dashboard/ImprovementAnalysisPanel'
import { SignalBreakdown } from '@/components/dashboard/SignalBreakdown'
import { VoiceInsightsCard } from '@/components/dashboard/VoiceInsightsCard'
import { ClinicalValidityCard } from '@/components/dashboard/ClinicalValidityCard'
import { DashboardStats } from '@/types'

const skeletons = Array.from({ length: 5 })

function DashboardSkeleton() {
    return (
        <div className="space-y-6">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
                {skeletons.map((_, index) => (
                    <div key={index} className="h-32 animate-pulse rounded-xl bg-slate-100" />
                ))}
            </div>
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
                <div className="h-80 animate-pulse rounded-xl bg-slate-100 xl:col-span-2" />
                <div className="h-80 animate-pulse rounded-xl bg-slate-100" />
            </div>
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                <div className="h-72 animate-pulse rounded-xl bg-slate-100" />
                <div className="h-72 animate-pulse rounded-xl bg-slate-100" />
            </div>
        </div>
    )
}

interface DashboardClientProps {
    initialStats: DashboardStats | null
}

export function DashboardClient({ initialStats }: DashboardClientProps) {
    const stats = initialStats
    const dataDepth = stats ? stats.dataQuality.moodLogs + stats.dataQuality.emotionSnapshots : 0
    const generatedLabel = stats?.generatedAt
        ? new Date(stats.generatedAt).toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: 'numeric',
            minute: '2-digit',
        })
        : null

    return (
        <main className="space-y-6 pb-10">
            <header className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
                    <div>
                        <div className="flex flex-wrap items-center gap-2">
                            <span className="rounded-full bg-slate-900 px-3 py-1 text-xs font-semibold text-white">
                                Advanced analytics
                            </span>
                            <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
                                Background tracking enabled
                            </span>
                            {stats && (
                                <span className="rounded-full bg-cyan-50 px-3 py-1 text-xs font-semibold text-cyan-700">
                                    {stats.windowDays}-day window
                                </span>
                            )}
                        </div>
                        <h1 className="mt-4 text-2xl font-black tracking-tight text-slate-950">
                            Wellness Dashboard
                        </h1>
                        <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-600 sm:block">
                            Mood, symptoms, outcomes, and personalization in one view.
                        </p>
                    </div>

                    {stats && (
                    <div className="grid grid-cols-2 gap-3 rounded-xl border border-slate-100 bg-slate-50 p-3 text-center sm:grid-cols-4">
                            <div className="px-3">
                                <p className="text-[11px] font-semibold uppercase text-slate-400">Trend</p>
                                <p className="mt-1 text-sm font-black capitalize text-slate-900">
                                    {stats.longTermOutcomes.moodTrendLabel}
                                </p>
                                {stats.compositeScore !== undefined && (
                                    <p className="text-[10px] text-slate-400 mt-0.5">
                                        {Math.round(stats.compositeScore * 100)}% composite
                                    </p>
                                )}
                            </div>
                            <div className="border-x border-slate-200 px-3">
                                <p className="text-[11px] font-semibold uppercase text-slate-400">Readiness</p>
                                <p className="mt-1 text-sm font-black text-slate-900">
                                    {stats.longTermOutcomes.interventionReadiness}%
                                </p>
                            </div>
                            <div className="px-3 sm:border-r sm:border-slate-200">
                                <p className="text-[11px] font-semibold uppercase text-slate-400">Records</p>
                                <p className="mt-1 text-sm font-black text-slate-900">{dataDepth}</p>
                            </div>
                            <div className="px-3">
                                <p className="text-[11px] font-semibold uppercase text-slate-400">Updated</p>
                                <p className="mt-1 text-sm font-black text-slate-900">
                                    {generatedLabel ?? 'Live'}
                                </p>
                            </div>
                        </div>
                    )}
                </div>
            </header>

            {!stats && (
                <div className="flex items-center gap-2 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
                    <AlertCircle className="h-4 w-4 shrink-0" />
                    Could not load dashboard stats. Start chatting to generate insights, then refresh the dashboard.
                </div>
            )}

            {!stats ? (
                <DashboardSkeleton />
            ) : (
                <>
                    <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
                        <StatCard
                            title="Total Sessions"
                            value={stats.totalSessions}
                            icon={<CalendarDays className="h-4 w-4" />}
                            sub={`${stats.sessionsThisWeek} this week`}
                            color="text-slate-700"
                            gradient="from-white to-slate-50"
                        />
                        <StatCard
                            title="Mood Score"
                            value={`${stats.avgMood}%`}
                            icon={<HeartPulse className="h-4 w-4" />}
                            trend={stats.moodTrend}
                            sub={`${stats.longTermOutcomes.moodTrendDelta} delta`}
                            color="text-emerald-700"
                            gradient="from-white to-emerald-50"
                        />
                        <StatCard
                            title="Dominant Emotion"
                            value={<span className="capitalize">{stats.topEmotion}</span>}
                            icon={<Activity className="h-4 w-4" />}
                            sub={stats.topSubEmotion ? `${stats.topSubEmotion} sub-emotion` : `${stats.dataQuality.moodLogs} mood logs`}
                            color="text-amber-700"
                            gradient="from-white to-amber-50"
                        />
                        <StatCard
                            title="Check-In Streak"
                            value={`${stats.streak}d`}
                            icon={<TrendingUp className="h-4 w-4" />}
                            sub="current streak"
                            color="text-sky-700"
                            gradient="from-white to-sky-50"
                        />
                        <StatCard
                            title="Technique Fit"
                            value={`${stats.longTermOutcomes.techniqueEffectiveness}%`}
                            icon={<Target className="h-4 w-4" />}
                            sub={`${stats.longTermOutcomes.techniqueAdherenceRate}% adherence`}
                            color="text-cyan-700"
                            gradient="from-white to-cyan-50"
                        />
                    </section>

                    {/* ── Clinical Tool Validity (GAD-7 / PHQ-9) ───────────────────── */}
                    {stats.clinicalAssessment?.hasData && (
                        <ClinicalValidityCard assessment={stats.clinicalAssessment} />
                    )}

                    <section id="outcomes" className="content-auto grid grid-cols-1 gap-4 xl:grid-cols-3">
                        <div className="xl:col-span-2">
                            <MoodChart data={stats.moodTimeline} />
                        </div>
                        <OutcomeRadar stats={stats} />
                    </section>

                    <div className="content-auto">
                        <ImprovementAnalysisPanel
                            analysis={stats.longTermOutcomes.improvementAnalysis}
                        />
                    </div>

                    <div className="content-auto">
                        <VoiceInsightsCard insights={stats.voiceInsights} />
                    </div>

                    <div className="content-auto">
                        <SignalBreakdown
                            secondaryEmotions={stats.secondaryEmotionDistribution}
                            symptoms={stats.symptomDistribution}
                            behaviors={stats.behaviorDistribution}
                            contexts={stats.contextDistribution}
                            subEmotions={stats.subEmotionDistribution}
                        />
                    </div>

                    <section className="content-auto grid grid-cols-1 gap-4 xl:grid-cols-3">
                        <EmotionDistribution data={stats.emotionDistribution} subEmotions={stats.subEmotionDistribution} />
                        <div className="xl:col-span-2">
                            <TechniqueOutcomeChart outcomes={stats.techniqueOutcomes} />
                        </div>
                    </section>

                    <section className="content-auto grid grid-cols-1 gap-4 xl:grid-cols-2">
                        <TopTechniques data={stats.topTechniques} preferredCategories={stats.preferredCategories} />
                        <PsychologicalProfileCard profile={stats.psychologicalProfile} />
                    </section>

                    <section className="content-auto">
                        <SuggestionPanel suggestions={stats.suggestions} />
                    </section>

                    {stats.dataQuality.warnings.length > 0 && (
                        <section className="content-auto rounded-xl border border-amber-200 bg-amber-50 p-4">
                            <div className="flex items-start gap-3">
                                <Database className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
                                <div>
                                    <p className="text-sm font-bold text-amber-900">Data quality notes</p>
                                    <div className="mt-2 flex flex-wrap gap-2">
                                        {stats.dataQuality.warnings.map((warning) => (
                                            <span key={warning} className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-amber-800">
                                                {warning}
                                            </span>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        </section>
                    )}

                    <section className="content-auto rounded-xl border border-slate-200 bg-white p-4">
                        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                            <div className="flex items-start gap-3">
                                <Clock3 className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
                                <div>
                                    <p className="text-sm font-bold text-slate-900">Analytics window</p>
                                    <p className="mt-1 text-xs leading-5 text-slate-500">
                                        Mood score, dominant emotion, distributions, signals, and outcomes use the current {stats.windowDays}-day dashboard window.
                                    </p>
                                </div>
                            </div>
                            <div className="grid grid-cols-4 gap-2 text-center text-xs sm:min-w-[24rem]">
                                <div className="rounded-lg bg-slate-50 px-2 py-2">
                                    <p className="font-black text-slate-900">{stats.dataQuality.moodLogs}</p>
                                    <p className="text-slate-500">moods</p>
                                </div>
                                <div className="rounded-lg bg-slate-50 px-2 py-2">
                                    <p className="font-black text-slate-900">{stats.dataQuality.emotionSnapshots}</p>
                                    <p className="text-slate-500">signals</p>
                                </div>
                                <div className="rounded-lg bg-slate-50 px-2 py-2">
                                    <p className="font-black text-slate-900">{stats.dataQuality.sessions}</p>
                                    <p className="text-slate-500">sessions</p>
                                </div>
                                <div className="rounded-lg bg-slate-50 px-2 py-2">
                                    <p className="font-black text-slate-900">{stats.dataQuality.ratings}</p>
                                    <p className="text-slate-500">ratings</p>
                                </div>
                            </div>
                        </div>
                    </section>

                    <div className="content-auto">
                        <SessionHistoryTable sessions={stats.recentSessions} />
                    </div>

                    <footer className="flex items-center justify-center gap-2 pt-2 text-xs text-slate-400">
                        <Sparkles className="h-3.5 w-3.5" />
                        Analytics refresh in the background after each completed response.
                    </footer>
                </>
            )}
        </main>
    )
}
