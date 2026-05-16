/**
 * Vitest unit tests for PopoutPage — minimal popout chat view.
 *
 * Covers:
 *   - No handle: shows "No conversation specified" message
 *   - No handle: does not render MessageList or ComposeBox
 *   - ?handle=X: header shows handle, MessageList + ComposeBox rendered with handle
 *   - ?handle=X: MessageList isGroup=false for a plain handle
 *   - ?chat=X: isGroup=true, header shows chat value
 *   - Group handle (semicolons in ?handle): isGroup=true, header shows last segment
 *   - ?chat=X with semicolons: header shows last segment
 *   - Theme: applyTheme called with stored theme on mount
 *   - Theme: falls back to "dracula" when localStorage has no theme
 *   - SSE matching handle: invalidates queries + clears optimistic (rowid present)
 *   - SSE different handle: no query invalidation, no clearOptimistic
 *   - SSE no rowid: invalidates queries but no clearOptimistic call
 *   - SSE URL-encoded handle: decodeURIComponent comparison works
 */
import { render, screen, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { PopoutPage } from './PopoutPage'
import { useSSE } from '../hooks/useSSE'
import { applyTheme } from '../hooks/useTheme'
import { useChatStore } from '../store'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../components/MessageList', () => ({
  MessageList: ({ handle, isGroup }: { handle: string; isGroup: boolean }) => (
    <div
      data-testid="message-list"
      data-handle={handle}
      data-is-group={String(isGroup)}
    />
  ),
}))

vi.mock('../components/ComposeBox', () => ({
  ComposeBox: ({ handle, isGroup }: { handle: string; isGroup?: boolean }) => (
    <div
      data-testid="compose-box"
      data-handle={handle}
      data-is-group={String(isGroup ?? false)}
    />
  ),
}))

vi.mock('../hooks/useTheme', () => ({
  applyTheme: vi.fn(),
}))

vi.mock('../hooks/useSSE', () => ({
  useSSE: vi.fn(),
}))

vi.mock('../store', () => ({
  useChatStore: vi.fn(),
}))

const mockedUseSSE = vi.mocked(useSSE)
const mockedApplyTheme = vi.mocked(applyTheme)
const mockedUseChatStore = vi.mocked(useChatStore)

const mockClearOptimistic = vi.fn()

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderPage(search = '', qc = makeQC()) {
  render(
    <MemoryRouter initialEntries={[`/popout${search}`]}>
      <QueryClientProvider client={qc}>
        <PopoutPage />
      </QueryClientProvider>
    </MemoryRouter>,
  )
  return qc
}

