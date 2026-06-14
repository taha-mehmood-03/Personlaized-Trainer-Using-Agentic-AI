import React from 'react'
import { LayoutDashboard, UserRound } from 'lucide-react'
import Link from 'next/link'

interface NavbarProps {
    name?: string | null
}

export function Navbar({ name }: NavbarProps) {
    const initials = name
        ? name.split(' ').map((w: string) => w[0]).join('').toUpperCase().slice(0, 2)
        : null

    return (
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-4">
            <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-slate-900 shadow-sm">
                    <span className="text-lg font-bold leading-none text-white">S</span>
                </div>
                <span className="font-semibold tracking-tight text-slate-800">SentiMind</span>
            </div>

            <div className="flex items-center gap-2">
                <Link
                    href="/dashboard"
                    prefetch={false}
                    className="flex h-9 w-9 items-center justify-center rounded-xl text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-950"
                    title="Dashboard"
                    aria-label="Dashboard"
                >
                    <LayoutDashboard className="h-5 w-5" />
                </Link>

                <Link
                    href="/profile"
                    prefetch={false}
                    className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-900 text-xs font-bold text-white transition-colors hover:bg-slate-800"
                    title={name ?? 'Profile'}
                    aria-label="Profile"
                >
                    {initials ?? <UserRound className="h-4 w-4" />}
                </Link>
            </div>
        </header>
    )
}
