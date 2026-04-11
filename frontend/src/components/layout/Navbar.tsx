import React from 'react'
import { User, Bell, LayoutDashboard } from 'lucide-react'
import Link from 'next/link'

export function Navbar() {
  return (
    <header className="h-14 border-b border-slate-200 bg-white px-4 flex items-center justify-between shrink-0">
      <div className="flex items-center gap-2">
        <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-purple-500 to-teal-400 flex items-center justify-center shadow-sm">
          <span className="text-white font-bold text-lg leading-none">S</span>
        </div>
        <span className="font-semibold text-slate-800 tracking-tight">SentiMind Dashboard</span>
      </div>

      <div className="flex items-center gap-4">
        <Link href="/dashboard" className="text-slate-500 hover:text-purple-600 transition-colors">
          <LayoutDashboard className="w-5 h-5" />
        </Link>
        <button className="text-slate-500 hover:text-purple-600 transition-colors relative">
          <Bell className="w-5 h-5" />
          <span className="absolute top-0 right-0 w-2 h-2 rounded-full bg-red-500 border-2 border-white" />
        </button>
        <Link href="/profile" className="w-8 h-8 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center hover:ring-2 ring-purple-400 transition-all">
          <User className="w-4 h-4 text-slate-600" />
        </Link>
      </div>
    </header>
  )
}
