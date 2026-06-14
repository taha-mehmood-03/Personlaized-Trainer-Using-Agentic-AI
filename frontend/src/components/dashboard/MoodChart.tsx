import React from 'react'
import { MoodDataPoint } from '@/types'

interface MoodChartProps {
    data: MoodDataPoint[]
}

const clamp = (value: number) => Math.min(100, Math.max(0, value))

function pointPath(points: Array<{ x: number; y: number }>) {
    return points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ')
}

function buildPoints(data: MoodDataPoint[], key: 'score' | 'intensity') {
    const width = 640
    const height = 210
    const top = 18
    const bottom = 30
    const usableHeight = height - top - bottom
    const step = data.length > 1 ? width / (data.length - 1) : width

    return data.map((point, index) => {
        const value = key === 'score' ? point.score : point.intensity ?? 0
        return {
            x: Math.round(index * step),
            y: Math.round(top + (100 - clamp(value)) / 100 * usableHeight),
            value: clamp(value),
            label: point.date,
        }
    })
}

export const MoodChart = ({ data }: MoodChartProps) => {
    const chartData = data.slice(-18)
    const hasData = chartData.length > 0
    const scorePoints = buildPoints(hasData ? chartData : [{ date: 'No data', score: 0, intensity: 0, emotion: 'neutral' as const }], 'score')
    const intensityPoints = buildPoints(hasData ? chartData : [{ date: 'No data', score: 0, intensity: 0, emotion: 'neutral' as const }], 'intensity')
    const areaPath = hasData
        ? `${pointPath(scorePoints)} L ${scorePoints[scorePoints.length - 1].x} 210 L ${scorePoints[0].x} 210 Z`
        : ''
    const latest = chartData[chartData.length - 1]

    return (
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-start justify-between gap-4">
                <div>
                    <h2 className="text-sm font-bold text-slate-800">Mood and Intensity Timeline</h2>
                    <p className="mt-1 text-xs text-slate-500">
                        Score rises with positive mood and falls with distress intensity
                    </p>
                </div>
                <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">
                    {data.length} points
                </span>
            </div>

            {hasData ? (
                <>
                    <div className="mt-4 overflow-hidden rounded-xl border border-slate-100 bg-slate-50 p-3">
                        <svg viewBox="0 0 640 230" role="img" aria-label="Mood score and intensity timeline" className="h-72 w-full">
                            {[25, 50, 75, 100].map((tick) => {
                                const y = 18 + (100 - tick) / 100 * 162
                                return (
                                    <g key={tick}>
                                        <line x1="0" x2="640" y1={y} y2={y} stroke="#e2e8f0" strokeDasharray="4 6" />
                                        <text x="4" y={y - 5} fill="#94a3b8" fontSize="11">{tick}</text>
                                    </g>
                                )
                            })}
                            <path d={areaPath} fill="#0891b2" opacity="0.12" />
                            <path d={pointPath(scorePoints)} fill="none" stroke="#0891b2" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
                            <path d={pointPath(intensityPoints)} fill="none" stroke="#f97316" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
                            {scorePoints.map((point, index) => (
                                <circle key={`${point.x}-${index}`} cx={point.x} cy={point.y} r="4" fill="#0891b2" stroke="#ffffff" strokeWidth="2" />
                            ))}
                            <text x="0" y="224" fill="#64748b" fontSize="12">{chartData[0]?.date}</text>
                            <text x="640" y="224" fill="#64748b" fontSize="12" textAnchor="end">{latest?.date}</text>
                        </svg>
                    </div>

                    <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-500">
                        <span className="inline-flex items-center gap-1.5">
                            <span className="h-2.5 w-2.5 rounded-full bg-cyan-700" />
                            Mood score
                        </span>
                        <span className="inline-flex items-center gap-1.5">
                            <span className="h-2.5 w-2.5 rounded-full bg-orange-500" />
                            Intensity
                        </span>
                        {latest && (
                            <span className="capitalize text-slate-600">
                                Latest: {latest.emotion}{latest.primarySubEmotion ? ` / ${latest.primarySubEmotion.replaceAll('_', ' ')}` : ''}
                            </span>
                        )}
                    </div>
                </>
            ) : (
                <div className="mt-4 flex h-72 items-center justify-center rounded-xl border border-dashed border-slate-200 bg-slate-50 text-sm text-slate-500">
                    Mood timeline will appear after mood logs.
                </div>
            )}
        </section>
    )
}
