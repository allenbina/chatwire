/**
 * usePinnedSettings — manages which settings toggles are pinned to the
 * sidebar footer.  Pinned state lives in localStorage so it survives
 * page reloads without a round-trip to the server.
 *
 * Pinnable keys:
 *   "hiatus_enabled"   — Notifications hiatus mode (PauseCircle icon)
 *   "reminder_enabled" — Daily reminder timer (Bell icon)
 */
import { useState, useCallback } from 'react'

const LS_KEY = 'chatwire-pinned-settings'

export type PinnableKey = 'hiatus_enabled' | 'reminder_enabled'

/** Human-readable label for each pinnable key (used for aria-label / title). */
export const PINNABLE_LABELS: Record<PinnableKey, string> = {
  hiatus_enabled: 'Hiatus',
  reminder_enabled: 'Reminder',
}

function load(): PinnableKey[] {
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as PinnableKey[]) : []
  } catch {
    return []
  }
}

export function usePinnedSettings() {
  const [pinnedKeys, setPinnedKeys] = useState<PinnableKey[]>(load)

  const togglePin = useCallback((key: PinnableKey) => {
    setPinnedKeys((prev) => {
      const next = prev.includes(key)
        ? prev.filter((k) => k !== key)
        : [...prev, key]
      localStorage.setItem(LS_KEY, JSON.stringify(next))
      return next
    })
  }, [])

  const isPinned = useCallback(
    (key: PinnableKey) => pinnedKeys.includes(key),
    [pinnedKeys],
  )

  return { pinnedKeys, togglePin, isPinned }
}
