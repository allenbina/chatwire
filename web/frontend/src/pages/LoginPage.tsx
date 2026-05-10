/**
 * LoginPage — React replacement for the Jinja2 _login.html template.
 *
 * Rendered at /login (React Router route "/login", basename "/app").
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
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export function LoginPage() {
  const [searchParams] = useSearchParams()
  const nextParam = searchParams.get('next') || '/'

  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)

  const inputRef = useRef<HTMLInputElement>(null)
  useEffect(() => { inputRef.current?.focus() }, [])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (busy) return
    setBusy(true)

    try {
      const resp = await fetch('/api/ui/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password, next: nextParam }),
      })

      if (resp.ok) {
        const data = await resp.json()
        window.location.href = data.next || '/'
        return
      }

      let msg = 'Sign in failed.'
      try {
        const data = await resp.json()
        msg = data.detail ?? msg
      } catch {
        // non-JSON error body — use default message
      }
      toast.error(msg)
    } catch {
      toast.error('Network error — please try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center bg-background"
    >
      <div
        className="rounded-[var(--radius)] shadow-[var(--shadow-card)] w-full max-w-sm mx-4 p-8
                   bg-card border border-border"
      >
        <h1 className="text-2xl font-bold mb-1 text-foreground">
          iMessage bridge
        </h1>
        <p className="text-sm mb-6 text-muted-foreground">
          Sign in to continue.
        </p>

        <form onSubmit={handleSubmit} autoComplete="on">
          <label
            htmlFor="password"
            className="block text-sm font-medium mb-2 text-foreground"
          >
            Password
          </label>
          <Input
            ref={inputRef}
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mb-5 bg-background border-border text-foreground
                       focus-visible:ring-ring"
          />
          <Button
            type="submit"
            disabled={busy}
            className="w-full"
          >
            {busy ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>
      </div>
    </div>
  )
}
