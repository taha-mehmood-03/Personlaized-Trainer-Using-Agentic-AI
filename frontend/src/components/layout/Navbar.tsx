'use client'

import React from 'react'
import { useSession, signOut } from 'next-auth/react'
import { Bell, LayoutDashboard } from 'lucide-react'
import Link from 'next/link'

export function Navbar() {
    const { data: session } = useSession()
    const name = session?.user?.name
    const initials = name
        ? name.split(' ').map((w: string) => w[0]).join('').toUpperCase().slice(0, 2)
        : '?'

    return (
        <header className="h-14 border-b border-slate-200 bg-white px-4 flex items-center justify-between shrink-0">
            <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-purple-500 to-teal-400 flex items-center justify-center shadow-sm">
                    <span className="text-white font-bold text-lg leading-none">S</span>
                </div>
                <span className="font-semibold text-slate-800 tracking-tight">SentiMind</span>
            </div>

            <div className="flex items-center gap-4">
                <Link href="/dashboard" className="text-slate-500 hover:text-purple-600 transition-colors" title="Dashboard">
                    <LayoutDashboard className="w-5 h-5" />
                </Link>

                <button className="text-slate-500 hover:text-purple-600 transition-colors relative" aria-label="Notifications">
                    <Bell className="w-5 h-5" />
                    <span className="absolute top-0 right-0 w-2 h-2 rounded-full bg-red-500 border-2 border-white" />
                </button>

                {/* Avatar — links to profile, shows initials from session */}
                <Link
                    href="/profile"
                    className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-500 to-teal-400 flex items-center justify-center text-white text-xs font-bold hover:ring-2 ring-purple-400 ring-offset-1 transition-all"
                    title={name ?? 'Profile'}
                >
                    {initials}
                </Link>
            </div>
        </header>
    )
}
