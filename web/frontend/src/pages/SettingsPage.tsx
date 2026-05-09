/**
 * Settings panel — theme switcher + links to the full Jinja2 settings page.
 *
 * The theme list comes from /api/ui/themes. Changing the theme posts to the
 * existing /api/settings/theme endpoint (same as the Jinja2 UI) so the
 * server-side config is updated. The page reloads to apply the new theme CSS.
 *
 * This is a minimal Phase 2 implementation. Full settings parity (plugin
 * manager, export, push notifications) is planned for Phase 3.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { fetchThemes } from '../api'
import { Layout } from '../components/Layout'

function ThemeButton({
  name,
  active,
  onClick,
}: {
  name: string
  active: boolean
  onClick: () => void
}) {
  const label = name
    .replace(/-/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())

  return (
    <button
      onClick={onClick}
      className={[
        'px-4 py-2 rounded-lg text-sm border transition-colors',
        active
          ? 'border-[--color-accent] bg-[--color-accent] text-[--color-bg-primary] font-semibold'
          : 'border-[--color-border] text-[--color-text-secondary] hover:border-[--color-accent] hover:text-[--color-text-primary]',
      ].join(' ')}
    >
      {label}
    </button>
  )
}

export function SettingsPage() {
  const navigate = useNavigate()
  const [applying, setApplying] = useState(false)
  const [feedback, setFeedback] = useState<string | null>(null)

  const { data } = useQuery({
    queryKey: ['themes'],
    queryFn: fetchThemes,
    staleTime: 60_000,
  })

  const themes = data?.themes ?? []
  const currentTheme = data?.current ?? 'dracula'

  async function applyTheme(theme: string) {
    if (applying) return
    setApplying(true)
    setFeedback(null)
    try {
      const fd = new FormData()
      fd.append('theme', theme)
      const res = await fetch('/api/settings/theme', { method: 'POST', body: fd, credentials: 'same-origin' })
      if (!res.ok) throw new Error(`${res.status}`)
      // Reload so the new theme CSS (served by Jinja2) takes effect.
      window.location.reload()
    } catch (err) {
      setFeedback(`Failed to apply theme: ${err instanceof Error ? err.message : err}`)
    } finally {
      setApplying(false)
    }
  }

  return (
    <Layout>
      <div className="flex-1 overflow-y-auto p-6 max-w-2xl mx-auto w-full">
        {/* Header */}
        <div className="flex items-center gap-4 mb-6">
          <button
            onClick={() => navigate(-1)}
            className="text-[--color-text-muted] hover:text-[--color-accent] transition-colors text-sm"
            aria-label="Go back"
          >
            &#8592; Back
          </button>
          <h1 className="text-xl font-semibold text-[--color-text-primary]">Settings</h1>
        </div>

        {/* Theme picker */}
        <section className="mb-8">
          <h2 className="text-base font-semibold text-[--color-text-primary] mb-3">Theme</h2>
          {themes.length === 0 ? (
            <p className="text-sm text-[--color-text-muted]">Loading themes&hellip;</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {themes.map((t) => (
                <ThemeButton
                  key={t}
                  name={t}
                  active={t === currentTheme}
                  onClick={() => applyTheme(t)}
                />
              ))}
            </div>
          )}
          {feedback && <p className="mt-2 text-sm text-[--color-error]">{feedback}</p>}
          {applying && <p className="mt-2 text-sm text-[--color-text-muted] animate-pulse">Applying&hellip;</p>}
        </section>

        {/* Link to full settings */}
        <section className="border-t border-[--color-border] pt-6">
          <h2 className="text-base font-semibold text-[--color-text-primary] mb-3">Advanced Settings</h2>
          <p className="text-sm text-[--color-text-muted] mb-3">
            Plugin management, push notifications, export, and more are available in the full settings page.
          </p>
          <a
            href="/settings"
            className="inline-block px-4 py-2 rounded-lg border border-[--color-border]
                       text-sm text-[--color-text-secondary] hover:border-[--color-accent]
                       hover:text-[--color-accent] transition-colors"
          >
            Open full settings &rarr;
          </a>
        </section>

        {/* Version info */}
        <section className="border-t border-[--color-border] pt-6 mt-6">
          <VersionInfo />
        </section>
      </div>
    </Layout>
  )
}

function VersionInfo() {
  const { data } = useQuery({
    queryKey: ['health'],
    queryFn: () => fetch('/healthz').then((r) => r.json()),
    staleTime: 30_000,
  })
  if (!data) return null
  return (
    <p className="text-xs text-[--color-text-muted]">
      Chatwire {data.release ?? data.version ?? ''}
    </p>
  )
}
