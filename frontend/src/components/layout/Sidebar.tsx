'use client'

import { format } from 'date-fns'
import { Plus, MessageSquare, Menu, LogOut, User as UserIcon } from 'lucide-react'
import { Session } from '@/types'
import { SessionItem } from '@/components/layout/SessionItem'
import { useAuth } from '@/components/providers/AuthProvider'

interface SidebarProps {
  sessions: Session[]
  currentSessionId: string | null
  isLoading: boolean
  onNewSession: () => void
  onSelectSession: (id: string) => void
  onDeleteSession: (id: string) => void
  onRenameSession: (id: string, title: string) => void
}

export function Sidebar({
  sessions,
  currentSessionId,
  isLoading,
  onNewSession,
  onSelectSession,
  onDeleteSession,
  onRenameSession,
}: SidebarProps) {
  const { logout } = useAuth()

  // Group sessions by date
  const grouped = sessions.reduce((acc, session) => {
    const d = new Date(session.createdAt)
    const now = new Date()
    const diff = Math.floor((now.getTime() - d.getTime()) / 86400000)

    let group = 'Older'
    if (diff === 0) group = 'Today'
    else if (diff === 1) group = 'Yesterday'
    else if (diff < 7) group = 'Previous 7 Days'
    else if (diff < 30) group = 'Previous 30 Days'

    if (!acc[group]) acc[group] = []
    acc[group].push(session)
    return acc
  }, {} as Record<string, Session[]>)

  const groupOrder = ['Today', 'Yesterday', 'Previous 7 Days', 'Previous 30 Days', 'Older']

  return (
    <div className="flex flex-col h-full bg-slate-50/50">
      {/* Header */}
      <div className="p-4 border-b border-slate-100 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-purple-500 to-teal-400 flex items-center justify-center shadow-sm">
            <span className="text-white font-bold text-lg leading-none">S</span>
          </div>
          <span className="font-semibold text-slate-800 tracking-tight">SentiMind</span>
        </div>
        <button className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors">
          <Menu className="w-4 h-4" />
        </button>
      </div>

      {/* New Chat Button */}
      <div className="p-3 shrink-0">
        <button
          onClick={onNewSession}
          className="w-full flex items-center gap-2 px-4 py-2.5 bg-white border border-slate-200 rounded-xl text-sm font-medium text-slate-700 hover:border-purple-300 hover:text-purple-700 hover:shadow-sm transition-all active:scale-95 group"
        >
          <div className="p-1 bg-purple-50 rounded-md group-hover:bg-purple-100 transition-colors">
            <Plus className="w-4 h-4 text-purple-600" />
          </div>
          New Chat
        </button>
      </div>

      {/* Session List */}
      <div className="flex-1 overflow-y-auto px-3 pb-4 space-y-5 custom-scrollbar">
        {isLoading ? (
          <div className="flex flex-col gap-2 mt-4 px-2">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-12 bg-slate-100 rounded-xl animate-pulse" />
            ))}
          </div>
        ) : sessions.length === 0 ? (
          <div className="text-center mt-10 px-4">
            <div className="w-12 h-12 bg-slate-100 rounded-full flex items-center justify-center mx-auto mb-3">
              <MessageSquare className="w-5 h-5 text-slate-400" />
            </div>
            <p className="text-sm font-medium text-slate-600">No chats yet</p>
            <p className="text-xs text-slate-400 mt-1">Start a conversation to see your history here.</p>
          </div>
        ) : (
          groupOrder.map(group => {
            if (!grouped[group] || grouped[group].length === 0) return null
            return (
              <div key={group} className="animate-fade-in">
                <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2 px-2">
                  {group}
                </h3>
                <div className="space-y-0.5">
                  {grouped[group].map(session => (
                    <SessionItem
                      key={session.id}
                      session={session}
                      isActive={currentSessionId === session.id}
                      onSelect={() => onSelectSession(session.id)}
                      onDelete={() => onDeleteSession(session.id)}
                      onRename={(title) => onRenameSession(session.id, title)}
                    />
                  ))}
                </div>
              </div>
            )
          })
        )}
      </div>

      {/* User / Settings Footer */}
      <div className="p-3 border-t border-slate-100 shrink-0 bg-white">
        <button
          onClick={logout}
          className="w-full flex items-center justify-between p-2 hover:bg-slate-50 rounded-xl transition-colors group"
        >
          <div className="flex items-center gap-3 overflow-hidden">
            <div className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center shrink-0 border border-slate-200">
              <UserIcon className="w-4 h-4 text-slate-500" />
            </div>
            <div className="text-left overflow-hidden">
              <p className="text-sm font-semibold text-slate-700 truncate min-w-[100px]">Sign Out</p>
            </div>
          </div>
          <LogOut className="w-4 h-4 text-slate-400 group-hover:text-red-500 transition-colors" />
        </button>
      </div>
    </div>
  )
}
