import React, { useState } from 'react'
import { Plus, Trash2, Edit2, Calendar, MessageSquare, Check, X, Loader } from 'lucide-react'

export default function SessionPanel({
  sessions,
  currentSessionId,
  onNewSession,
  onSelectSession,
  onDeleteSession,
  onRenameSession,
  isLoading
}) {
  const [editingId, setEditingId] = useState(null)
  const [editTitle, setEditTitle] = useState('')
  const [deletingId, setDeletingId] = useState(null)

  const handleRename = async (sessionId) => {
    if (!editTitle.trim()) {
      setEditingId(null)
      return
    }
    await onRenameSession(sessionId, editTitle)
    setEditingId(null)
    setEditTitle('')
  }

  const handleDelete = async (sessionId) => {
    await onDeleteSession(sessionId)
    setDeletingId(null)
  }

  const formatDate = (date) => {
    const d = new Date(date)
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  }

  return (
    <div className="flex flex-col h-full bg-gradient-to-b from-gray-50 to-white">
      {/* Header */}
      <div className="p-4 border-b border-gray-200 bg-white">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-gray-900">Conversations</h2>
          <button
            onClick={onNewSession}
            className="p-2 bg-gradient-to-br from-purple-500 to-teal-500 text-white rounded-lg hover:shadow-lg transition-all hover:scale-105 active:scale-95"
            title="New conversation"
          >
            <Plus className="w-5 h-5" />
          </button>
        </div>
        {isLoading && (
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <Loader className="w-4 h-4 animate-spin" />
            Loading sessions...
          </div>
        )}
      </div>

      {/* Sessions List */}
      <div className="flex-1 overflow-y-auto">
        {sessions.length === 0 ? (
          <div className="p-6 text-center text-gray-500">
            <MessageSquare className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p className="text-sm">No conversations yet</p>
            <p className="text-xs mt-2">Start chatting to create one!</p>
          </div>
        ) : (
          <div className="space-y-2 p-3">
            {sessions.map((session) => (
              <div
                key={session.id}
                className={`group relative p-3 rounded-lg transition-all cursor-pointer ${
                  currentSessionId === session.id
                    ? 'bg-gradient-to-r from-purple-100 to-teal-100 border-2 border-purple-300 shadow-md'
                    : 'bg-white border border-gray-200 hover:border-gray-300 hover:shadow-sm'
                }`}
                onClick={() => {
                  if (editingId !== session.id) {
                    onSelectSession(session.id)
                  }
                }}
              >
                {editingId === session.id ? (
                  // Edit mode
                  <div className="flex gap-2">
                    <input
                      autoFocus
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      onKeyPress={(e) => {
                        if (e.key === 'Enter') handleRename(session.id)
                      }}
                      className="flex-1 px-2 py-1 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
                      placeholder="Session title"
                    />
                    <button
                      onClick={() => handleRename(session.id)}
                      className="p-1 hover:bg-green-100 rounded transition-colors"
                    >
                      <Check className="w-4 h-4 text-green-600" />
                    </button>
                    <button
                      onClick={() => {
                        setEditingId(null)
                        setEditTitle('')
                      }}
                      className="p-1 hover:bg-gray-100 rounded transition-colors"
                    >
                      <X className="w-4 h-4 text-gray-600" />
                    </button>
                  </div>
                ) : (
                  // View mode
                  <>
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <p className="font-semibold text-gray-900 text-sm truncate">
                          {session.title || 'Untitled Session'}
                        </p>
                        <div className="flex items-center gap-2 mt-1">
                          <Calendar className="w-3 h-3 text-gray-400" />
                          <span className="text-xs text-gray-500">{formatDate(session.createdAt)}</span>
                        </div>
                      </div>
                      <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            setEditingId(session.id)
                            setEditTitle(session.title || '')
                          }}
                          className="p-1 hover:bg-blue-100 rounded transition-colors"
                          title="Rename"
                        >
                          <Edit2 className="w-4 h-4 text-blue-600" />
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            setDeletingId(session.id)
                          }}
                          className="p-1 hover:bg-red-100 rounded transition-colors"
                          title="Delete"
                        >
                          <Trash2 className="w-4 h-4 text-red-600" />
                        </button>
                      </div>
                    </div>

                    {/* Message count */}
                    <div className="mt-2 text-xs text-gray-400">
                      {session.messages?.length || 0} messages
                    </div>

                    {/* Delete confirmation */}
                    {deletingId === session.id && (
                      <div className="absolute inset-0 bg-red-50 rounded-lg border-2 border-red-300 flex items-center justify-center p-2 gap-2">
                        <p className="text-xs font-semibold text-red-700">Delete?</p>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            handleDelete(session.id)
                          }}
                          className="px-2 py-1 bg-red-500 text-white text-xs rounded hover:bg-red-600"
                        >
                          Yes
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            setDeletingId(null)
                          }}
                          className="px-2 py-1 bg-gray-300 text-gray-800 text-xs rounded hover:bg-gray-400"
                        >
                          No
                        </button>
                      </div>
                    )}
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
