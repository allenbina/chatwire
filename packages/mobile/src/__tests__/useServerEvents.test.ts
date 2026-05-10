/**
 * Unit tests for useServerEvents hook.
 * Verifies reconnect logic fires after simulated disconnection.
 */
import { renderHook, act } from '@testing-library/react-native'

// Mock AppStateContext
const mockClient = {
  eventsUrl: jest.fn().mockReturnValue('http://localhost:8723/events'),
}
jest.mock('../state/AppStateContext', () => ({
  useAppState: () => ({ client: mockClient }),
}))

import { useServerEvents } from '../hooks/useServerEvents'

// Fake EventSource
class FakeEventSource {
  static instances: FakeEventSource[] = []
  url: string
  onmessage: ((e: MessageEvent) => void) | null = null
  onerror: ((e: Event) => void) | null = null
  closed = false

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  close() {
    this.closed = true
  }

  triggerMessage() {
    this.onmessage?.(new MessageEvent('message', { data: 'ping' }))
  }

  triggerError() {
    this.onerror?.(new Event('error'))
  }
}

describe('useServerEvents', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    ;(global as any).EventSource = FakeEventSource
    jest.useFakeTimers()
  })

  afterEach(() => {
    jest.useRealTimers()
    delete (global as any).EventSource
  })

  it('creates an EventSource connection on mount', () => {
    const onEvent = jest.fn()
    renderHook(() => useServerEvents(onEvent))
    expect(FakeEventSource.instances).toHaveLength(1)
    expect(FakeEventSource.instances[0].url).toBe('http://localhost:8723/events')
  })

  it('calls onEvent when a message arrives', () => {
    const onEvent = jest.fn()
    renderHook(() => useServerEvents(onEvent))
    act(() => {
      FakeEventSource.instances[0].triggerMessage()
    })
    expect(onEvent).toHaveBeenCalledTimes(1)
  })

  it('reconnects after an error with back-off', () => {
    const onEvent = jest.fn()
    renderHook(() => useServerEvents(onEvent))

    act(() => {
      FakeEventSource.instances[0].triggerError()
      jest.advanceTimersByTime(1100) // back-off 1s + buffer
    })

    // A second EventSource should have been created
    expect(FakeEventSource.instances).toHaveLength(2)
  })

  it('closes EventSource on unmount', () => {
    const onEvent = jest.fn()
    const { unmount } = renderHook(() => useServerEvents(onEvent))
    const es = FakeEventSource.instances[0]
    unmount()
    expect(es.closed).toBe(true)
  })
})
