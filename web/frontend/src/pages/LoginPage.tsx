/**
 * LoginPage — React replacement for the Jinja2 _login.html template.
 *
 * Rendered at /app/login (React Router route "/login", basename "/app").
 * The auth-gate middleware in main.py redirects unauthenticated requests
 * here with an optional ?next= param; on success we follow it.
 *
 * POST /api/ui/auth/login (public path, no cookie required)
 *   Body: { password, next }
 *   200:  { ok: true, next: string }  →  follow `next`
 *   403:  wrong password
 *   429:  rate-limited (message in detail)
 */
import { useState, useRef, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'

export function LoginPage() {
  const [searchParams] = useSearchParams()
  const nextParam = searchParams.get('next') || '/app/'

  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const inputRef = useRef<HTMLInputElement>(null)
  useEffect(() => { inputRef.current?.focus() }, [])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')

    try {
      const resp = await fetch('/api/ui/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password, next: nextParam }),
      })

      if (resp.ok) {
        const data = await resp.json()
        // Hard navigate so the browser picks up the new session cookie for
        // subsequent HTML requests (the SPA's fetch calls already carry it
        // via the browser's cookie jar after this response).
        window.location.href = data.next || '/app/'
        return
      }

      let msg = 'Sign in failed.'
      try {
        const data = await resp.json()
        msg = data.detail ?? msg
      } catch {
        // non-JSON error body — use default message
      }
      setError(msg)
    } catch {
      setError('Network error — please try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center"
      style={{ backgroundColor: 'var(--color-bg-primary)' }}
    >
      <div
        className="rounded-xl shadow-lg w-full max-w-sm mx-4 p-8"
        style={{
          backgroundColor: 'var(--color-bg-secondary)',
          border: '1px solid var(--color-border)',
        }}
      >
        <h1
          className="text-2xl font-bold mb-1"
          style={{ color: 'var(--color-text-primary)' }}
        >
          iMessage bridge
        </h1>
        <p className="text-sm mb-6" style={{ color: 'var(--color-text-muted)' }}>
          Sign in to continue.
        </p>

        {error && (
          <div
            role="alert"
            className="text-sm rounded-lg p-3 mb-4"
            style={{
              backgroundColor: 'var(--color-error-bg, #fee2e2)',
              border: '1px solid var(--color-error-border, #fca5a5)',
              color: 'var(--color-error, #dc2626)',
            }}
          >
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} autoComplete="on">
          <label
            htmlFor="password"
            className="block text-sm font-medium mb-2"
            style={{ color: 'var(--color-text-primary)' }}
          >
            Password
          </label>
          <input
            ref={inputRef}
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-lg px-3 py-2.5 text-sm mb-5 outline-none
                       focus:ring-2 focus:ring-[--color-accent]"
            style={{
              backgroundColor: 'var(--color-bg-tertiary)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-text-primary)',
            }}
          />
          <button
            type="submit"
            disabled={busy}
            className="w-full py-2.5 rounded-lg text-sm font-medium transition-colors
                       disabled:opacity-50"
            style={{
              backgroundColor: 'var(--color-accent)',
              color: 'var(--color-on-accent, #fff)',
            }}
          >
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}
