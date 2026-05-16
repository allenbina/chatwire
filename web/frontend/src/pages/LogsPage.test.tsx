/**
 * Vitest unit tests for LogsPage — structured log viewer.
 *
 * Covers:
 *   - Basic render: heading, status indicator, empty state
 *   - History fetch on mount (/api/ui/logs?limit=500)
 *   - SSE events: open → "live", error → "history", message → appends entry
 *   - SSE cleanup on unmount
 *   - Pause/Resume toggle: button label, paused notice, buffered message ignored
 *   - Source and level filter selectors (initial values)
 *   - Text search filters entries; shows "no match" message
 *   - Level min-filter hides entries below selected level
 *   - Export button disabled/enabled; blob download triggered
 *   - Footer entry count (total and filtered)
 */
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'
import { LogsPage } from './LogsPage'

// ---------------------------------------------------------------------------
// Mock Layout — render children directly, no sidebar / nav fetches
// ---------------------------------------------------------------------------

vi.mock('../components/Layout', () => ({
  Layout: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}))

// ---------------------------------------------------------------------------
// Mock @tanstack/react-virtual — return all items regardless of DOM layout
// ---------------------------------------------------------------------------

vi.mock('@tanstack/react-virtual', () => ({
  useVirtualizer: (opts: {
    count: number
    getScrollElement: () => HTMLElement | null
    estimateSize: () => number
  }) => ({
    getVirtualItems: () =>
      Array.from({ length: opts.count }, (_, i) => ({
        key: i,
        index: i,
        start: i * opts.estimateSize(),
        size: opts.estimateSize(),
      })),
    getTotalSize: () => opts.count * opts.estimateSize(),
    scrollToIndex: vi.fn(),
    measureElement: vi.fn(),
  }),
}))

// ---------------------------------------------------------------------------
// EventSource mock
// ---------------------------------------------------------------------------

interface MockESInstance {
  url: string
  withCredentials: boolean
  onopen: ((ev: Event) => void) | null
  onerror: ((ev: Event) => void) | null
  onmessage: ((ev: MessageEvent) => void) | null
  close: ReturnType<typeof vi.fn>
}

let lastEs: MockESInstance | null = null

class MockEventSource {
  url: string
  withCredentials: boolean
  onopen: ((ev: Event) => void) | null = null
  onerror: ((ev: Event) => void) | null = null
  onmessage: ((ev: MessageEvent) => void) | null = null
  close = vi.fn()

  constructor(url: string, init?: { withCredentials?: boolean }) {
    this.url = url
    this.withCredentials = init?.withCredentials ?? false
    lastEs = this as unknown as MockESInstance
  }
}

// ---------------------------------------------------------------------------
// Sample log entries
// ---------------------------------------------------------------------------

const INFO_ENTRY = {
  ts: '2026-01-01T12:00:00Z',
  source: 'bridge',
  level: 'info',
  msg: 'Hello world',
}
const WARN_ENTRY = {
  ts: '2026-01-01T12:00:01Z',
  source: 'web',
  level: 'warn',
  msg: 'Low memory',
}
const ERROR_ENTRY = {
  ts: '2026-01-01T12:00:02Z',
  source: 'bridge',
  level: 'error',
  msg: 'Connection failed',
}

// ---------------------------------------------------------------------------
// fetch stub
// ---------------------------------------------------------------------------

function stubFetch(entries: object[] = []) {
  globalThis.fetch = vi.fn().mockImplementation((url: string) => {
    if (typeof url === 'string' && url.includes('/api/ui/logs')) {
      return Promise.resolve({
        ok: true,
        json: async () => ({ entries }),
      } as Response)
    }
    return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
  }) as unknown as typeof fetch
}

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

