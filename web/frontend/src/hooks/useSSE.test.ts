/**
 * Vitest tests for the useSSE hook.
 *
 * Covers:
 *   - Does not open an EventSource when enabled=false
 *   - Opens EventSource('/events', {withCredentials:true}) when enabled=true
 *   - Calls onEvent with the parsed JSON payload on message
 *   - Ignores malformed JSON frames (no throw)
 *   - Reconnects after 3 s when the connection errors
 *   - Does NOT reconnect when the hook has been unmounted (destroyed flag)
 *   - Closes EventSource and cancels reconnect timer on unmount
 *   - onEvent callback updated via ref — no reconnect when callback identity changes
 *   - Stops subscribing when enabled transitions true→false and re-renders
 *   - Starts subscribing when enabled transitions false→true and re-renders
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useSSE } from './useSSE'
import type { SSEEvent } from './useSSE'

// ---------------------------------------------------------------------------
// Mock EventSource
// ---------------------------------------------------------------------------

class MockEventSource {
  static instances: MockEventSource[] = []

  url: string
  options: EventSourceInit
  onmessage: ((e: MessageEvent) => void) | null = null
  onerror: (() => void) | null = null
  closed = false

  constructor(url: string, options: EventSourceInit) {
    this.url = url
    this.options = options
    MockEventSource.instances.push(this)
  }

  close() {
    this.closed = true
  }

  /** Simulate a message arriving from the server. */
  simulateMessage(data: string) {
    this.onmessage?.({ data } as MessageEvent)
  }

  /** Simulate a connection error. */
  simulateError() {
    this.onerror?.()
  }
}

