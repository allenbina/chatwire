/**
 * Vitest unit tests for ConversationList.
 *
 * Covers:
 *   - shows loading state while fetch is pending
 *   - shows "No conversations yet." when server returns empty list
 *   - shows "Failed to load conversations." on network error
 *   - renders conversation names and previews
 *   - clicking a row calls navigate with /chat/:encodedHandle
 *   - clicking a row sets activeHandle in the zustand store
 *   - clicking a row closes the mobile sidebar (setSidebarOpen(false))
 *   - active conversation row has aria-current="page"
 *   - group conversation renders [G] prefix
 *   - unread badge renders when n > 0
 *   - favourite star renders when is_favorite is true
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ConversationList } from './ConversationList'
import { fetchConversations } from '../api'
import { useChatStore } from '../store'
import type { HandleConversation, GroupConversation } from '../api'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// vi.hoisted ensures these refs are created before vi.mock is hoisted to the
// top of the module, so the mock factories can close over them safely.
const { mockNavigate, mockUseParams } = vi.hoisted(() => ({
  mockNavigate: vi.fn(),
  mockUseParams: vi.fn().mockReturnValue({ handle: '' }),
}))

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useParams: mockUseParams,
  }
})

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    fetchConversations: vi.fn(),
  }
})

const mockedFetch = vi.mocked(fetchConversations)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderList(qc = makeQC()) {
  return render(
    <QueryClientProvider client={qc}>
      <ConversationList />
    </QueryClientProvider>,
  )
}

function makeHandleConvo(overrides?: Partial<HandleConversation>): HandleConversation {
  return {
    kind: 'handle',
    handle: '+15550001111',
    name: 'Alice',
    preview: 'Hey there',
    has_media: false,
    last_dt: 1_000_000,
    n: 0,
    all_handles: ['+15550001111'],
    is_favorite: false,
    last: '12:00 PM',
    ...overrides,
  }
}

function makeGroupConvo(overrides?: Partial<GroupConversation>): GroupConversation {
  return {
    kind: 'group',
    guid: 'chat00112233-4455-6677-8899-aabbccddeeff',
    name: 'Team Chat',
    preview: 'See you at 3',
    has_media: false,
    last_dt: 2_000_000,
    n: 0,
    is_favorite: false,
    last: '1:00 PM',
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks()
  mockUseParams.mockReturnValue({ handle: '' })
  useChatStore.setState({ activeHandle: null, sidebarOpen: false, optimistic: {} })
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ConversationList', () => {
  it('shows loading state before fetch resolves', () => {
    mockedFetch.mockReturnValue(new Promise(() => {}))
    renderList()
    expect(screen.getByText(/loading conversations/i)).toBeInTheDocument()
  })

  it('shows "No conversations yet." when server returns empty list', async () => {
    mockedFetch.mockResolvedValue([])
    renderList()
    await waitFor(() => {
      expect(screen.getByText(/no conversations yet/i)).toBeInTheDocument()
    })
  })

  it('shows "Failed to load conversations." on error', async () => {
    mockedFetch.mockRejectedValue(new Error('network down'))
    renderList()
    await waitFor(() => {
      expect(screen.getByText(/failed to load conversations/i)).toBeInTheDocument()
    })
  })

  it('renders conversation names and previews', async () => {
    mockedFetch.mockResolvedValue([
      makeHandleConvo({ name: 'Alice', preview: 'Hey there' }),
      makeHandleConvo({ handle: '+15550002222', name: 'Bob', preview: 'Sounds good' }),
    ])
    renderList()
    await waitFor(() => {
      expect(screen.getByText('Alice')).toBeInTheDocument()
    })
    expect(screen.getByText('Bob')).toBeInTheDocument()
    expect(screen.getByText('Hey there')).toBeInTheDocument()
    expect(screen.getByText('Sounds good')).toBeInTheDocument()
  })

  it('clicking a row calls navigate with /chat/:encodedHandle', async () => {
    const user = userEvent.setup()
    const convo = makeHandleConvo({ handle: '+15550001111', name: 'Alice' })
    mockedFetch.mockResolvedValue([convo])
    renderList()

    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /alice/i }))

    expect(mockNavigate).toHaveBeenCalledOnce()
    expect(mockNavigate).toHaveBeenCalledWith('/chat/%2B15550001111')
  })

  it('clicking a row sets activeHandle in the zustand store', async () => {
    const user = userEvent.setup()
    const convo = makeHandleConvo({ handle: '+15550001111', name: 'Alice' })
    mockedFetch.mockResolvedValue([convo])
    renderList()

    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /alice/i }))

    expect(useChatStore.getState().activeHandle).toBe('+15550001111')
  })

  it('clicking a row closes the mobile sidebar', async () => {
    const user = userEvent.setup()
    useChatStore.setState({ sidebarOpen: true })
    const convo = makeHandleConvo({ name: 'Alice' })
    mockedFetch.mockResolvedValue([convo])
    renderList()

    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /alice/i }))

    expect(useChatStore.getState().sidebarOpen).toBe(false)
  })

  it('active conversation row has aria-current="page"', async () => {
    // Simulate the router reporting that +15550001111 is the active handle.
    const encoded = encodeURIComponent('+15550001111')
    mockUseParams.mockReturnValue({ handle: encoded })

    mockedFetch.mockResolvedValue([
      makeHandleConvo({ handle: '+15550001111', name: 'Alice' }),
      makeHandleConvo({ handle: '+15550002222', name: 'Bob' }),
    ])
    renderList()

    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())

    const aliceBtn = screen.getByRole('button', { name: /alice/i })
    const bobBtn = screen.getByRole('button', { name: /bob/i })

    expect(aliceBtn).toHaveAttribute('aria-current', 'page')
    expect(bobBtn).not.toHaveAttribute('aria-current')
  })

  it('group conversation renders [G] prefix and navigates to /chat/:guid', async () => {
    const user = userEvent.setup()
    const convo = makeGroupConvo({ guid: 'group-abc', name: 'Team Chat' })
    mockedFetch.mockResolvedValue([convo])
    renderList()

    await waitFor(() => expect(screen.getByText('Team Chat')).toBeInTheDocument())
    // [G] tag is rendered as a separate span next to the name.
    expect(screen.getByText('[G]')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /team chat/i }))
    expect(mockNavigate).toHaveBeenCalledWith('/chat/group-abc')
  })

  it('renders unread badge when n > 0', async () => {
    mockedFetch.mockResolvedValue([makeHandleConvo({ name: 'Alice', n: 5 })])
    renderList()
    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  it('truncates unread badge to "99+" when n > 99', async () => {
    mockedFetch.mockResolvedValue([makeHandleConvo({ name: 'Alice', n: 150 })])
    renderList()
    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())
    expect(screen.getByText('99+')).toBeInTheDocument()
  })

  it('renders favourite star when is_favorite is true', async () => {
    mockedFetch.mockResolvedValue([makeHandleConvo({ name: 'Alice', is_favorite: true })])
    renderList()
    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())
    // The ★ glyph is rendered as &#9733; (Unicode star) in a sibling span.
    expect(screen.getByText('Alice').closest('button')).toHaveTextContent('★')
  })
})
