'use client'

import { useEffect } from 'react'
import type { ReactNode } from 'react'

export type ThemePreference = 'light' | 'dark' | 'system'

export const THEME_STORAGE_KEY = 'sentimind-theme'

function isThemePreference(value: string | null): value is ThemePreference {
  return value === 'light' || value === 'dark' || value === 'system'
}

function systemPrefersDark() {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
}

export function resolveThemePreference(preference: ThemePreference) {
  return preference === 'system' ? (systemPrefersDark() ? 'dark' : 'light') : preference
}

export function applyThemePreference(preference: ThemePreference) {
  if (typeof window === 'undefined') return

  const resolved = resolveThemePreference(preference)
  const root = document.documentElement
  root.dataset.theme = resolved
  root.dataset.themePreference = preference
  root.classList.toggle('dark', resolved === 'dark')

  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, preference)
  } catch {
    // Storage can be unavailable in private contexts; the DOM theme still applies.
  }

  const themeColor = resolved === 'dark' ? '#08111f' : '#f8fafc'
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', themeColor)
}

function storedThemePreference(): ThemePreference {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY)
    return isThemePreference(stored) ? stored : 'system'
  } catch {
    return 'system'
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  useEffect(() => {
    const applyStored = () => applyThemePreference(storedThemePreference())
    const media = window.matchMedia?.('(prefers-color-scheme: dark)')

    applyStored()
    media?.addEventListener('change', applyStored)
    window.addEventListener('storage', applyStored)

    return () => {
      media?.removeEventListener('change', applyStored)
      window.removeEventListener('storage', applyStored)
    }
  }, [])

  return children
}