/** Return the onEvent callback from the most recent useSSE call. */
function getLastOnEvent() {
  const calls = mockedUseSSE.mock.calls
  return calls[calls.length - 1][0].onEvent
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  localStorage.clear()
  mockClearOptimistic.mockReset()
  mockedUseSSE.mockReset()
  mockedApplyTheme.mockReset()
  mockedUseChatStore.mockReset()
  mockedUseChatStore.mockImplementation(
    // @ts-expect-error — minimal mock: only clearOptimistic needed for this test
    (selector: (s: { clearOptimistic: typeof mockClearOptimistic }) => unknown) =>
      selector({ clearOptimistic: mockClearOptimistic }),
  )
  mockedUseSSE.mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// No handle
// ---------------------------------------------------------------------------

describe('PopoutPage — no handle', () => {
  it('shows "No conversation specified" when neither ?handle nor ?chat is provided', () => {
    renderPage('')
    expect(screen.getByText(/No conversation specified/i)).toBeInTheDocument()
  })

  it('does not render MessageList when handle is absent', () => {
    renderPage('')
    expect(screen.queryByTestId('message-list')).toBeNull()
  })

  it('does not render ComposeBox when handle is absent', () => {
    renderPage('')
    expect(screen.queryByTestId('compose-box')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// DM conversation (?handle=X)
// ---------------------------------------------------------------------------

describe('PopoutPage — ?handle=X (DM)', () => {
  it('renders the handle in the header', () => {
    renderPage('?handle=alice')
    expect(screen.getByText('alice')).toBeInTheDocument()
  })

  it('passes the handle to MessageList', () => {
    renderPage('?handle=alice')
    expect(screen.getByTestId('message-list')).toHaveAttribute('data-handle', 'alice')
  })

  it('renders MessageList with isGroup=false for a plain handle', () => {
    renderPage('?handle=alice')
    expect(screen.getByTestId('message-list')).toHaveAttribute('data-is-group', 'false')
  })

  it('passes the handle to ComposeBox', () => {
    renderPage('?handle=alice')
    expect(screen.getByTestId('compose-box')).toHaveAttribute('data-handle', 'alice')
  })
})

// ---------------------------------------------------------------------------
// Group via ?chat=X
// ---------------------------------------------------------------------------

describe('PopoutPage — ?chat=X', () => {
  it('renders MessageList with isGroup=true for the ?chat param', () => {
    renderPage('?chat=FamilyGroup')
    expect(screen.getByTestId('message-list')).toHaveAttribute('data-is-group', 'true')
  })

  it('renders the chat value in the header', () => {
    renderPage('?chat=FamilyGroup')
    expect(screen.getByText('FamilyGroup')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Group handle (semicolons in ?handle)
// ---------------------------------------------------------------------------

describe('PopoutPage — group handle (semicolons in ?handle)', () => {
  it('isGroup=true when ?handle contains a semicolon', () => {
    renderPage('?handle=alice%3Bbob%3BFriends')
    expect(screen.getByTestId('message-list')).toHaveAttribute('data-is-group', 'true')
  })

  it('header shows the last semicolon-delimited segment', () => {
    renderPage('?handle=alice%3Bbob%3BFriends')
    expect(screen.getByText('Friends')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// ?chat=X with semicolons
// ---------------------------------------------------------------------------

describe('PopoutPage — ?chat=X with semicolons', () => {
  it('header shows the last semicolon-delimited segment of the ?chat value', () => {
    renderPage('?chat=alice%3Bbob%3BFamilyChat')
    expect(screen.getByText('FamilyChat')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Theme
// ---------------------------------------------------------------------------

describe('PopoutPage — theme', () => {
  it('calls applyTheme with the stored theme from localStorage', () => {
    localStorage.setItem('chatwire-theme', 'nord')
    renderPage('?handle=alice')
    expect(mockedApplyTheme).toHaveBeenCalledWith('nord')
  })

  it('falls back to "dracula" when no theme is saved in localStorage', () => {
    renderPage('?handle=alice')
    expect(mockedApplyTheme).toHaveBeenCalledWith('dracula')
  })
})

// ---------------------------------------------------------------------------
// SSE event handling
// ---------------------------------------------------------------------------

describe('PopoutPage — SSE', () => {
  it('invalidates messages query when SSE event handle matches the active handle', () => {
    const qc = makeQC()
    vi.spyOn(qc, 'invalidateQueries')
    renderPage('?handle=alice', qc)
    const onEvent = getLastOnEvent()
    act(() => {
      onEvent({ handle: 'alice', rowid: 1 })
    })
    expect(qc.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ['messages', 'alice'],
    })
  })

  it('calls clearOptimistic with handle and rowid when rowid is present', () => {
    renderPage('?handle=alice')
    const onEvent = getLastOnEvent()
    act(() => {
      onEvent({ handle: 'alice', rowid: 42 })
    })
    expect(mockClearOptimistic).toHaveBeenCalledWith('alice', 42)
  })

  it('does not invalidate queries when SSE event handle does not match', () => {
    const qc = makeQC()
    vi.spyOn(qc, 'invalidateQueries')
    renderPage('?handle=alice', qc)
    const onEvent = getLastOnEvent()
    act(() => {
      onEvent({ handle: 'bob', rowid: 1 })
    })
    expect(qc.invalidateQueries).not.toHaveBeenCalled()
  })

  it('does not call clearOptimistic when event rowid is null/undefined', () => {
    const qc = makeQC()
    vi.spyOn(qc, 'invalidateQueries')
    renderPage('?handle=alice', qc)
    const onEvent = getLastOnEvent()
    act(() => {
      onEvent({ handle: 'alice' })
    })
    expect(mockClearOptimistic).not.toHaveBeenCalled()
    expect(qc.invalidateQueries).toHaveBeenCalled()
  })

  it('matches URL-encoded handle in SSE event via decodeURIComponent', () => {
    const qc = makeQC()
    vi.spyOn(qc, 'invalidateQueries')
    // URL param decoded by router → handle = 'alice@example.com'
    renderPage('?handle=alice%40example.com', qc)
    const onEvent = getLastOnEvent()
    act(() => {
      // Event carries the percent-encoded form
      onEvent({ handle: 'alice%40example.com' })
    })
    expect(qc.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ['messages', 'alice@example.com'],
    })
  })
})
