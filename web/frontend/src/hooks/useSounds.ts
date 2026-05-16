/**
 * Audio feedback for message events.
 * Preloads sent/received sounds on first call, plays on demand.
 * Only plays when the document is visible (respects tab focus).
 *
 * Call configureSounds() to set custom/none modes; the module caches the
 * config and lazily reinitialises audio elements on next play.
 */

export type SoundMode = 'default' | 'none' | 'custom'

export interface SoundsConfig {
  sent: SoundMode
  received: SoundMode
}

let _config: SoundsConfig = { sent: 'default', received: 'default' }
let sentAudio: HTMLAudioElement | null = null
let receivedAudio: HTMLAudioElement | null = null

/**
 * Update the sound configuration.  Clears cached audio elements so the next
 * play call picks up the new URLs.
 */
export function configureSounds(cfg: SoundsConfig) {
  _config = cfg
  sentAudio = null
  receivedAudio = null
}

function urlFor(type: 'sent' | 'received'): string | null {
  const mode = type === 'sent' ? _config.sent : _config.received
  if (mode === 'none') return null
  if (mode === 'custom') return `/api/ui/sounds/custom-${type}`
  return `/static/sounds/${type}.wav`
}

function ensureLoaded() {
  const sentUrl = urlFor('sent')
  const receivedUrl = urlFor('received')

  if (sentUrl) {
    if (!sentAudio || sentAudio.src !== new URL(sentUrl, location.href).href) {
      sentAudio = new Audio(sentUrl)
      sentAudio.volume = 0.4
    }
  } else {
    sentAudio = null
  }

  if (receivedUrl) {
    if (!receivedAudio || receivedAudio.src !== new URL(receivedUrl, location.href).href) {
      receivedAudio = new Audio(receivedUrl)
      receivedAudio.volume = 0.5
    }
  } else {
    receivedAudio = null
  }
}

export function playSentSound() {
  if (document.hidden) return
  if (_config.sent === 'none') return
  ensureLoaded()
  if (!sentAudio) return
  sentAudio.currentTime = 0
  try {
    sentAudio.play().catch(() => {/* autoplay blocked — ignore */})
  } catch {
    // Not implemented in some environments (e.g., jsdom in tests)
  }
}

export function playReceivedSound() {
  if (document.hidden) return
  if (_config.received === 'none') return
  ensureLoaded()
  if (!receivedAudio) return
  receivedAudio.currentTime = 0
  try {
    receivedAudio.play().catch(() => {/* autoplay blocked — ignore */})
  } catch {
    // Not implemented in some environments (e.g., jsdom in tests)
  }
}
