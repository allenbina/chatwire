/**
 * Vitest tests for the useSounds module.
 *
 * Covers:
 *   - playSentSound / playReceivedSound: silent when document.hidden
 *   - playSentSound / playReceivedSound: silent when mode is 'none'
 *   - Default URL: /static/sounds/{type}.wav
 *   - Custom URL: /api/ui/sounds/custom-{type}
 *   - Volume: sent → 0.4, received → 0.5
 *   - currentTime reset to 0 before each play() call
 *   - Audio element reuse when URL is unchanged
 *   - New Audio element created after configureSounds clears cache
 *   - play() rejection handled silently (no thrown error)
 *   - configureSounds sets _config and nulls cached audio elements
 *
 * Implementation note:
 *   ensureLoaded() eagerly initialises BOTH sentAudio and receivedAudio in one
 *   call.  Consequently, the first play* call always adds 2 MockAudio instances:
 *     instances[0] → sentAudio  (created first inside ensureLoaded)
 *     instances[1] → receivedAudio  (created second)
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { configureSounds, playSentSound, playReceivedSound } from './useSounds'

// ── Mock Audio class ──────────────────────────────────────────────────────────

class MockAudio {
  /** All instances constructed during the current test. */
  static instances: MockAudio[] = []

  src: string
  volume = 1
  currentTime = 0
  play = vi.fn().mockResolvedValue(undefined)

  constructor(url: string) {
    // Resolve to absolute URL to match the browser behaviour in ensureLoaded comparisons.
    this.src = new URL(url, location.href).href
    MockAudio.instances.push(this)
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function setHidden(value: boolean) {
  Object.defineProperty(document, 'hidden', { get: () => value, configurable: true })
}

// ── Setup / Teardown ──────────────────────────────────────────────────────────

beforeEach(() => {
  MockAudio.instances = []
  globalThis.Audio = MockAudio as unknown as typeof Audio

  // Reset module-level config and clear cached audio elements.
  configureSounds({ sent: 'default', received: 'default' })

  // Default: tab is visible.
  setHidden(false)
})

afterEach(() => {
  setHidden(false)
  vi.restoreAllMocks()
})

// ── playSentSound ─────────────────────────────────────────────────────────────

describe('playSentSound', () => {
  it('does nothing when document.hidden is true', () => {
    setHidden(true)
    playSentSound()
    expect(MockAudio.instances).toHaveLength(0)
  })

  it('does nothing when sent mode is "none"', () => {
    configureSounds({ sent: 'none', received: 'default' })
    playSentSound()
    expect(MockAudio.instances).toHaveLength(0)
  })

  it('creates sentAudio with default URL and calls play()', () => {
    playSentSound()
    // ensureLoaded creates both sentAudio (index 0) and receivedAudio (index 1).
    expect(MockAudio.instances).toHaveLength(2)
    const sent = MockAudio.instances[0]
    expect(sent.src).toContain('/static/sounds/sent.wav')
    expect(sent.play).toHaveBeenCalledOnce()
    // receivedAudio is initialised but play() is NOT called on it.
    expect(MockAudio.instances[1].play).not.toHaveBeenCalled()
  })

  it('sets sentAudio volume to 0.4', () => {
    playSentSound()
    expect(MockAudio.instances[0].volume).toBe(0.4)
  })

  it('resets currentTime to 0 before each play() call', () => {
    playSentSound()
    const sent = MockAudio.instances[0]
    sent.currentTime = 5
    playSentSound()
    expect(sent.currentTime).toBe(0)
    expect(sent.play).toHaveBeenCalledTimes(2)
  })

  it('uses custom URL in custom mode', () => {
    configureSounds({ sent: 'custom', received: 'default' })
    playSentSound()
    expect(MockAudio.instances[0].src).toContain('/api/ui/sounds/custom-sent')
  })

  it('reuses the same Audio element when URL is unchanged', () => {
    playSentSound()
    playSentSound()
    // No additional Audio elements constructed on the second call.
    expect(MockAudio.instances).toHaveLength(2)
    expect(MockAudio.instances[0].play).toHaveBeenCalledTimes(2)
  })

  it('creates a new sentAudio element after configureSounds changes mode', () => {
    playSentSound()
    // instances[0]=sent_default, instances[1]=recv_default
    expect(MockAudio.instances).toHaveLength(2)

    configureSounds({ sent: 'custom', received: 'default' })
    playSentSound()
    // ensureLoaded creates two more: instances[2]=sent_custom, instances[3]=recv_default2
    expect(MockAudio.instances).toHaveLength(4)
    expect(MockAudio.instances[2].src).toContain('/api/ui/sounds/custom-sent')
  })

  it('handles play() rejection without throwing', async () => {
    playSentSound()
    const sent = MockAudio.instances[0]
    sent.play = vi.fn().mockRejectedValue(new Error('AutoplayBlocked'))
    // Second call — rejection caught inside useSounds, not propagated.
    expect(() => playSentSound()).not.toThrow()
    // Drain microtask queue so the .catch() runs.
    await new Promise<void>(resolve => setTimeout(resolve, 0))
    expect(sent.play).toHaveBeenCalled()
  })
})

// ── playReceivedSound ─────────────────────────────────────────────────────────

describe('playReceivedSound', () => {
  it('does nothing when document.hidden is true', () => {
    setHidden(true)
    playReceivedSound()
    expect(MockAudio.instances).toHaveLength(0)
  })

  it('does nothing when received mode is "none"', () => {
    configureSounds({ sent: 'default', received: 'none' })
    playReceivedSound()
    expect(MockAudio.instances).toHaveLength(0)
  })

  it('creates receivedAudio with default URL and calls play()', () => {
    playReceivedSound()
    // instances[0]=sentAudio, instances[1]=receivedAudio
    expect(MockAudio.instances).toHaveLength(2)
    const recv = MockAudio.instances[1]
    expect(recv.src).toContain('/static/sounds/received.wav')
    expect(recv.play).toHaveBeenCalledOnce()
    // sentAudio is initialised but play() is NOT called on it.
    expect(MockAudio.instances[0].play).not.toHaveBeenCalled()
  })

  it('sets receivedAudio volume to 0.5', () => {
    playReceivedSound()
    expect(MockAudio.instances[1].volume).toBe(0.5)
  })

  it('resets currentTime to 0 before each play() call', () => {
    playReceivedSound()
    const recv = MockAudio.instances[1]
    recv.currentTime = 3
    playReceivedSound()
    expect(recv.currentTime).toBe(0)
    expect(recv.play).toHaveBeenCalledTimes(2)
  })

  it('uses custom URL in custom mode', () => {
    configureSounds({ sent: 'default', received: 'custom' })
    playReceivedSound()
    expect(MockAudio.instances[1].src).toContain('/api/ui/sounds/custom-received')
  })

  it('reuses the same Audio element when URL is unchanged', () => {
    playReceivedSound()
    playReceivedSound()
    expect(MockAudio.instances).toHaveLength(2)
    expect(MockAudio.instances[1].play).toHaveBeenCalledTimes(2)
  })

  it('creates a new receivedAudio element after configureSounds changes mode', () => {
    playReceivedSound()
    // instances[0]=sent_default, instances[1]=recv_default
    expect(MockAudio.instances).toHaveLength(2)

    configureSounds({ sent: 'default', received: 'custom' })
    playReceivedSound()
    // instances[2]=sent_default2, instances[3]=recv_custom
    expect(MockAudio.instances).toHaveLength(4)
    expect(MockAudio.instances[3].src).toContain('/api/ui/sounds/custom-received')
  })
})

// ── configureSounds ───────────────────────────────────────────────────────────

describe('configureSounds', () => {
  it('setting both modes to "none" prevents any Audio from being created', () => {
    configureSounds({ sent: 'none', received: 'none' })
    playSentSound()
    playReceivedSound()
    expect(MockAudio.instances).toHaveLength(0)
  })

  it('nulls cached elements so next play() reinitialises them', () => {
    // First round: both elements created.
    playSentSound()
    playReceivedSound()
    // Second call reuses existing elements — still only 2 instances.
    expect(MockAudio.instances).toHaveLength(2)
    const [origSent, origReceived] = MockAudio.instances

    // Reconfigure — caches cleared.
    configureSounds({ sent: 'default', received: 'default' })

    // Next play creates two fresh elements.
    playSentSound()
    playReceivedSound()
    expect(MockAudio.instances).toHaveLength(4)
    expect(MockAudio.instances[2]).not.toBe(origSent)
    expect(MockAudio.instances[3]).not.toBe(origReceived)
  })
})
