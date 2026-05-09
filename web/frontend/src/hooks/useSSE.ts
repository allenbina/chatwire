/**
 * Subscribes to the /events SSE stream and calls `onEvent` for each
 * parsed JSON payload. Automatically reconnects on connection drop.
 *
 * Returns a cleanup function (also called on unmount).
 */
import { useEffect, useRef } from 'react'

export interface SSEEvent {
  handle?: string
  name?: string
  rowid?: number
  text?: string
  from_me?: boolean
  date?: number
  ts?: string
  [key: string]: unknown
}

interface UseSSEOptions {
  onEvent: (event: SSEEvent) => void
  /** Whether to actually subscribe. Default true. */
  enabled?: boolean
}

export function useSSE({ onEvent, enabled = true }: UseSSEOptions) {
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  useEffect(() => {
    if (!enabled) return

    let es: EventSource | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let destroyed = false

    function connect() {
      if (destroyed) return
      es = new EventSource('/events', { withCredentials: true })

      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data) as SSEEvent
          onEventRef.current(data)
        } catch {
          // ignore malformed frames
        }
      }

      es.onerror = () => {
        es?.close()
        if (!destroyed) {
          reconnectTimer = setTimeout(connect, 3000)
        }
      }
    }

    connect()

    return () => {
      destroyed = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      es?.close()
    }
  }, [enabled])
}
