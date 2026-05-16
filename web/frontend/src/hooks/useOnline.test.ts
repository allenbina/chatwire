/**
 * Vitest tests for the useOnline hook.
 *
 * Covers:
 *   - Initial state mirrors navigator.onLine
 *   - Transitions to offline when 'offline' event fires
 *   - Transitions back online when 'online' event fires
 *   - Multiple transitions (online → offline → online)
 *   - Event listeners removed on unmount (no state update after unmount)
 *   - navigator.onLine=false at mount returns false initially
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useOnline } from './useOnline'

// Helper to set navigator.onLine without reassigning the read-only property directly.
function setOnline(value: boolean) {
  Object.defineProperty(navigator, 'onLine', { get: () => value, configurable: true })
}

describe('useOnline', () => {
  beforeEach(() => {
    // Default: browser is online.
    setOnline(true)
  })

  afterEach(() => {
    // Restore to true so other tests are unaffected.
    setOnline(true)
  })

  it('returns true when navigator.onLine is true at mount', () => {
    setOnline(true)
    const { result } = renderHook(() => useOnline())
    expect(result.current).toBe(true)
  })

  it('returns false when navigator.onLine is false at mount', () => {
    setOnline(false)
    const { result } = renderHook(() => useOnline())
    expect(result.current).toBe(false)
  })

  it('transitions to false when "offline" event fires', () => {
    setOnline(true)
    const { result } = renderHook(() => useOnline())
    expect(result.current).toBe(true)

    act(() => {
      setOnline(false)
      window.dispatchEvent(new Event('offline'))
    })

    expect(result.current).toBe(false)
  })

  it('transitions to true when "online" event fires after going offline', () => {
    setOnline(false)
    const { result } = renderHook(() => useOnline())
    expect(result.current).toBe(false)

    act(() => {
      setOnline(true)
      window.dispatchEvent(new Event('online'))
    })

    expect(result.current).toBe(true)
  })

  it('tracks multiple online/offline transitions', () => {
    setOnline(true)
    const { result } = renderHook(() => useOnline())

    act(() => {
      setOnline(false)
      window.dispatchEvent(new Event('offline'))
    })
    expect(result.current).toBe(false)

    act(() => {
      setOnline(true)
      window.dispatchEvent(new Event('online'))
    })
    expect(result.current).toBe(true)

    act(() => {
      setOnline(false)
      window.dispatchEvent(new Event('offline'))
    })
    expect(result.current).toBe(false)
  })

  it('removes event listeners on unmount (no state update after unmount)', () => {
    setOnline(true)
    const { result, unmount } = renderHook(() => useOnline())
    expect(result.current).toBe(true)

    unmount()

    // Dispatching events after unmount should not throw or update state.
    act(() => {
      setOnline(false)
      window.dispatchEvent(new Event('offline'))
    })

    // Result is frozen at the last rendered value (true).
    expect(result.current).toBe(true)
  })

  it('handles rapid offline/online events without errors', () => {
    setOnline(true)
    const { result } = renderHook(() => useOnline())

    act(() => {
      for (let i = 0; i < 10; i++) {
        const goingOffline = i % 2 === 0
        setOnline(!goingOffline)
        window.dispatchEvent(new Event(goingOffline ? 'offline' : 'online'))
      }
    })

    // After 10 events (0-indexed: 0=offline, 1=online, ..., 9=online), last is online.
    expect(result.current).toBe(true)
  })
})
