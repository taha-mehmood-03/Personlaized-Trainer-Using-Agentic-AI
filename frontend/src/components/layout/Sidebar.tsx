'use client'

import { useMemo } from 'react'
import { BarChart3, LogOut, MessageSquare, Plus, User as UserIcon, Zap } from 'lucide-react'
import { signOut } from 'next-auth/react'
import { Session, Technique } from '@/types'
import { SessionItem } from '@/components/layout/SessionItem'

const CATEGORY_GRADIENT: Record<string, string> = {
  breathing: 'from-cyan-500 to-blue-600',
  meditation: 'from-cyan-700 to-slate-900',
  mindfulness: 'from-emerald-500 to-cyan-700',
  grounding: 'from-amber-500 to-orange-600',
  cbt: 'from-slate-700 to-cyan-800',
  journaling: 'from-sky-500 to-cyan-600',
  dbt: 'from-blue-500 to-cyan-700',
  'behavioral activation': 'from-emerald-500 to-green-600',
  visualization: 'from-yellow-500 to-orange-500',
  general: 'from-slate-700 to-slate-900',
}

interface SidebarProps {
  sessions: Session[]
  currentSessionId: string | null
  isLoading: boolean
  activeTechnique?: Technique | null
  userName?: string | null
  userEmail?: string | null
  onNewSession: () => void
  onSelectSession: (id: string) => void | Promise<void>
  onDeleteSession: (id: string) => void | Promise<void>
  onRenameSession: (id: string, title: string) => void | Promise<void>
}

function groupSessions(sessions: Session[]) {
  return sessions.reduce((acc, session) => {
    const created = new Date(session.createdAt)
    const now = new Date()
    const diff = Math.floor((now.getTime() - created.getTime()) / 86400000)
    let group = 'Older'
    if (diff === 0) group = 'Today'
    else if (diff === 1) group = 'Yesterday'
    else if (diff < 7) group = 'Previous 7 Days'
    else if (diff < 30) group = 'Previous 30 Days'
    if (!acc[group]) acc[group] = []
    acc[group].push(session)
    return acc
  }, {} as Record<string, Session[]>)
}

export function Sidebar({
  sessions,
  currentSessionId,
  isLoading,
  activeTechnique,
  userName,
  userEmail,
  onNewSession,
  onSelectSession,
  onDeleteSession,
  onRenameSession,
}: SidebarProps) {
  const grouped = useMemo(() => groupSessions(sessions), [sessions])
  const groupOrder = ['Today', 'Yesterday', 'Previous 7 Days', 'Previous 30 Days', 'Older']
  const catKey = activeTechnique?.category?.toLowerCase() ?? 'general'
  const techGradient = CATEGORY_GRADIENT[catKey] ?? CATEGORY_GRADIENT.general

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 p-4">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-900 text-white">
              <MessageSquare className="h-5 w-5" />
            </div>
            <div>
              <p className="font-black tracking-tight text-slate-900">Sessions</p>
              <p className="text-xs text-slate-500">{sessions.length} saved chats</p>
            </div>
          </div>
          <BarChart3 className="h-4 w-4 text-slate-400" />
        </div>
      </div>

      <div className="p-3">
        <button
          onClick={onNewSession}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-3 text-sm font-bold text-white shadow-sm transition-colors hover:bg-slate-800"
        >
          <Plus className="h-4 w-4" />
          New conversation
        </button>
      </div>

      <div className="custom-scrollbar flex-1 overflow-y-auto px-3 pb-4">
        {isLoading ? (
          <div className="space-y-2 pt-2">
            {[1, 2, 3, 4].map((item) => (
              <div key={item} className="h-14 animate-pulse rounded-xl bg-slate-100" />
            ))}
          </div>
        ) : sessions.length === 0 ? (
          <div className="mt-8 rounded-xl border border-dashed border-slate-200 bg-slate-50 p-5 text-center">
            <MessageSquare className="mx-auto h-6 w-6 text-slate-400" />
            <p className="mt-3 text-sm font-bold text-slate-700">No chats yet</p>
            <p className="mt-1 text-xs leading-5 text-slate-500">Start a conversation and your history will appear here.</p>
          </div>
        ) : (
          <div className="space-y-5">
            {groupOrder.map((group) => {
              const items = grouped[group]
              if (!items?.length) return null
              return (
                <section key={group}>
                  <h3 className="mb-2 px-2 text-[11px] font-bold uppercase tracking-wider text-slate-400">
                    {group}
                  </h3>
                  <div className="space-y-1">
                    {items.map((item) => (
                      <SessionItem
                        key={item.id}
                        session={item}
                        isActive={currentSessionId === item.id}
                        onSelect={() => onSelectSession(item.id)}
                        onDelete={() => onDeleteSession(item.id)}
                        onRename={(title) => onRenameSession(item.id, title)}
                      />
                    ))}
                  </div>
                </section>
              )
            })}
          </div>
        )}
      </div>



      <div className="border-t border-slate-100 bg-white p-3">
        <button
          onClick={() => signOut({ callbackUrl: '/' })}
          className="flex w-full items-center justify-between rounded-xl p-2 transition-colors hover:bg-slate-50"
        >
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-900 text-xs font-bold text-white">
              {userName?.[0]?.toUpperCase() ?? <UserIcon className="h-4 w-4" />}
            </div>
            <div className="min-w-0 text-left">
              <p className="truncate text-sm font-bold text-slate-800">{userName ?? 'Account'}</p>
              <p className="truncate text-xs text-slate-400">{userEmail ?? ''}</p>
            </div>
          </div>
          <LogOut className="h-4 w-4 shrink-0 text-slate-400" />
        </button>
      </div>
    </div>
  )
}
