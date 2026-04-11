import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** Merge Tailwind class names safely (clsx + tailwind-merge). */
export function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs))
}

/** Format a date string to a human-readable relative label. */
export function relativeDate(date: string | Date): string {
    const d = new Date(date)
    const now = new Date()
    const diff = Math.floor((now.getTime() - d.getTime()) / 86400000)
    if (diff === 0) return 'Today'
    if (diff === 1) return 'Yesterday'
    if (diff < 7) return d.toLocaleDateString('en-US', { weekday: 'long' })
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

/** Format time portion of a date string, e.g. "10:42 AM". */
export function formatTime(ts?: string): string {
    if (!ts) return ''
    const d = new Date(ts)
    return isNaN(d.getTime())
        ? ''
        : d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
}

/** Clamp a number between min and max. */
export function clamp(val: number, min: number, max: number) {
    return Math.min(max, Math.max(min, val))
}
