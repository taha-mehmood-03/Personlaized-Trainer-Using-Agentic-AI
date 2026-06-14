import React from 'react'
import Link from 'next/link'
import { Activity, BarChart3, LayoutDashboard, MessageCircle, Settings } from 'lucide-react'
import { Navbar } from '@/components/layout/Navbar'

const links = [
    { href: '/dashboard', label: 'Overview', icon: LayoutDashboard },
    { href: '/chat', label: 'Sessions', icon: MessageCircle },
    { href: '/dashboard#outcomes', label: 'Outcomes', icon: BarChart3 },
    { href: '/profile', label: 'Settings', icon: Settings },
]

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
    return (
        <div className="flex h-screen w-full overflow-hidden bg-slate-50">
            <aside className="hidden w-64 shrink-0 flex-col border-r border-slate-200 bg-white md:flex">
                <div className="border-b border-slate-100 p-5">
                    <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-900 text-white">
                            <Activity className="h-5 w-5" />
                        </div>
                        <div>
                            <p className="font-black tracking-tight text-slate-900">SentiMind</p>
                            <p className="text-xs font-medium text-slate-500">Analytics Console</p>
                        </div>
                    </div>
                </div>

                <nav className="flex-1 space-y-1 p-3">
                    {links.map(({ href, label, icon: Icon }) => (
                        <Link
                            key={label}
                            href={href}
                            prefetch={false}
                            className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-950"
                        >
                            <Icon className="h-4 w-4" />
                            {label}
                        </Link>
                    ))}
                </nav>

                <div className="border-t border-slate-100 p-4">
                    <div className="rounded-xl bg-slate-50 p-4">
                        <p className="text-xs font-semibold uppercase text-slate-400">Tracking</p>
                        <p className="mt-1 text-sm font-bold text-slate-900">Mood, symptoms, outcomes</p>
                    </div>
                </div>
            </aside>

            <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
                <Navbar />
                <div className="custom-scrollbar flex-1 overflow-y-auto p-4 sm:p-6">{children}</div>
            </div>
        </div>
    )
}