function renderPage() {
  return render(
    <MemoryRouter>
      <LogsPage />
    </MemoryRouter>,
  )
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  lastEs = null
  globalThis.EventSource = MockEventSource as unknown as typeof EventSource
  stubFetch([])
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// Initial render
// ---------------------------------------------------------------------------

describe('LogsPage — initial render', () => {
  it('renders the "Logs" page heading', () => {
    renderPage()
    expect(screen.getByRole('heading', { name: /^logs$/i })).toBeInTheDocument()
  })

  it('shows the "connecting…" status indicator before SSE opens', () => {
    renderPage()
    expect(screen.getByText(/connecting/i)).toBeInTheDocument()
  })

  it('shows "No log entries yet." when no history is loaded', async () => {
    stubFetch([])
    renderPage()
    await waitFor(() =>
      expect(screen.getByText('No log entries yet.')).toBeInTheDocument(),
    )
  })

  it('fetches history from /api/ui/logs?limit=500 on mount', async () => {
    renderPage()
    await waitFor(() =>
      expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
        expect.stringContaining('/api/ui/logs?limit=500'),
        expect.any(Object),
      ),
    )
  })

  it('renders history entries returned by the API', async () => {
    stubFetch([INFO_ENTRY, WARN_ENTRY])
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('Hello world')).toBeInTheDocument()
      expect(screen.getByText('Low memory')).toBeInTheDocument()
    })
  })
})

// ---------------------------------------------------------------------------
// SSE connection
// ---------------------------------------------------------------------------

describe('LogsPage — SSE connection', () => {
  it('shows "● live" after SSE onopen fires', async () => {
    renderPage()
    act(() => {
      lastEs?.onopen?.(new Event('open'))
    })
    await waitFor(() => expect(screen.getByText('● live')).toBeInTheDocument())
  })

  it('shows "○ history" after SSE onerror fires when entries are present', async () => {
    stubFetch([INFO_ENTRY])
    renderPage()
    await waitFor(() => expect(screen.getByText('Hello world')).toBeInTheDocument())
    act(() => {
      lastEs?.onerror?.(new Event('error'))
    })
    await waitFor(() => expect(screen.getByText('○ history')).toBeInTheDocument())
  })

  it('appends a new entry when SSE onmessage fires', async () => {
    stubFetch([])
    renderPage()
    await waitFor(() => expect(screen.getByText('No log entries yet.')).toBeInTheDocument())

    act(() => {
      lastEs?.onmessage?.(
        new MessageEvent('message', { data: JSON.stringify(INFO_ENTRY) }),
      )
    })

    await waitFor(() => expect(screen.getByText('Hello world')).toBeInTheDocument())
  })

  it('creates the EventSource with withCredentials: true', () => {
    renderPage()
    expect(lastEs?.withCredentials).toBe(true)
  })

  it('closes the EventSource on unmount', () => {
    const { unmount } = renderPage()
    const esRef = lastEs
    unmount()
    expect(esRef?.close).toHaveBeenCalledOnce()
  })
})

// ---------------------------------------------------------------------------
// Pause / Resume
// ---------------------------------------------------------------------------

describe('LogsPage — pause / resume', () => {
  it('Pause button is labeled "⏸ Pause" initially', () => {
    renderPage()
    expect(screen.getByRole('button', { name: /pause/i })).toBeInTheDocument()
  })

  it('clicking Pause shows the paused notice banner', async () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: /pause/i }))
    await waitFor(() =>
      expect(screen.getByText(/stream paused/i)).toBeInTheDocument(),
    )
  })

  it('clicking Pause changes button label to "▶ Resume"', async () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: /pause/i }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /resume/i })).toBeInTheDocument(),
    )
  })

  it('SSE message is ignored while stream is paused', async () => {
    stubFetch([])
    renderPage()
    await waitFor(() => expect(screen.getByText('No log entries yet.')).toBeInTheDocument())

    // Pause the stream
    fireEvent.click(screen.getByRole('button', { name: /pause/i }))
    await waitFor(() => expect(screen.getByText(/stream paused/i)).toBeInTheDocument())

    // Fire SSE message while paused
    act(() => {
      lastEs?.onmessage?.(
        new MessageEvent('message', { data: JSON.stringify(INFO_ENTRY) }),
      )
    })

    // Entry must NOT appear
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.queryByText('Hello world')).toBeNull()
  })

  it('clicking Resume hides the paused notice banner', async () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: /pause/i }))
    await waitFor(() => expect(screen.getByText(/stream paused/i)).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /resume/i }))
    await waitFor(() => expect(screen.queryByText(/stream paused/i)).toBeNull())
  })
})

