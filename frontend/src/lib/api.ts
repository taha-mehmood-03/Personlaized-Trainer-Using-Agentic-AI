// ─── Central API client ─────────────────────────────────────────────────────
// Wraps all backend calls in one place. Import the helpers from
// server actions files; this module is safe for both server and browser.

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api'
export const SERVER_API_BASE =
    process.env.API_URL ??
    process.env.BACKEND_API_URL ??
    API_BASE

export interface ApiResponse<T = unknown> {
    data: T | null
    error: string | null
    ok: boolean
}

type ApiRequestInit = RequestInit & {
    timeoutMs?: number
}

const DEFAULT_API_TIMEOUT_MS = 10000

// Crisis-related types
export interface CrisisResource {
    primary_hotline?: {
        name: string
        number: string
        available: string
        call_text?: string
        language?: string
    }
    secondary_hotline?: {
        name: string
        number: string
        available: string
        call_text?: string
        language?: string
    }
    tertiary_hotline?: {
        name: string
        number: string
        available: string
        call_text?: string
    }
    emergency_service?: {
        name: string
        number: string
        available: string
        call_text?: string
    }
    text_line?: {
        name: string
        action: string
        available: string
        supported?: boolean
    }
    international?: {
        name: string
        website: string
    }
    message?: string
    disclaimer?: {
        text: string
    }
}

export interface CrisisResourcesResponse {
    success: boolean
    country_code: string
    resources: CrisisResource
    user_id?: string
}

export interface CountryDetectionResponse {
    success: boolean
    country_code: string
    detected_from: string
}

export interface CrisisCallResponse {
    success: boolean
    call_sid?: string
    message: string
    error?: string
    user_id?: string
}

/** Generic fetch wrapper with consistent error handling. */
export async function apiRequest<T>(
    path: string,
    options?: ApiRequestInit
): Promise<ApiResponse<T>> {
    const { timeoutMs = DEFAULT_API_TIMEOUT_MS, ...fetchOptions } = options ?? {}
    const controller = new AbortController()
    const timeout = timeoutMs > 0
        ? setTimeout(() => controller.abort(), timeoutMs)
        : null

    try {
        const headers = {
            'Content-Type': 'application/json',
            ...((fetchOptions.headers ?? {}) as Record<string, string>),
        }
        const baseUrl = typeof window === 'undefined' ? SERVER_API_BASE : API_BASE
        const res = await fetch(`${baseUrl}${path}`, {
            ...fetchOptions,
            headers,
            cache: fetchOptions.cache ?? 'no-store',
            signal: fetchOptions.signal ?? controller.signal,
        })

        if (!res.ok) {
            const text = await res.text().catch(() => res.statusText)
            return { data: null, error: text, ok: false }
        }

        const data: T = await res.json()
        return { data, error: null, ok: true }
    } catch (err) {
        const message = err instanceof Error && err.name === 'AbortError'
            ? `Request timed out after ${timeoutMs}ms`
            : err instanceof Error ? err.message : 'Network error'
        return { data: null, error: message, ok: false }
    } finally {
        if (timeout) clearTimeout(timeout)
    }
}

/** Convenience wrappers */
export const api = {
    get: <T>(path: string, init?: ApiRequestInit) =>
        apiRequest<T>(path, { method: 'GET', ...init }),

    post: <T>(path: string, body: unknown, init?: ApiRequestInit) =>
        apiRequest<T>(path, {
            method: 'POST',
            body: JSON.stringify(body),
            ...init,
        }),

    patch: <T>(path: string, body: unknown, init?: ApiRequestInit) =>
        apiRequest<T>(path, { method: 'PATCH', body: JSON.stringify(body), ...init }),

    delete: <T>(path: string, init?: ApiRequestInit) =>
        apiRequest<T>(path, { method: 'DELETE', ...init }),
}

export function userScopeHeader(userId: string): HeadersInit {
    return { 'X-SentiMind-User-Id': userId }
}
