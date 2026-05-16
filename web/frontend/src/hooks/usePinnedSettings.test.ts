/**
 * Vitest tests for usePinnedSettings hook and related exports.
 *
 * Covers:
 *   - PINNABLE_LABELS exports correct human-readable labels
 *   - Starts with empty pinnedKeys when localStorage is empty
 *   - Loads previously saved pinnedKeys from localStorage on mount
 *   - Handles invalid JSON in localStorage gracefully (returns empty)
 *   - Handles non-array JSON in localStorage gracefully (returns empty)
 *   - togglePin adds an unpinned key
 *   - togglePin removes a key that is already pinned
 *   - togglePin persists state to localStorage
 *   - isPinned returns true for a pinned key
 *   - isPinned returns false for an unpinned key
 *   - Toggling the same key twice round-trips back to unpinned
 *   - Multiple keys can be pinned simultaneously
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { usePinnedSettings, PINNABLE_LABELS } from './usePinnedSettings'

const LS_KEY = 'chatwire-pinned-settings'

describe('PINNABLE_LABELS', () => {
  it('has a label for hiatus_enabled', () => {
    expect(PINNABLE_LABELS.hiatus_enabled).toBe('Hiatus')
  })

  it('has a label for reminder_enabled', () => {
    expect(PINNABLE_LABELS.reminder_enabled).toBe('Reminder')
  })
})

describe('usePinnedSettings — initial state', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('starts with empty pinnedKeys when localStorage is empty', () => {
    const { result } = renderHook(() => usePinnedSettings())
    expect(result.current.pinnedKeys).toEqual([])
  })

  it('loads pinnedKeys from localStorage on mount', () => {
    localStorage.setItem(LS_KEY, JSON.stringify(['hiatus_enabled']))
    const { result } = renderHook(() => usePinnedSettings())
    expect(result.current.pinnedKeys).toEqual(['hiatus_enabled'])
  })

  it('loads multiple pinnedKeys from localStorage', () => {
    localStorage.setItem(LS_KEY, JSON.stringify(['hiatus_enabled', 'reminder_enabled']))
    const { result } = renderHook(() => usePinnedSettings())
    expect(result.current.pinnedKeys).toEqual(['hiatus_enabled', 'reminder_enabled'])
  })

  it('returns empty array when localStorage contains invalid JSON', () => {
    localStorage.setItem(LS_KEY, 'not-valid-json{{{')
    const { result } = renderHook(() => usePinnedSettings())
    expect(result.current.pinnedKeys).toEqual([])
  })

  it('returns empty array when localStorage contains non-array JSON', () => {
    localStorage.setItem(LS_KEY, JSON.stringify({ hiatus_enabled: true }))
    const { result } = renderHook(() => usePinnedSettings())
    expect(result.current.pinnedKeys).toEqual([])
  })

  it('returns empty array when localStorage contains null', () => {
    localStorage.setItem(LS_KEY, 'null')
    const { result } = renderHook(() => usePinnedSettings())
    expect(result.current.pinnedKeys).toEqual([])
  })
})

describe('usePinnedSettings — togglePin', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('togglePin adds a key that is not yet pinned', () => {
    const { result } = renderHook(() => usePinnedSettings())
    expect(result.current.pinnedKeys).toEqual([])

    act(() => {
      result.current.togglePin('hiatus_enabled')
    })

    expect(result.current.pinnedKeys).toContain('hiatus_enabled')
  })

  it('togglePin removes a key that is already pinned', () => {
    localStorage.setItem(LS_KEY, JSON.stringify(['hiatus_enabled']))
    const { result } = renderHook(() => usePinnedSettings())

    act(() => {
      result.current.togglePin('hiatus_enabled')
    })

    expect(result.current.pinnedKeys).not.toContain('hiatus_enabled')
  })

  it('togglePin round-trips: add then remove returns empty', () => {
    const { result } = renderHook(() => usePinnedSettings())

    act(() => { result.current.togglePin('reminder_enabled') })
    expect(result.current.pinnedKeys).toContain('reminder_enabled')

    act(() => { result.current.togglePin('reminder_enabled') })
    expect(result.current.pinnedKeys).not.toContain('reminder_enabled')
  })

  it('togglePin persists the new value to localStorage', () => {
    const { result } = renderHook(() => usePinnedSettings())

    act(() => { result.current.togglePin('hiatus_enabled') })

    const stored = JSON.parse(localStorage.getItem(LS_KEY) ?? '[]')
    expect(stored).toContain('hiatus_enabled')
  })

  it('togglePin removes key from localStorage when unpinned', () => {
    localStorage.setItem(LS_KEY, JSON.stringify(['hiatus_enabled']))
    const { result } = renderHook(() => usePinnedSettings())

    act(() => { result.current.togglePin('hiatus_enabled') })

    const stored = JSON.parse(localStorage.getItem(LS_KEY) ?? '[]')
    expect(stored).not.toContain('hiatus_enabled')
  })

  it('multiple keys can be pinned simultaneously', () => {
    const { result } = renderHook(() => usePinnedSettings())

    act(() => { result.current.togglePin('hiatus_enabled') })
    act(() => { result.current.togglePin('reminder_enabled') })

    expect(result.current.pinnedKeys).toContain('hiatus_enabled')
    expect(result.current.pinnedKeys).toContain('reminder_enabled')
    expect(result.current.pinnedKeys).toHaveLength(2)
  })

  it('toggling one key does not affect another pinned key', () => {
    localStorage.setItem(LS_KEY, JSON.stringify(['hiatus_enabled', 'reminder_enabled']))
    const { result } = renderHook(() => usePinnedSettings())

    act(() => { result.current.togglePin('hiatus_enabled') })

    expect(result.current.pinnedKeys).not.toContain('hiatus_enabled')
    expect(result.current.pinnedKeys).toContain('reminder_enabled')
  })
})

describe('usePinnedSettings — isPinned', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('isPinned returns true for a pinned key', () => {
    localStorage.setItem(LS_KEY, JSON.stringify(['hiatus_enabled']))
    const { result } = renderHook(() => usePinnedSettings())
    expect(result.current.isPinned('hiatus_enabled')).toBe(true)
  })

  it('isPinned returns false for an unpinned key', () => {
    const { result } = renderHook(() => usePinnedSettings())
    expect(result.current.isPinned('hiatus_enabled')).toBe(false)
  })

  it('isPinned updates reactively after togglePin', () => {
    const { result } = renderHook(() => usePinnedSettings())
    expect(result.current.isPinned('reminder_enabled')).toBe(false)

    act(() => { result.current.togglePin('reminder_enabled') })
    expect(result.current.isPinned('reminder_enabled')).toBe(true)

    act(() => { result.current.togglePin('reminder_enabled') })
    expect(result.current.isPinned('reminder_enabled')).toBe(false)
  })
})
