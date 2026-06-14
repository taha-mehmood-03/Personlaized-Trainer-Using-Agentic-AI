'use client'

import React, { useState } from 'react'
import { MessageSquare, MoreVertical, Pencil, Trash2, Check, X } from 'lucide-react'
import { Session } from '@/types'
import { relativeDate } from '@/lib/utils'

interface SessionItemProps {
  session: Session
  isActive: boolean
  onSelect: () => void
  onDelete: () => void
  onRename: (title: string) => void
}

export function SessionItem({ session, isActive, onSelect, onDelete, onRename }: SessionItemProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [editTitle, setEditTitle] = useState(session.title)
  const [showOptions, setShowOptions] = useState(false)
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false)

  const handleSaveRename = (e?: React.FormEvent) => {
    e?.preventDefault()
    if (editTitle.trim() && editTitle !== session.title) {
      onRename(editTitle.trim())
    }
    setIsEditing(false)
    setShowOptions(false)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      setIsEditing(false)
      setEditTitle(session.title)
    }
  }

  // Edit Mode
  if (isEditing) {
    return (
      <div className={`group relative flex items-center gap-3 p-3 rounded-xl transition-all border ${
        isActive 
          ? 'bg-white border-cyan-200 shadow-sm ring-1 ring-cyan-100' 
          : 'hover:bg-white border-transparent hover:border-slate-200 hover:shadow-sm'
      }`}>
        <form onSubmit={handleSaveRename} className="flex-1 flex items-center gap-2">
          <input
            autoFocus
            type="text"
            value={editTitle}
            onChange={e => setEditTitle(e.target.value)}
            onKeyDown={handleKeyDown}
            onBlur={() => handleSaveRename()}
            className="w-full text-sm font-medium text-slate-800 bg-transparent border-b-2 border-cyan-500 focus:outline-none px-1 py-0.5"
          />
        </form>
      </div>
    )
  }

  // Delete Confirmation Mode
  if (isConfirmingDelete) {
    return (
      <div className="flex items-center justify-between p-3 rounded-xl bg-red-50 border border-red-100">
        <span className="text-xs font-semibold text-red-600">Delete chat?</span>
        <div className="flex gap-1">
          <button 
            onClick={() => { onDelete(); setIsConfirmingDelete(false) }}
            className="p-1.5 hover:bg-red-100 rounded-md text-red-700 transition-colors"
          >
            <Check className="w-3.5 h-3.5" />
          </button>
          <button 
            onClick={() => setIsConfirmingDelete(false)}
            className="p-1.5 hover:bg-red-100 rounded-md text-red-700 transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    )
  }

  // Normal Display Mode
  return (
    <div 
      className={`group relative flex cursor-pointer flex-col gap-1 rounded-xl border p-3 transition-all ${
        isActive 
          ? 'border-slate-900 bg-slate-900 text-white shadow-sm' 
          : 'border-transparent hover:border-slate-200 hover:bg-slate-50'
      }`}
      onClick={onSelect}
      onMouseLeave={() => setShowOptions(false)}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 overflow-hidden flex-1">
          <div className={`p-1.5 rounded-lg shrink-0 ${isActive ? 'bg-white/10 text-white' : 'bg-slate-100 text-slate-500 group-hover:bg-slate-200'}`}>
            <MessageSquare className="w-3.5 h-3.5" />
          </div>
          <p className={`text-sm font-semibold truncate ${isActive ? 'text-white' : 'text-slate-700'}`}>
            {session.title}
          </p>
        </div>

        {/* Options Menu Toggle */}
        <div className="relative shrink-0">
          <button
            onClick={(e) => { e.stopPropagation(); setShowOptions(!showOptions) }}
            className={`p-1 rounded-md transition-colors ${
              showOptions || isActive ? 'text-slate-300 hover:bg-white/10 hover:text-white' : 'text-transparent group-hover:text-slate-400 hover:text-slate-800'
            }`}
          >
            <MoreVertical className="w-4 h-4" />
          </button>

          {/* Dropdown Options */}
          {showOptions && (
            <div className="absolute right-0 top-full mt-1 w-32 bg-white rounded-lg shadow-lg border border-slate-200 py-1 z-50 animate-fade-in origin-top-right">
              <button
                onClick={(e) => { e.stopPropagation(); setIsEditing(true); setShowOptions(false) }}
                className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50 hover:text-slate-900 transition-colors"
              >
                <Pencil className="w-3 h-3" /> Rename
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); setIsConfirmingDelete(true); setShowOptions(false) }}
                className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-red-600 hover:bg-red-50 transition-colors"
              >
                <Trash2 className="w-3 h-3" /> Delete
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between mt-1 pl-8 pr-1 opacity-70">
        <p className={`text-[10px] font-medium ${isActive ? 'text-white/60' : 'text-slate-400'}`}>
          {relativeDate(session.updatedAt ?? session.createdAt)}
        </p>
      </div>
    </div>
  )
}
