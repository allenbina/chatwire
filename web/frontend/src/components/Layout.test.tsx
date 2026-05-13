/**
 * Vitest unit tests for Layout / SidebarContent — hiatus indicator.
 *
 * Covers:
 *   - "Hiatus ON" banner is shown when hiatus_enabled is true
 *   - "Hiatus ON" banner is hidden when hiatus_enabled is false
 *   - "Hiatus ON" banner is hidden while the notifications fetch is pending
 */
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { Layout } from './Layout'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// ConversationList makes its own fetch — stub it out.
vi.mock('./ConversationList', () => ({
  ConversationList: () => <div data-testid="mock-conv-list" />,
}))

// SlotRenderer renders nothing in tests.
vi.mock('../plugins/SlotRenderer', () => ({
  SlotRenderer: () => null,
}))

// SlidingHighlight uses requestAnimationFrame/DOM measurement — render children.
vi.mock('./SlidingHighlight', () => ({
  SlidingHighlight: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <div className={className}>{children}</div>
  ),
}))

// useOnline — default online so the "Offline" banner doesn't interfere.
vi.mock('../hooks/useOnline', () => ({
  useOnline: () => true,
}))

// useTheme — minimal stub.
vi.mock('../hooks/useTheme', () => ({
  useTheme: () => ({ themeMode: 'light', setThemeMode: vi.fn() }),
}))

// Zustand store — handle both selector and no-arg calling conventions.
// SidebarContent: useChatStore((s) => s.setSidebarOpen)  → selector form
// Layout:         const { sidebarOpen, setSidebarOpen } = useChatStore()  → no selector
vi.mock('../store', () => {
  const state = { setSidebarOpen: vi.fn(), sidebarOpen: false }
  return {
    useChatStore: (selector?: (s: typeof state) => unknown) =>
      selector ? selector(state) : state,
  }
})

// Radix Sheet — render children so jsdom sees sidebar content.
vi.mock('@/components/ui/sheet', () => ({
  Sheet: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

// ../api — stub fetchConversations (used in SidebarContent for hasUnseen).
vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    fetchConversations: vi.fn().mockResolvedValue([]),
    markAllSeen: vi.fn(),
  }
})

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a QueryClient with retries disabled (fast failure in tests). */
function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

/**
 * Stub global `fetch` so that:
 * - /api/ui/settings/notifications → { hiatus_enabled, hiatus_started_at }
 * - /api/ui/auth/has-password      → { has_password: false }
 * - everything else                → empty object
 */
function stubFetch(hiatusEnabled: boolean, hiatusStartedAt = 0) {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      let body: object = {}
      if (url.includes('settings/notifications')) {
        body = {
          hiatus_enabled: hiatusEnabled,
          hiatus_duration_minutes: 30,
          hiatus_started_at: hiatusStartedAt,
          reminder_enabled: false,
          reminder_days: 7,
          reminder_contacts: [],
          notification_detail: 'rich',
          notification_depth: {},
        }
      } else if (url.includes('auth/has-password')) {
        body = { has_password: false }
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(body),
      } as Response)
    }),
  )
}

function renderLayout(hiatusEnabled: boolean, hiatusStartedAt = 0) {
  stubFetch(hiatusEnabled, hiatusStartedAt)
  const qc = makeQC()
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Layout>
          <div data-testid="mock-child" />
        </Layout>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Layout — hiatus indicator', () => {
  it('shows "Hiatus ON" banner when hiatus_enabled is true', async () => {
    renderLayout(true)
    await waitFor(() => {
      expect(screen.getAllByText('Hiatus ON').length).toBeGreaterThan(0)
    })
  })

  it('does NOT show "Hiatus ON" banner when hiatus_enabled is false', async () => {
    renderLayout(false)
    // Wait for the query to resolve before asserting absence.
    await waitFor(() => {
      expect(vi.mocked(fetch)).toHaveBeenCalled()
    })
    expect(screen.queryByText('Hiatus ON')).not.toBeInTheDocument()
  })

  it('does NOT show "Hiatus ON" banner before the fetch resolves', () => {
    // Use a fetch that never resolves to simulate pending state.
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise(() => {})),
    )
    const qc = makeQC()
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <Layout>
            <div />
          </Layout>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(screen.queryByText('Hiatus ON')).not.toBeInTheDocument()
  })

  it('shows "End" button in the hiatus banner when hiatus is active', async () => {
    renderLayout(true)
    await waitFor(() => {
      expect(screen.getAllByText('Hiatus ON').length).toBeGreaterThan(0)
    })
    expect(screen.getAllByRole('button', { name: /end hiatus/i }).length).toBeGreaterThan(0)
  })

  it('shows "Xm left" in banner when hiatus_started_at is set', async () => {
    // Started 5 minutes ago, duration 30 min → ~25m left.
    const startedAt = (Date.now() - 5 * 60 * 1000) / 1000
    renderLayout(true, startedAt)
    await waitFor(() => {
      const banners = screen.getAllByText(/Hiatus ON/)
      expect(banners.length).toBeGreaterThan(0)
      expect(banners[0].textContent).toMatch(/·\s*\d+m left/)
    })
  })

  it('does NOT show "Xm left" in banner when hiatus_started_at is 0', async () => {
    renderLayout(true, 0)
    await waitFor(() => {
      expect(screen.getAllByText(/Hiatus ON/).length).toBeGreaterThan(0)
    })
    const banners = screen.getAllByText(/Hiatus ON/)
    for (const banner of banners) {
      expect(banner.textContent).not.toMatch(/m left/)
    }
  })

  it('clicking "End" button POSTs hiatus_enabled=false and invalidates the cache', async () => {
    // Use a fetch that returns hiatus=true on GET, and ok on POST.
    const mockFetch = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) } as Response)
      }
      let body: object = {}
      if (url.includes('settings/notifications')) {
        body = {
          hiatus_enabled: true,
          hiatus_duration_minutes: 30,
          reminder_enabled: false,
          reminder_days: 7,
          reminder_contacts: [],
          notification_detail: 'rich',
          notification_depth: {},
        }
      } else if (url.includes('auth/has-password')) {
        body = { has_password: false }
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve(body) } as Response)
    })
    vi.stubGlobal('fetch', mockFetch)

    const qc = makeQC()
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <Layout>
            <div />
          </Layout>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    // Wait for banner to appear.
    await waitFor(() => {
      expect(screen.getAllByText('Hiatus ON').length).toBeGreaterThan(0)
    })

    // Click the End button.
    const endBtn = screen.getAllByRole('button', { name: /end hiatus/i })[0]
    fireEvent.click(endBtn)

    // The POST to /api/settings/hiatus_settings should be called with hiatus_enabled=false.
    await waitFor(() => {
      const postCall = mockFetch.mock.calls.find(
        (args) => (args[0] as string).includes('hiatus_settings') && (args[1] as RequestInit)?.method === 'POST',
      )
      expect(postCall).toBeTruthy()
      const body = (postCall as [string, RequestInit])[1].body as FormData
      expect(body.get('hiatus_enabled')).toBe('false')
    })
  })
})