// ---------------------------------------------------------------------------
// Filters
// ---------------------------------------------------------------------------

describe('LogsPage — filters', () => {
  it('source selector shows "All sources" by default', () => {
    renderPage()
    expect(screen.getByDisplayValue('All sources')).toBeInTheDocument()
  })

  it('level selector shows "All levels" by default', () => {
    renderPage()
    expect(screen.getByDisplayValue('All levels')).toBeInTheDocument()
  })

  it('text search hides non-matching entries', async () => {
    stubFetch([INFO_ENTRY, WARN_ENTRY])
    renderPage()
    await waitFor(() => expect(screen.getByText('Hello world')).toBeInTheDocument())

    fireEvent.change(screen.getByPlaceholderText(/search/i), {
      target: { value: 'Low' },
    })

    await waitFor(() => {
      expect(screen.queryByText('Hello world')).toBeNull()
      expect(screen.getByText('Low memory')).toBeInTheDocument()
    })
  })

  it('shows "No entries match the current filter." when search matches nothing', async () => {
    stubFetch([INFO_ENTRY])
    renderPage()
    await waitFor(() => expect(screen.getByText('Hello world')).toBeInTheDocument())

    fireEvent.change(screen.getByPlaceholderText(/search/i), {
      target: { value: 'zzznomatch' },
    })

    await waitFor(() =>
      expect(
        screen.getByText('No entries match the current filter.'),
      ).toBeInTheDocument(),
    )
  })

  it('level filter hides entries below the selected minimum level', async () => {
    stubFetch([INFO_ENTRY, ERROR_ENTRY])
    renderPage()
    await waitFor(() => expect(screen.getByText('Hello world')).toBeInTheDocument())

    fireEvent.change(screen.getByDisplayValue('All levels'), {
      target: { value: 'error' },
    })

    await waitFor(() => {
      expect(screen.queryByText('Hello world')).toBeNull()
      expect(screen.getByText('Connection failed')).toBeInTheDocument()
    })
  })
})

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

describe('LogsPage — export', () => {
  it('Export button is disabled when there are no entries', async () => {
    stubFetch([])
    renderPage()
    await waitFor(() => expect(screen.getByText('No log entries yet.')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /export/i })).toBeDisabled()
  })

  it('Export button is enabled when entries are loaded', async () => {
    stubFetch([INFO_ENTRY])
    renderPage()
    await waitFor(() => expect(screen.getByText('Hello world')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /export/i })).not.toBeDisabled()
  })

  it('clicking Export creates a blob URL and triggers an anchor click', async () => {
    stubFetch([INFO_ENTRY])
    renderPage()
    await waitFor(() => expect(screen.getByText('Hello world')).toBeInTheDocument())

    const createObjectURL = vi.fn(() => 'blob:mock-url')
    const revokeObjectURL = vi.fn()
    URL.createObjectURL = createObjectURL
    URL.revokeObjectURL = revokeObjectURL

    const anchorClickSpy = vi.fn()
    const origCreate = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      if (tag === 'a') {
        const a = origCreate('a')
        a.click = anchorClickSpy
        return a
      }
      return origCreate(tag)
    })

    fireEvent.click(screen.getByRole('button', { name: /export/i }))

    expect(createObjectURL).toHaveBeenCalledOnce()
    expect(anchorClickSpy).toHaveBeenCalledOnce()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:mock-url')
  })
})

// ---------------------------------------------------------------------------
// Footer
// ---------------------------------------------------------------------------

describe('LogsPage — footer entry count', () => {
  it('shows the total entry count when no filter is active', async () => {
    stubFetch([INFO_ENTRY, WARN_ENTRY])
    renderPage()
    await waitFor(() => expect(screen.getByText(/2 entries/i)).toBeInTheDocument())
  })

  it('shows filtered count with total when a filter is active', async () => {
    stubFetch([INFO_ENTRY, WARN_ENTRY])
    renderPage()
    await waitFor(() => expect(screen.getByText('Hello world')).toBeInTheDocument())

    fireEvent.change(screen.getByPlaceholderText(/search/i), {
      target: { value: 'Low' },
    })

    await waitFor(() =>
      expect(screen.getByText(/1 of 2/i)).toBeInTheDocument(),
    )
  })
})
