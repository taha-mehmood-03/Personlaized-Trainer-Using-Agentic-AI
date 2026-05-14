'use client'

import React from 'react'
import {
    PieChart,
    Pie,
    Cell,
    Tooltip,
    Legend,
    ResponsiveContainer,
} from 'recharts'
import { EmotionSlice } from '@/types'

const EMOTION_COLORS: Record<string, string> = {
    joy: '#10b981',
    sadness: '#6366f1',
    anxiety: '#f59e0b',
    anger: '#ef4444',
    fear: '#8b5cf6',
    disgust: '#64748b',
    neutral: '#94a3b8',
    surprise: '#06b6d4',
    guilt: '#f97316',
}

interface EmotionDistributionProps {
    data: EmotionSlice[]
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
        const entry = payload[0].payload as EmotionSlice
        return (
            <div className="bg-white border border-slate-200 rounded-xl shadow-lg px-4 py-3 text-sm">
                <p className="font-bold text-slate-800 capitalize">{entry.emotion}</p>
                <p className="text-slate-500">{entry.percentage}% of sessions</p>
            </div>
        )
    }
    return null
}

/** Donut pie chart showing emotion distribution. */
export const EmotionDistribution = ({ data }: EmotionDistributionProps) => {
    return (
        <div className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm">
            <h3 className="text-sm font-bold text-slate-700 mb-4">Emotion Distribution</h3>
            <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                    <Pie
                        data={data}
                        dataKey="count"
                        nameKey="emotion"
                        cx="50%"
                        cy="50%"
                        innerRadius={55}
                        outerRadius={80}
                        paddingAngle={3}
                    >
                        {data.map((entry) => (
                            <Cell
                                key={entry.emotion}
                                fill={EMOTION_COLORS[entry.emotion] ?? '#94a3b8'}
                            />
                        ))}
                    </Pie>
                    <Tooltip content={<CustomTooltip />} />
                    <Legend
                        formatter={(value) => (
                            <span className="text-xs text-slate-600 capitalize">{value}</span>
                        )}
                    />
                </PieChart>
            </ResponsiveContainer>
        </div>
    )
}
