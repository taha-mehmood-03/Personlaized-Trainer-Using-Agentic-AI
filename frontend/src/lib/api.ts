// ─── Central API client ─────────────────────────────────────────────────────
// Wraps all backend calls in one place. Import the helpers from
// server actions files; this module is safe for both server and browser.

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api'

export interface ApiResponse<T = unknown> {
    data: T | null
    error: string | null
    ok: boolean
}

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
    options?: RequestInit
): Promise<ApiResponse<T>> {
    try {
        const res = await fetch(`${API_BASE}${path}`, {
            headers: { 'Content-Type': 'application/json' },
            cache: 'no-store',
            ...options,
        })

        if (!res.ok) {
            const text = await res.text().catch(() => res.statusText)
            return { data: null, error: text, ok: false }
        }

        const data: T = await res.json()
        return { data, error: null, ok: true }
    } catch (err) {
        const message = err instanceof Error ? err.message : 'Network error'
        return { data: null, error: message, ok: false }
    }
}

/** Convenience wrappers */
export const api = {
    get: <T>(path: string, init?: RequestInit) =>
        apiRequest<T>(path, { method: 'GET', ...init }),

    post: <T>(path: string, body: unknown, init?: RequestInit) =>
        apiRequest<T>(path, {
            method: 'POST',
            body: JSON.stringify(body),
            ...init,
        }),

    patch: <T>(path: string, body: unknown) =>
        apiRequest<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),

    delete: <T>(path: string) =>
        apiRequest<T>(path, { method: 'DELETE' }),
}
