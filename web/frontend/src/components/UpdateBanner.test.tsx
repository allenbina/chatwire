/**
 * Vitest unit tests for UpdateBanner — new-version notification banner.
 *
 * Covers:
 *   - Returns null when health or release data is absent
 *   - Returns null when the current version equals or exceeds the latest
 *   - Returns null when the latest version has already been dismissed
 *   - Shows the GitHub release banner with version numbers when newer
 *   - Includes a "See release notes" link in the GitHub banner
 *   - Dismiss button hides the banner and persists to localStorage
 *   - Shows the SW update banner when a service-worker controllerchange fires
 *   - SW banner Reload button calls window.location.reload
 */
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { UpdateBanner } from './UpdateBanner'

// ---------------------------------------------------------------------------
// Constants (mirrored from the component)
// ---------------------------------------------------------------------------

const DISMISSED_KEY = 'chatwire-dismissed-version'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

/**
 * Stub globalThis.fetch so both /healthz and the GitHub releases API
 * return controlled values.
 *
 * @param currentVersion  - value placed in `health.release`; falsy = no health
 * @param latestTag       - value placed in `tag_name`; falsy = no release data
 */
function stubFetch(currentVersion: string | null, latestTag: string | null) {
  globalThis.fetch = vi.fn().mockImplementation((url: string) => {
    if (typeof url === 'string' && url.includes('github.com')) {
      if (!latestTag) {
        return Promise.resolve({ ok: false, json: async () => null } as Response)
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ tag_name: latestTag }),
      } as Response)
    }
    // /healthz
    if (!currentVersion) {
      return Promise.resolve({ ok: false, json: async () => ({}) } as Response)
    }
    return Promise.resolve({
      ok: true,
      json: async () => ({ release: currentVersion }),
    } as Response)
  }) as unknown as typeof fetch
}

function renderBanner() {
  const qc = makeQC()
  return render(
    <QueryClientProvider client={qc}>
      <UpdateBanner />
    </QueryClientProvider>,
  )
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// GitHub release banner
// ---------------------------------------------------------------------------

describe('UpdateBanner — GitHub release banner', () => {
  it('renders nothing when health data is absent', async () => {
    stubFetch(null, 'v1.15.0')
    const { container } = renderBanner()
    // Wait for queries to settle
    await new Promise((r) => setTimeout(r, 50))
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing when release data is absent', async () => {
    stubFetch('1.14.0', null)
    const { container } = renderBanner()
    await new Promise((r) => setTimeout(r, 50))
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing when versions are equal', async () => {
    stubFetch('1.14.0', 'v1.14.0')
    const { container } = renderBanner()
    await new Promise((r) => setTimeout(r, 50))
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing when current version is ahead', async () => {
    stubFetch('1.15.0', 'v1.14.0')
    const { container } = renderBanner()
    await new Promise((r) => setTimeout(r, 50))
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing when latest version is already dismissed', async () => {
    localStorage.setItem(DISMISSED_KEY, '1.15.0')
    stubFetch('1.14.0', 'v1.15.0')
    const { container } = renderBanner()
    await new Promise((r) => setTimeout(r, 50))
    expect(container.firstChild).toBeNull()
  })

  it('shows the release banner when a newer version is available', async () => {
    stubFetch('1.14.0', 'v1.15.0')
    renderBanner()
    await waitFor(() =>
      expect(screen.getByText(/1\.15\.0 is available/i)).toBeTruthy(),
    )
  })

  it('displays both the current and latest version numbers', async () => {
    stubFetch('1.14.0', 'v1.15.0')
    renderBanner()
    await waitFor(() => {
      expect(screen.getByText(/you have v1\.14\.0/i)).toBeTruthy()
    })
  })

  it('includes a "See release notes" link', async () => {
    stubFetch('1.14.0', 'v1.15.0')
    renderBanner()
    await waitFor(() => {
      const link = screen.getByRole('link', { name: /see release notes/i })
      expect(link).toBeTruthy()
    })
  })

  it('dismiss button hides the banner', async () => {
    stubFetch('1.14.0', 'v1.15.0')
    renderBanner()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /dismiss/i })).toBeTruthy(),
    )
    fireEvent.click(screen.getByRole('button', { name: /dismiss/i }))
    await waitFor(() =>
      expect(screen.queryByText(/1\.15\.0 is available/i)).toBeNull(),
    )
  })

  it('dismiss button persists the version to localStorage', async () => {
    stubFetch('1.14.0', 'v1.15.0')
    renderBanner()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /dismiss/i })).toBeTruthy(),
    )
    fireEvent.click(screen.getByRole('button', { name: /dismiss/i }))
    expect(localStorage.getItem(DISMISSED_KEY)).toBe('1.15.0')
  })

  it('banner has role="status" for screen-reader accessibility', async () => {
    stubFetch('1.14.0', 'v1.15.0')
    renderBanner()
    await waitFor(() =>
      expect(screen.getByRole('status')).toBeTruthy(),
    )
  })
})

