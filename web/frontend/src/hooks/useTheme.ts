/**
 * useTheme — reads, applies, and persists the active theme.
 *
 * Priority order for initial theme:
 *   1. localStorage key "chatwire-theme"
 *   2. Server setting from GET /api/ui/themes (fetched once on mount)
 *   3. Fall back to "dracula"
 *
 * Applying a theme sets --color-* CSS custom properties on :root so that
 * every component's var() references pick up the new values immediately.
 *
 * The "system" theme listens to prefers-color-scheme and re-applies when
 * the OS preference changes.
 */
import { useState, useEffect, useCallback } from 'react'
import { ALL_THEMES, THEME_MAP, resolveThemeColors, type ThemeDefinition } from '../themes'

const LS_KEY = 'chatwire-theme'

// ---------------------------------------------------------------------------
// Imperative helpers (usable outside React)
// ---------------------------------------------------------------------------

/** Apply a theme's CSS custom properties to :root. */
export function applyTheme(name: string): void {
  const theme = THEME_MAP[name]
  if (!theme) return
  const colors = resolveThemeColors(theme)
  const root = document.documentElement
  ;(Object.entries(colors) as [string, string][]).forEach(([key, value]) => {
    root.style.setProperty(`--color-${key}`, value)
  })
}

/** Persist the theme choice both in localStorage and on the server. */
export async function persistTheme(name: string): Promise<void> {
  localStorage.setItem(LS_KEY, name)
  try {
    const fd = new FormData()
    fd.append('theme', name)
    await fetch('/api/ui/themes', { method: 'POST', body: fd, credentials: 'same-origin' })
  } catch {
    // Best-effort — the local theme is already applied; server sync is non-blocking.
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useTheme() {
  const [current, setCurrent] = useState<string>(() => localStorage.getItem(LS_KEY) ?? 'dracula')
  const [loading, setLoading] = useState(true)

  // Initial load: apply from localStorage immediately, then reconcile with server.
  useEffect(() => {
    applyTheme(current)

    // Fetch server setting to reconcile (e.g. first visit, or setting changed on another device).
    fetch('/api/ui/themes', { credentials: 'same-origin' })
      .then((r) => r.json())
      .then((data: { themes: string[]; current: string }) => {
        const fromServer = data.current
        const fromLocal = localStorage.getItem(LS_KEY)
        // Local setting wins if it exists; otherwise adopt server setting.
        const effective = fromLocal ?? fromServer
        if (effective !== current) {
          setCurrent(effective)
          applyTheme(effective)
        }
      })
      .catch(() => {/* offline or unauthenticated — keep current */})
      .finally(() => setLoading(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // When "system" theme is active, re-apply whenever OS dark/light changes.
  useEffect(() => {
    if (current !== 'system') return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = () => applyTheme('system')
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [current])

  const setTheme = useCallback(async (name: string) => {
    setCurrent(name)
    applyTheme(name)
    await persistTheme(name)
  }, [])

  const themeDefinition: ThemeDefinition | undefined = THEME_MAP[current]

  return { current, themeDefinition, allThemes: ALL_THEMES, setTheme, loading }
}
