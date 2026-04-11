import React from 'react'
import { Navbar } from '@/components/layout/Navbar'
import { Sidebar } from '@/components/layout/Sidebar'

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen w-full bg-slate-50 overflow-hidden">
      {/* 
        For dashboard, we reuse the Sidebar but potentially pass a flag
        or use a different variant if we wanted pure dashboard links,
        but the user requested the layout structure to remain consistent.
      */}
      <div className="w-64 shrink-0 border-r border-slate-200 bg-white hidden md:flex flex-col">
        <div className="p-4 border-b border-slate-100 font-bold text-slate-800">
          SentiMind
        </div>
        <div className="p-4 text-sm text-slate-500">
          Dashboard Menu (Stub)
        </div>
      </div>

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Navbar />
        <div className="flex-1 overflow-y-auto p-6 custom-scrollbar">
          {children}
        </div>
      </div>
    </div>
  )
}
