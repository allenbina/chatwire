/**
 * Full-screen lockout overlay — shown when the anti-spam fuse is at step 4+.
 *
 * Steps 4-5: display a live countdown until the cooldown expires.
 * Step 6 (permanent): show the machine-bound CW code, a link to the unlock
 *   request form, and a text input for the admin-issued UL unlock code.
 *
 * The Google Form URL is read from window.__CHATWIRE_UNLOCK_FORM_URL__ (set
 * by the server for self-hosters) or falls back to UNLOCK_FORM_FALLBACK.
 * Chunk 5 will populate the real production URL.
 */
import { useState, useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { getFuseStatus, postUnlock, type FuseStatus } from '../api'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const UNLOCK_FORM_FALLBACK = 'https://chatwireapp.com/unlock'

function getUnlockFormUrl(fromApi?: string | null): string {
  // Priority: API config → window injection → hard-coded fallback
  if (fromApi) return fromApi
  return (
    (window as Window & { __CHATWIRE_UNLOCK_FORM_URL__?: string })
      .__CHATWIRE_UNLOCK_FORM_URL__ ?? UNLOCK_FORM_FALLBACK
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatHMS(totalSeconds: number): string {
  const h = Math.floor(totalSeconds / 3600)
  const m = Math.floor((totalSeconds % 3600) / 60)
  const s = totalSeconds % 60
  return [h, m, s].map((n) => String(n).padStart(2, '0')).join(':')
}

// ---------------------------------------------------------------------------
// Favicon SVG logo (inline — avoids network round-trip)
// ---------------------------------------------------------------------------

function ChatwireLogo() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 32 32"
      className="w-14 h-14 mx-auto"
      aria-hidden="true"
    >
      <rect width="32" height="32" rx="7" fill="#bd93f9" />
      <text
        x="16"
        y="23"
        textAnchor="middle"
        fontFamily="Inter, system-ui, sans-serif"
        fontWeight="700"
        fontSize="22"
        fill="#282a36"
      >
        c
      </text>
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface LockoutOverlayProps {
  fuseStatus: FuseStatus
}

export function LockoutOverlay({ fuseStatus }: LockoutOverlayProps) {
  const qc = useQueryClient()
  const [countdown, setCountdown] = useState<number | null>(null)
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // Sync countdown from fuse status (steps 4-5 with timed cooldown)
  useEffect(() => {
    if (
      fuseStatus.step >= 4 &&
      fuseStatus.step <= 5 &&
      fuseStatus.cooldown_remaining_s != null
    ) {
      setCountdown(Math.ceil(fuseStatus.cooldown_remaining_s))
    } else {
      setCountdown(null)
    }
  }, [fuseStatus])

  // Tick down; re-fetch status when it reaches zero
  useEffect(() => {
    if (countdown == null) return
    if (countdown <= 0) {
      qc.invalidateQueries({ queryKey: ['fuse-status'] })
      return
    }
    const t = setTimeout(
      () => setCountdown((c) => (c != null ? c - 1 : null)),
      1000,
    )
    return () => clearTimeout(t)
  }, [countdown, qc])

  async function handleUnlock() {
    const trimmed = code.trim()
    if (!trimmed || submitting) return
    setSubmitting(true)
    setError('')
    try {
      await postUnlock(trimmed)
      await qc.invalidateQueries({ queryKey: ['fuse-status'] })
    } catch {
      setError('Invalid code')
    } finally {
      setSubmitting(false)
    }
  }

  const isPermanent = fuseStatus.step >= 6

  return (
    <div
      className="flex-1 flex items-center justify-center bg-background"
      data-testid="lockout-overlay"
    >
      <div className="max-w-sm w-full mx-auto px-6 text-center space-y-6">
        {/* Logo */}
        <ChatwireLogo />

        {/* Heading */}
        <div className="space-y-3">
          <h2 className="text-lg font-semibold text-foreground">
            Outbound messaging is locked.
          </h2>
          <p className="text-sm text-muted-foreground leading-relaxed">
            Chatwire was made to help you stay connected with the people you
            care about — not for bulk or automated messaging.
          </p>
          <p className="text-sm text-muted-foreground">
            If this was a mistake, we'd love to help.
          </p>
        </div>

        {/* Steps 4-5: countdown */}
        {!isPermanent && countdown != null && countdown > 0 && (
          <div className="rounded-lg border border-border bg-card px-4 py-3">
            <p className="text-xs text-muted-foreground mb-1">Resumes in</p>
            <p className="text-2xl font-mono font-semibold text-foreground tabular-nums">
              {formatHMS(countdown)}
            </p>
          </div>
        )}

        {/* Step 6: permanent lockout — unlock flow */}
        {isPermanent && (
          <div className="space-y-4">
            {/* Machine-bound CW code */}
            {fuseStatus.unlock_code && (
              <div className="rounded-lg border border-border bg-card px-4 py-3 text-left">
                <p className="text-xs text-muted-foreground mb-1">Your unlock code</p>
                <p className="font-mono text-base font-semibold text-foreground select-all">
                  {fuseStatus.unlock_code}
                </p>
              </div>
            )}

            {/* Request form link */}
            <a
              href={getUnlockFormUrl(fuseStatus.unlock_form_url)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block w-full rounded-lg border border-primary/40 bg-primary/10
                         px-4 py-2.5 text-sm font-medium text-primary
                         hover:bg-primary/20 transition-colors"
            >
              Request unlock →
            </a>

            {/* Unlock code input */}
            <div className="space-y-2">
              <label
                htmlFor="unlock-code-input"
                className="block text-xs text-muted-foreground text-left"
              >
                Paste your unlock code (UL-XXXX-XXXX)
              </label>
              <input
                id="unlock-code-input"
                type="text"
                value={code}
                onChange={(e) => {
                  setCode(e.target.value)
                  setError('')
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleUnlock()
                }}
                placeholder="UL-XXXX-XXXX"
                disabled={submitting}
                className="w-full rounded-lg border border-border bg-input px-3 py-2 text-sm
                           font-mono text-foreground placeholder:text-muted-foreground
                           focus:outline-none focus:ring-2 focus:ring-primary
                           disabled:opacity-50"
                aria-label="Paste your unlock code"
              />
              {error && (
                <p className="text-xs text-destructive text-left">{error}</p>
              )}
              <Button
                onClick={handleUnlock}
                disabled={!code.trim() || submitting}
                className="w-full"
              >
                {submitting ? 'Verifying…' : 'Unlock'}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Hook — used by ChatPage to check whether lockout is active
// ---------------------------------------------------------------------------

export { getFuseStatus }