describe('useSSE', () => {
  beforeEach(() => {
    MockEventSource.instances = []
    vi.useFakeTimers()
    // @ts-expect-error override with mock
    globalThis.EventSource = MockEventSource
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  // -------------------------------------------------------------------------
  // enabled=false — no connection
  // -------------------------------------------------------------------------

  it('does not open EventSource when enabled=false', () => {
    const onEvent = vi.fn()
    renderHook(() => useSSE({ onEvent, enabled: false }))
    expect(MockEventSource.instances).toHaveLength(0)
  })

  it('does not call onEvent when enabled=false and a message arrives from elsewhere', () => {
    const onEvent = vi.fn()
    renderHook(() => useSSE({ onEvent, enabled: false }))
    // No EventSource opened — onEvent should never fire.
    expect(onEvent).not.toHaveBeenCalled()
  })

  // -------------------------------------------------------------------------
  // enabled=true (default) — basic connection
  // -------------------------------------------------------------------------

  it('opens EventSource at /events with withCredentials:true', () => {
    const onEvent = vi.fn()
    renderHook(() => useSSE({ onEvent }))

    expect(MockEventSource.instances).toHaveLength(1)
    expect(MockEventSource.instances[0].url).toBe('/events')
    expect(MockEventSource.instances[0].options.withCredentials).toBe(true)
  })

  it('calls onEvent with parsed JSON on message', () => {
    const onEvent = vi.fn()
    renderHook(() => useSSE({ onEvent }))

    const payload: SSEEvent = { handle: '+15551234567', text: 'hello', rowid: 42 }
    act(() => {
      MockEventSource.instances[0].simulateMessage(JSON.stringify(payload))
    })

    expect(onEvent).toHaveBeenCalledTimes(1)
    expect(onEvent).toHaveBeenCalledWith(payload)
  })

  it('ignores malformed JSON frames without throwing', () => {
    const onEvent = vi.fn()
    renderHook(() => useSSE({ onEvent }))

    expect(() => {
      act(() => {
        MockEventSource.instances[0].simulateMessage('not-json{{{')
      })
    }).not.toThrow()

    expect(onEvent).not.toHaveBeenCalled()
  })

  it('handles multiple messages in sequence', () => {
    const onEvent = vi.fn()
    renderHook(() => useSSE({ onEvent }))
    const es = MockEventSource.instances[0]

    act(() => {
      es.simulateMessage(JSON.stringify({ handle: 'a', rowid: 1 }))
      es.simulateMessage(JSON.stringify({ handle: 'b', rowid: 2 }))
    })

    expect(onEvent).toHaveBeenCalledTimes(2)
    expect(onEvent).toHaveBeenNthCalledWith(1, { handle: 'a', rowid: 1 })
    expect(onEvent).toHaveBeenNthCalledWith(2, { handle: 'b', rowid: 2 })
  })

  // -------------------------------------------------------------------------
  // Reconnect logic
  // -------------------------------------------------------------------------

  it('closes the broken EventSource and schedules reconnect after 3 s on error', () => {
    const onEvent = vi.fn()
    renderHook(() => useSSE({ onEvent }))
    const firstEs = MockEventSource.instances[0]

    act(() => {
      firstEs.simulateError()
    })

    expect(firstEs.closed).toBe(true)
    // Not yet reconnected — timer not fired.
    expect(MockEventSource.instances).toHaveLength(1)

    act(() => {
      vi.advanceTimersByTime(3000)
    })

    // Second EventSource created after 3 s.
    expect(MockEventSource.instances).toHaveLength(2)
    expect(MockEventSource.instances[1].url).toBe('/events')
  })

  it('new connection after reconnect also calls onEvent', () => {
    const onEvent = vi.fn()
    renderHook(() => useSSE({ onEvent }))

    act(() => {
      MockEventSource.instances[0].simulateError()
      vi.advanceTimersByTime(3000)
    })

    const secondEs = MockEventSource.instances[1]
    act(() => {
      secondEs.simulateMessage(JSON.stringify({ handle: '+1', rowid: 99 }))
    })

    expect(onEvent).toHaveBeenCalledWith({ handle: '+1', rowid: 99 })
  })

  it('does not reconnect after unmount (destroyed flag prevents timer callback)', () => {
    const onEvent = vi.fn()
    const { unmount } = renderHook(() => useSSE({ onEvent }))
    const firstEs = MockEventSource.instances[0]

    act(() => {
      firstEs.simulateError()
    })

    unmount()

    act(() => {
      vi.advanceTimersByTime(3000)
    })

    // No second EventSource was created.
    expect(MockEventSource.instances).toHaveLength(1)
  })

  it('closes EventSource on unmount', () => {
    const onEvent = vi.fn()
    const { unmount } = renderHook(() => useSSE({ onEvent }))
    const es = MockEventSource.instances[0]

    unmount()

    expect(es.closed).toBe(true)
  })

  it('cancels a pending reconnect timer on unmount', () => {
    const onEvent = vi.fn()
    const { unmount } = renderHook(() => useSSE({ onEvent }))

    act(() => {
      MockEventSource.instances[0].simulateError()
    })

    // Timer is pending — unmount before it fires.
    unmount()

    act(() => {
      vi.advanceTimersByTime(3000)
    })

    // No new EventSource should have been created.
    expect(MockEventSource.instances).toHaveLength(1)
  })

  // -------------------------------------------------------------------------
  // onEvent ref — no reconnect when callback identity changes
  // -------------------------------------------------------------------------

  it('updating onEvent callback does not cause reconnect', () => {
    let onEvent = vi.fn()
    const { rerender } = renderHook(({ cb }) => useSSE({ onEvent: cb }), {
      initialProps: { cb: onEvent },
    })

    expect(MockEventSource.instances).toHaveLength(1)
    const firstEs = MockEventSource.instances[0]

    // Replace the callback (new function identity).
    const onEvent2 = vi.fn()
    onEvent = onEvent2
    rerender({ cb: onEvent2 })

    // Still only one EventSource — no reconnect.
    expect(MockEventSource.instances).toHaveLength(1)
    expect(MockEventSource.instances[0]).toBe(firstEs)
  })

  it('new callback via ref receives subsequent messages', () => {
    const onEvent1 = vi.fn()
    const onEvent2 = vi.fn()

    const { rerender } = renderHook(({ cb }) => useSSE({ onEvent: cb }), {
      initialProps: { cb: onEvent1 },
    })

    const es = MockEventSource.instances[0]

    act(() => {
      es.simulateMessage(JSON.stringify({ rowid: 1 }))
    })
    expect(onEvent1).toHaveBeenCalledTimes(1)

    // Swap callback.
    rerender({ cb: onEvent2 })

    act(() => {
      es.simulateMessage(JSON.stringify({ rowid: 2 }))
    })
    // New callback gets the second message; old callback stays at 1.
    expect(onEvent2).toHaveBeenCalledTimes(1)
    expect(onEvent1).toHaveBeenCalledTimes(1)
  })

  // -------------------------------------------------------------------------
  // enabled transitions
  // -------------------------------------------------------------------------

  it('starts subscribing when enabled transitions false→true', () => {
    const onEvent = vi.fn()
    const { rerender } = renderHook(
      ({ enabled }) => useSSE({ onEvent, enabled }),
      { initialProps: { enabled: false } },
    )

    expect(MockEventSource.instances).toHaveLength(0)

    rerender({ enabled: true })

    expect(MockEventSource.instances).toHaveLength(1)
    expect(MockEventSource.instances[0].url).toBe('/events')
  })

  it('stops subscribing when enabled transitions true→false', () => {
    const onEvent = vi.fn()
    const { rerender } = renderHook(
      ({ enabled }) => useSSE({ onEvent, enabled }),
      { initialProps: { enabled: true } },
    )

    const firstEs = MockEventSource.instances[0]
    expect(firstEs.closed).toBe(false)

    rerender({ enabled: false })

    expect(firstEs.closed).toBe(true)
    // No new EventSource opened.
    expect(MockEventSource.instances).toHaveLength(1)
  })
})
