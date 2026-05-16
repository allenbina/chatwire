/**
 * Vitest unit tests for StatsWidget — sidebar stats panel plugin component.
 *
 * Covers:
 *   - Returns null while loading
 *   - Returns null when the fetch errors
 *   - Returns null when enabled is false
 *   - Renders the stats panel when enabled is true
 *   - Displays the correct date-range label for known keys
 *   - Displays the raw date_range value for unknown keys
 *   - Shows total message count
 *   - Shows sent and received counts
 *   - Renders the sent/received progress bar when total > 0
 *   - Omits the progress bar when total is 0
 *   - Renders up to 3 top contacts in order
 *   - Clips top_contacts list to at most 3 entries
 *   - Omits the contacts section when top_contacts is empty
 *   - Handles missing sent_total / received_total (defaults to 0)
 *   - Handles missing top_contacts (defaults to empty)
 *   - Sends credentials: same-origin with the fetch request
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StatsWidget } from './StatsWidget'

// ---------------------------------------------------------------------------
// Types (mirrored from component)
// ---------------------------------------------------------------------------

interface StatsData {
  enabled: boolean
  date_range?: string
  sent_total?: number
  received_total?: number
  top_contacts?: Array<{ name: string; handle: string; count: number }>
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function stubStats(data: StatsData | null, ok = true) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok,
      json: async () => data,
    } as Response),
  )
}

function stubStatsError() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: false, status: 500 } as Response),
  )
}

function renderWidget() {
  const qc = makeQC()
  return render(
    <QueryClientProvider client={qc}>
      <StatsWidget />
    </QueryClientProvider>,
  )
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.restoreAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// Loading / error / disabled states
// ---------------------------------------------------------------------------

describe('StatsWidget — null states', () => {
  it('returns null while loading (no DOM output)', () => {
    // Never resolves — simulates loading state
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})))
    const { container } = renderWidget()
    expect(container.firstChild).toBeNull()
  })

  it('returns null when the API returns an error status', async () => {
    stubStatsError()
    const { container } = renderWidget()
    await new Promise((r) => setTimeout(r, 50))
    expect(container.firstChild).toBeNull()
  })

  it('returns null when enabled is false', async () => {
    stubStats({ enabled: false, sent_total: 100, received_total: 50 })
    const { container } = renderWidget()
    await new Promise((r) => setTimeout(r, 50))
    expect(container.firstChild).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Rendered state
// ---------------------------------------------------------------------------

describe('StatsWidget — rendered state', () => {
  it('renders the stats panel when enabled is true', async () => {
    stubStats({
      enabled: true,
      date_range: '30d',
      sent_total: 10,
      received_total: 5,
    })
    renderWidget()
    await waitFor(() =>
      expect(screen.getByRole('complementary')).toBeTruthy(),
    )
    expect(screen.getByLabelText(/message statistics/i)).toBeTruthy()
  })

  it('shows the "Stats" heading', async () => {
    stubStats({ enabled: true, date_range: '30d', sent_total: 1, received_total: 1 })
    renderWidget()
    await waitFor(() =>
      expect(screen.getByText(/^stats$/i)).toBeTruthy(),
    )
  })
})

// ---------------------------------------------------------------------------
// Date range labels
// ---------------------------------------------------------------------------

describe('StatsWidget — date range labels', () => {
  const cases: Array<[string, string]> = [
    ['30d', 'Last 30 days'],
    ['90d', 'Last 90 days'],
    ['365d', 'Last year'],
    ['all', 'All time'],
  ]

  for (const [key, label] of cases) {
    it(`shows "${label}" for date_range="${key}"`, async () => {
      stubStats({ enabled: true, date_range: key, sent_total: 5, received_total: 5 })
      renderWidget()
      await waitFor(() =>
        expect(screen.getByText(new RegExp(label))).toBeTruthy(),
      )
    })
  }

  it('shows the raw value for an unknown date_range key', async () => {
    stubStats({ enabled: true, date_range: 'custom', sent_total: 1, received_total: 1 })
    renderWidget()
    await waitFor(() =>
      expect(screen.getByText(/custom/)).toBeTruthy(),
    )
  })
})

// ---------------------------------------------------------------------------
// Message counts
// ---------------------------------------------------------------------------

describe('StatsWidget — message counts', () => {
  it('shows total message count', async () => {
    stubStats({ enabled: true, date_range: '30d', sent_total: 30, received_total: 70 })
    renderWidget()
    await waitFor(() =>
      expect(screen.getByText(/100 msgs/)).toBeTruthy(),
    )
  })

  it('shows sent count with ↑ arrow', async () => {
    stubStats({ enabled: true, date_range: '30d', sent_total: 30, received_total: 70 })
    renderWidget()
    await waitFor(() =>
      expect(screen.getByText(/↑ 30 sent/)).toBeTruthy(),
    )
  })

  it('shows received count with ↓ arrow', async () => {
    stubStats({ enabled: true, date_range: '30d', sent_total: 30, received_total: 70 })
    renderWidget()
    await waitFor(() =>
      expect(screen.getByText(/↓ 70 received/)).toBeTruthy(),
    )
  })

  it('defaults sent_total and received_total to 0 when absent', async () => {
    stubStats({ enabled: true, date_range: '30d' })
    renderWidget()
    await waitFor(() =>
      expect(screen.getByText(/0 msgs/)).toBeTruthy(),
    )
    expect(screen.getByText(/↑ 0 sent/)).toBeTruthy()
    expect(screen.getByText(/↓ 0 received/)).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// Progress bar
// ---------------------------------------------------------------------------

describe('StatsWidget — progress bar', () => {
  it('renders the sent/received bar when total > 0', async () => {
    stubStats({ enabled: true, date_range: '30d', sent_total: 60, received_total: 40 })
    renderWidget()
    await waitFor(() =>
      expect(screen.getByLabelText(/% sent/)).toBeTruthy(),
    )
    const bar = screen.getByLabelText(/% sent/)
    expect(bar.getAttribute('aria-label')).toContain('60%')
    expect((bar as HTMLElement).style.width).toBe('60%')
  })

  it('omits the progress bar when total is 0', async () => {
    stubStats({ enabled: true, date_range: '30d', sent_total: 0, received_total: 0 })
    renderWidget()
    await waitFor(() =>
      expect(screen.getByText(/0 msgs/)).toBeTruthy(),
    )
    expect(screen.queryByLabelText(/% sent/)).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Top contacts
// ---------------------------------------------------------------------------

describe('StatsWidget — top contacts', () => {
  it('renders top contacts in order', async () => {
    stubStats({
      enabled: true,
      date_range: '30d',
      sent_total: 10,
      received_total: 10,
      top_contacts: [
        { name: 'Alice', handle: '+1111', count: 50 },
        { name: 'Bob', handle: '+2222', count: 30 },
        { name: 'Carol', handle: '+3333', count: 10 },
      ],
    })
    renderWidget()
    await waitFor(() => expect(screen.getByText('Alice')).toBeTruthy())
    expect(screen.getByText('Bob')).toBeTruthy()
    expect(screen.getByText('Carol')).toBeTruthy()
    expect(screen.getByText('50')).toBeTruthy()
    expect(screen.getByText('30')).toBeTruthy()
    expect(screen.getByText('10')).toBeTruthy()
  })

  it('clips top_contacts to at most 3 entries', async () => {
    stubStats({
      enabled: true,
      date_range: '30d',
      sent_total: 10,
      received_total: 10,
      top_contacts: [
        { name: 'Alice', handle: '+1111', count: 50 },
        { name: 'Bob', handle: '+2222', count: 30 },
        { name: 'Carol', handle: '+3333', count: 10 },
        { name: 'Dave', handle: '+4444', count: 5 },
        { name: 'Eve', handle: '+5555', count: 2 },
      ],
    })
    renderWidget()
    await waitFor(() => expect(screen.getByText('Alice')).toBeTruthy())
    expect(screen.queryByText('Dave')).toBeNull()
    expect(screen.queryByText('Eve')).toBeNull()
  })

  it('omits the contacts section when top_contacts is empty', async () => {
    stubStats({
      enabled: true,
      date_range: '30d',
      sent_total: 10,
      received_total: 10,
      top_contacts: [],
    })
    renderWidget()
    await waitFor(() => expect(screen.getByText(/↑ 10 sent/)).toBeTruthy())
    // No contact names rendered
    expect(screen.queryByTitle(/\+/)).toBeNull()
  })

  it('omits the contacts section when top_contacts is absent', async () => {
    stubStats({ enabled: true, date_range: '30d', sent_total: 5, received_total: 5 })
    renderWidget()
    await waitFor(() => expect(screen.getByText(/↑ 5 sent/)).toBeTruthy())
    expect(screen.queryByTitle(/\+/)).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Fetch mechanics
// ---------------------------------------------------------------------------

describe('StatsWidget — fetch mechanics', () => {
  it('fetches /api/ui/stats with credentials: same-origin', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ enabled: true, date_range: '30d', sent_total: 1, received_total: 1 }),
    } as Response)
    vi.stubGlobal('fetch', fetchMock)
    renderWidget()
    await waitFor(() => expect(screen.getByRole('complementary')).toBeTruthy())
    expect(fetchMock).toHaveBeenCalledWith('/api/ui/stats', { credentials: 'same-origin' })
  })
})
