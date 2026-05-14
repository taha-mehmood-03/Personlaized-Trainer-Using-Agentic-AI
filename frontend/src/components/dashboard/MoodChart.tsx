'use client'

import React from 'react'
import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
} from 'recharts'
import { MoodDataPoint } from '@/types'

interface MoodChartProps {
    data: MoodDataPoint[]
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
        const score = payload[0].value as number
        return (
            <div className="bg-white border border-slate-200 rounded-xl shadow-lg px-4 py-3 text-sm">
                <p className="font-bold text-slate-800">{label}</p>
                <p className="text-purple-600 font-semibold">Mood: {score}%</p>
                <p className="text-slate-500 capitalize">{payload[0].payload?.emotion}</p>
            </div>
        )
    }
    return null
}

/** Line chart showing mood score over the past week. */
export const MoodChart = ({ data }: MoodChartProps) => {
    return (
        <div className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm">
            <h3 className="text-sm font-bold text-slate-700 mb-4">Mood Timeline</h3>
            <ResponsiveContainer width="100%" height={200}>
                <LineChart data={data} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
                    <defs>
                        <linearGradient id="moodGradient" x1="0" y1="0" x2="1" y2="0">
                            <stop offset="0%" stopColor="#7c3aed" />
                            <stop offset="100%" stopColor="#14b8a6" />
                        </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis
                        dataKey="date"
                        tick={{ fontSize: 12, fill: '#94a3b8' }}
                        axisLine={false}
                        tickLine={false}
                    />
                    <YAxis
                        domain={[0, 100]}
                        tick={{ fontSize: 12, fill: '#94a3b8' }}
                        axisLine={false}
                        tickLine={false}
                    />
                    <Tooltip content={<CustomTooltip />} />
                    <Line
                        type="monotone"
                        dataKey="score"
                        stroke="url(#moodGradient)"
                        strokeWidth={3}
                        dot={{ fill: '#7c3aed', r: 5, strokeWidth: 2, stroke: '#fff' }}
                        activeDot={{ r: 7, strokeWidth: 2, stroke: '#fff' }}
                    />
                </LineChart>
            </ResponsiveContainer>
        </div>
    )
}
