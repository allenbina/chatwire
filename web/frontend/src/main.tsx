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

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
