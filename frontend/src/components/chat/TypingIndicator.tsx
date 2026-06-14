/**
 * Typing Indicator Component
 * Shows animated dots while the assistant is generating a response
 * Smooth animation matching ChatGPT-like experience
 */

'use client'

import React from 'react'

interface TypingIndicatorProps {
    /**
     * Optional custom message to display before the dots
     * Default: "Assistant is typing"
     */
    message?: string

    /**
     * Custom styling className
     */
    className?: string
}

export function TypingIndicator({ message = 'Thinking', className = '' }: TypingIndicatorProps) {
    return (
        <div className={`flex items-center gap-3 py-2 ${className}`}>
            <div className="flex items-center gap-2 bg-white/70 backdrop-blur-md border border-white/50 shadow-soft px-4 py-2.5 rounded-2xl">
                <span className="text-sm font-medium text-slate-700">{message}</span>
                <div className="flex gap-1.5 ml-1">
                    <span
                        className="w-1.5 h-1.5 rounded-full bg-emerald-brand shadow-glow animate-bounce-gentle"
                        style={{ animationDelay: '0s' }}
                    />
                    <span
                        className="w-1.5 h-1.5 rounded-full bg-cyan-brand shadow-glow animate-bounce-gentle"
                        style={{ animationDelay: '0.2s' }}
                    />
                    <span
                        className="w-1.5 h-1.5 rounded-full bg-emerald-brand shadow-glow animate-bounce-gentle"
                        style={{ animationDelay: '0.4s' }}
                    />
                </div>
            </div>
        </div>
    )
}
