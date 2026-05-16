import React, { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import ReactDOM from 'react-dom'
import './index.css'
import App from './App.tsx'
import { registerSlot } from './plugins/registry.ts'
import { applyDecorations, loadStoredDecorations, restoreThemePack, restorePluginThemes } from './hooks/useTheme.ts'

// Apply persisted color scheme + structural style before first render to avoid FOUC.
document.documentElement.setAttribute(
  'data-theme',
  localStorage.getItem('chatwire-theme') ?? 'dracula',
)
document.documentElement.setAttribute(
  'data-style',
  localStorage.getItem('chatwire-style') ?? 'default',
)

// Restore persisted decoration overrides (no FOUC risk — CSS vars resolve immediately).
applyDecorations(loadStoredDecorations())

// Restore persisted theme pack (async — fetches CSS from server).
restoreThemePack()

// Inject CSS contributed by installed theme plugins (async — avoids FOUC for plugin schemes).
restorePluginThemes()

// ---------------------------------------------------------------------------
// Built-in plugin registrations (lazy — not in the main bundle)
// StatsWidget fetches /api/ui/stats and renders nothing when disabled.
// ---------------------------------------------------------------------------
import('./plugins/StatsWidget.tsx').then(({ StatsWidget }) => {
  registerSlot('sidebar.panel', StatsWidget, { key: 'stats-widget' })
})

// Conditionally load axe-core in development for a11y warnings in the console.
if (import.meta.env.DEV) {
  import('@axe-core/react').then(({ default: axe }) => {
    axe(React, ReactDOM, 1000)
  }).catch(() => {/* axe not available — safe to ignore */})
}

// ---------------------------------------------------------------------------
// Cache retention sweep — prune cached thumbnails/avatars older than the
// user's chosen retention period (localStorage 'chatwire-cache-max-age-days').
// Runs once on startup, non-blocking.
// ---------------------------------------------------------------------------
if ('caches' in window) {
  const maxDays = parseInt(localStorage.getItem('chatwire-cache-max-age-days') ?? '30', 10)
  if (maxDays > 0) {
    const cutoff = Date.now() - maxDays * 86_400_000
    for (const name of ['thumb-cache', 'avatar-cache']) {
      caches.open(name).then(async (cache) => {
        for (const req of await cache.keys()) {
          const resp = await cache.match(req)
          if (!resp) continue
          const dateStr = resp.headers.get('date')
          if (dateStr && new Date(dateStr).getTime() < cutoff) {
            cache.delete(req)
          }
        }
      }).catch(() => {/* cache doesn't exist yet */})
    }
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
