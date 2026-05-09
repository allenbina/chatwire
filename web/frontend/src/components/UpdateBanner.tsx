/**
 * UpdateBanner — shows a dismissible top banner when a new chatwire version
 * is available. Handles two sources:
 *
 *   1. GitHub Releases API — new PyPI/chatwire server release available.
 *   2. PWA service-worker update — the Workbox `autoUpdate` SW installed a
 *      new version while the app was open; a page reload picks it up.
 *
 * Dismissal of the GitHub banner is persisted per version in localStorage.
 */
import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'

const DISMISSED_KEY = 'chatwire-dismissed-version'

function parseSemver(v: string): [number, number, number] {
  const parts = v.replace(/^v/, '').split('.').map(Number)
  return [parts[0] ?? 0, parts[1] ?? 0, parts[2] ?? 0]
}

function isNewer(latest: string, current: string): boolean {
  const [la, lb, lc] = parseSemver(latest)
  const [ca, cb, cc] = parseSemver(current)
  if (la !== ca) return la > ca
  if (lb !== cb) return lb > cb
  return lc > cc
}

export function UpdateBanner() {
  const dismissed = localStorage.getItem(DISMISSED_KEY)
  const [localDismiss, setLocalDismiss] = useState<string | null>(dismissed)
  // True when Workbox auto-updated the SW and a reload will activate it.
  const [swUpdated, setSwUpdated] = useState(false)

  // Listen for the Workbox controllerchange event that fires after autoUpdate
  // installs and activates a new service worker.
  useEffect(() => {
    if (!('serviceWorker' in navigator)) return
    const handler = () => setSwUpdated(true)
    navigator.serviceWorker.addEventListener('controllerchange', handler)
    return () => navigator.serviceWorker.removeEventListener('controllerchange', handler)
  }, [])

  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: () => fetch('/healthz').then((r) => r.json()),
    staleTime: 60_000,
  })

  const { data: release } = useQuery<{ tag_name?: string } | null>({
    queryKey: ['latest-release'],
    queryFn: () =>
      fetch('https://api.github.com/repos/allenbina/chatwire/releases/latest')
        .then((r) => r.ok ? r.json() : null)
        .catch(() => null),
    staleTime: 10 * 60_000,
    gcTime: 10 * 60_000,
  })

  // --- PWA SW update banner (higher priority) ---
  if (swUpdated) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="flex items-center justify-between px-4 py-2 text-sm
                   bg-[--color-accent] text-[--color-bg-primary]"
      >
        <span>App updated in background. Reload to activate the new version.</span>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="ml-4 flex-shrink-0 font-semibold underline hover:no-underline"
        >
          Reload
        </button>
      </div>
    )
  }

  // --- GitHub release banner ---
  const currentVersion: string = health?.release ?? health?.version ?? ''
  const latestVersion: string = release?.tag_name?.replace(/^v/, '') ?? ''

  if (
    !currentVersion ||
    !latestVersion ||
    !isNewer(latestVersion, currentVersion) ||
    localDismiss === latestVersion
  ) {
    return null
  }

  function dismiss() {
    localStorage.setItem(DISMISSED_KEY, latestVersion)
    setLocalDismiss(latestVersion)
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center justify-between px-4 py-2 text-sm
                 bg-[--color-warning] text-[--color-bg-primary]"
    >
      <span>
        chatwire v{latestVersion} is available (you have v{currentVersion}).{' '}
        <a
          href="https://github.com/allenbina/chatwire/releases"
          target="_blank"
          rel="noopener"
          className="underline font-medium"
        >
          See release notes
        </a>
      </span>
      <button
        type="button"
        onClick={dismiss}
        aria-label="Dismiss update notification"
        className="ml-4 flex-shrink-0 text-[--color-bg-primary] opacity-80 hover:opacity-100"
      >
        ✕
      </button>
    </div>
  )
}
