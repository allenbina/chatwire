/**
 * Returns true when the browser is online, false when offline.
 * Tracks window 'online' / 'offline' events.
 */
import { useState, useEffect } from 'react'

export function useOnline(): boolean {
  const [online, setOnline] = useState(() => navigator.onLine)
  useEffect(() => {
    const set = () => setOnline(navigator.onLine)
    window.addEventListener('online', set)
    window.addEventListener('offline', set)
    return () => {
      window.removeEventListener('online', set)
      window.removeEventListener('offline', set)
    }
  }, [])
  return online
}
