/**
 * useServerEvents — SSE connection to the chatwire /events endpoint.
 *
 * Uses a polling fallback since React Native does not have a native
 * EventSource. A polyfill (react-native-event-source) can be dropped in
 * by assigning it to the global EventSource before the first render.
 *
 * Auto-reconnects with exponential back-off (1s → 2s → 4s … max 30s).
 */
import { useEffect, useRef } from 'react'
import { useAppState } from '../state/AppStateContext'

const MIN_BACKOFF = 1000
const MAX_BACKOFF = 30_000

/** Callback invoked on every SSE message event (or poll tick). */
type OnEventFn = () => void

export function useServerEvents(onEvent: OnEventFn) {
  const { client } = useAppState()
  const onEventRef = useRef<OnEventFn>(onEvent)
  onEventRef.current = onEvent

  useEffect(() => {
    if (!client) return

    let es: EventSource | null = null
    let pollInterval: ReturnType<typeof setInterval> | null = null
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null
    let backoff = MIN_BACKOFF
    let destroyed = false

    function cleanup() {
      if (es) { es.close(); es = null }
      if (pollInterval) { clearInterval(pollInterval); pollInterval = null }
      if (reconnectTimeout) { clearTimeout(reconnectTimeout); reconnectTimeout = null }
    }

    function startPolling() {
      // Fallback: poll every 15 seconds
      pollInterval = setInterval(() => {
        onEventRef.current()
      }, 15_000)
    }

    function connect() {
      if (destroyed) return
      cleanup()

      if (typeof EventSource !== 'undefined') {
        try {
          es = new EventSource(client.eventsUrl())

          es.onmessage = () => {
            backoff = MIN_BACKOFF // reset on success
            onEventRef.current()
          }

          es.onerror = () => {
            if (destroyed) return
            cleanup()
            // Exponential back-off reconnect
            reconnectTimeout = setTimeout(() => {
              backoff = Math.min(backoff * 2, MAX_BACKOFF)
              connect()
            }, backoff)
          }
        } catch {
          startPolling()
        }
      } else {
        // No EventSource — fall back to polling
        startPolling()
      }
    }

    connect()

    return () => {
      destroyed = true
      cleanup()
    }
  }, [client])
}