// ---------------------------------------------------------------------------
// SW update banner
// ---------------------------------------------------------------------------

describe('UpdateBanner — service-worker update banner', () => {
  let swListeners: Map<string, EventListenerOrEventListenerObject[]>
  let addEventListenerSpy: ReturnType<typeof vi.fn>
  let removeEventListenerSpy: ReturnType<typeof vi.fn>

  beforeEach(() => {
    swListeners = new Map()
    addEventListenerSpy = vi.fn((type: string, handler: EventListenerOrEventListenerObject) => {
      const handlers = swListeners.get(type) ?? []
      handlers.push(handler)
      swListeners.set(type, handlers)
    })
    removeEventListenerSpy = vi.fn()
    Object.defineProperty(navigator, 'serviceWorker', {
      value: {
        addEventListener: addEventListenerSpy,
        removeEventListener: removeEventListenerSpy,
      },
      writable: true,
      configurable: true,
    })
  })

  afterEach(() => {
    // Restore to a no-op stub so the component cleanup function (which calls
    // navigator.serviceWorker.removeEventListener on unmount) doesn't throw
    // while React tears down the tree.
    Object.defineProperty(navigator, 'serviceWorker', {
      value: {
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      },
      writable: true,
      configurable: true,
    })
  })

  function fireSWControllerChange() {
    const handlers = swListeners.get('controllerchange') ?? []
    handlers.forEach((h) => {
      if (typeof h === 'function') {
        h(new Event('controllerchange'))
      }
    })
  }

  it('shows the SW update banner after controllerchange fires', async () => {
    stubFetch('1.14.0', null)
    renderBanner()
    fireSWControllerChange()
    await waitFor(() =>
      expect(screen.getByText(/app updated in background/i)).toBeTruthy(),
    )
  })

  it('SW banner shows a Reload button', async () => {
    stubFetch('1.14.0', null)
    renderBanner()
    fireSWControllerChange()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /reload/i })).toBeTruthy(),
    )
  })

  it('Reload button calls window.location.reload', async () => {
    stubFetch('1.14.0', null)
    const reloadSpy = vi.fn()
    Object.defineProperty(window, 'location', {
      value: { reload: reloadSpy },
      writable: true,
      configurable: true,
    })
    renderBanner()
    fireSWControllerChange()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /reload/i })).toBeTruthy(),
    )
    fireEvent.click(screen.getByRole('button', { name: /reload/i }))
    expect(reloadSpy).toHaveBeenCalledOnce()
  })

  it('SW banner has role="status" for accessibility', async () => {
    stubFetch('1.14.0', null)
    renderBanner()
    fireSWControllerChange()
    await waitFor(() =>
      expect(screen.getByRole('status')).toBeTruthy(),
    )
  })

  it('SW banner takes priority over the GitHub release banner', async () => {
    stubFetch('1.14.0', 'v1.15.0')
    renderBanner()
    // Wait for both queries to settle, then fire the SW event
    await new Promise((r) => setTimeout(r, 50))
    fireSWControllerChange()
    await waitFor(() =>
      expect(screen.getByText(/app updated in background/i)).toBeTruthy(),
    )
    // GitHub release text should not be visible
    expect(screen.queryByText(/1\.15\.0 is available/i)).toBeNull()
  })
})
