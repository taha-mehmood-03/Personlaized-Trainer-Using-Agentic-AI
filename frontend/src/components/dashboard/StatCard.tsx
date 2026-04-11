import React from 'react'
export function StatCard({ title, value }: { title: string, value: React.ReactNode }) {
  return <div className="p-6 bg-white border border-slate-200 rounded-xl shadow-sm">
    <h3 className="text-sm font-medium text-slate-500">{title}</h3>
    <p className="text-2xl font-bold text-slate-900 mt-2">{value}</p>
  </div>
}
