'use client'

import { useState, useRef, KeyboardEvent } from 'react'
import { Send, Mic, MicOff, Loader } from 'lucide-react'

interface ChatInputProps {
  isLoading: boolean
  isRecording: boolean
  onSend: (text: string) => void
  onStartRecording: () => void
  onStopRecording: () => void
}

export function ChatInput({
  isLoading,
  isRecording,
  onSend,
  onStartRecording,
  onStopRecording,
}: ChatInputProps) {
  const [input, setInput] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSend = () => {
    const text = input.trim()
    if (!text || isLoading) return
    onSend(text)
    setInput('')
    // Reset textarea height
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleInput = () => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }

  return (
    <div className="bg-white border-t border-gray-100 px-5 py-4 shrink-0">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-end gap-3">
          {/* Textarea */}
          <div className="flex-1 relative">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              onInput={handleInput}
              placeholder="Type your thoughts here..."
              rows={1}
              className="w-full resize-none px-4 py-3 pr-4 text-sm text-gray-800 placeholder-gray-400 bg-gray-50 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-purple-300 focus:border-purple-300 transition-all"
              style={{ minHeight: '48px', maxHeight: '160px' }}
              disabled={isRecording}
            />
          </div>

          {/* Mic button */}
          <button
            onClick={isRecording ? onStopRecording : onStartRecording}
            disabled={isLoading}
            title={isRecording ? 'Stop recording' : 'Voice message'}
            className={`p-3 rounded-xl transition-all shrink-0 ${
              isRecording
                ? 'bg-red-500 text-white shadow-lg shadow-red-500/40 animate-pulse'
                : 'bg-cyan-500 text-white hover:bg-cyan-600 hover:shadow-lg disabled:opacity-50'
            }`}
          >
            {isRecording ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
          </button>

          {/* Send button */}
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            title="Send (Enter)"
            className="p-3 rounded-xl bg-gradient-to-br from-purple-600 to-purple-500 text-white hover:shadow-lg hover:shadow-purple-500/30 disabled:opacity-40 disabled:cursor-not-allowed transition-all hover:scale-105 active:scale-95 shrink-0"
          >
            {isLoading ? (
              <Loader className="w-5 h-5 animate-spin" />
            ) : (
              <Send className="w-5 h-5" />
            )}
          </button>
        </div>

        {/* Disclaimer */}
        <p className="text-center text-[11px] text-gray-400 mt-2.5">
          SentiMind AI is a supportive companion and not a replacement for professional clinical help.
          In emergencies, please contact crisis services.
        </p>
      </div>
    </div>
  )
}
