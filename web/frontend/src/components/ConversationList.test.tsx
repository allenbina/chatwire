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
 *   - unseen dot renders based on Chatwire read state (not iMessage is_read)
 *   - favourite star renders when is_favorite is true
 *   - "Mark all read" CheckCheck icon is in Layout footer (not ConversationList)
 *   - Shift+Escape triggers markAllSeen
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

// Radix-ui AvatarImage hides itself from the DOM when the image fails to load.
// In jsdom there's no real network so images fail synchronously. Stub the
// radix primitive so AvatarImage always renders an <img> for src-checking.
vi.mock('@radix-ui/react-avatar', async () => {
  const React = await import('react')
  return {
    Root: ({ children, className }: React.HTMLAttributes<HTMLDivElement>) =>
      React.createElement('div', { className }, children),
    Image: ({ src, alt, className }: React.ImgHTMLAttributes<HTMLImageElement>) =>
      React.createElement('img', { src, alt, className }),
    Fallback: ({ children, className }: React.HTMLAttributes<HTMLSpanElement>) =>
      React.createElement('span', { className }, children),
  }
})

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    fetchConversations: vi.fn(),
    markAllSeen: vi.fn().mockResolvedValue(undefined),
  }
})

const mockedFetch = vi.mocked(fetchConversations)
// Import after mock so we get the vi.fn() version
import { markAllSeen } from '../api'
const mockedMarkAllSeen = vi.mocked(markAllSeen)

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
    last_rowid: 0,
    last_seen_rowid: 0,
    n: 0,
    unseen: false,
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
    last_rowid: 0,
    last_seen_rowid: 0,
    n: 0,
    unseen: false,
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

  it('clicking a row calls navigate with /chat/:slug', async () => {
    const user = userEvent.setup()
    const convo = makeHandleConvo({ handle: '+15550001111', name: 'Alice' })
    mockedFetch.mockResolvedValue([convo])
    renderList()

    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /alice/i }))

    expect(mockNavigate).toHaveBeenCalledOnce()
    expect(mockNavigate).toHaveBeenCalledWith('/chat/alice')
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
    // Simulate the router reporting the slug "alice" as the active param.
    mockUseParams.mockReturnValue({ handle: 'alice' })

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

  it('group conversation renders [G] prefix and navigates to /chat/:slug', async () => {
    const user = userEvent.setup()
    const convo = makeGroupConvo({ guid: 'group-abc', name: 'Team Chat' })
    mockedFetch.mockResolvedValue([convo])
    renderList()

    await waitFor(() => expect(screen.getByText('Team Chat')).toBeInTheDocument())
    // [G] tag is rendered as a separate span next to the name.
    expect(screen.getByText('[G]')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /team chat/i }))
    expect(mockNavigate).toHaveBeenCalledWith('/chat/team-chat')
  })

  it('renders unseen dot when unseen is true', async () => {
    mockedFetch.mockResolvedValue([makeHandleConvo({ name: 'Alice', n: 5, unseen: true })])
    renderList()
    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())
    expect(screen.getByLabelText('New messages')).toBeInTheDocument()
  })

  it('does not render unseen dot when unseen is false', async () => {
    mockedFetch.mockResolvedValue([makeHandleConvo({ name: 'Alice', n: 5, unseen: false })])
    renderList()
    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())
    expect(screen.queryByLabelText('New messages')).not.toBeInTheDocument()
  })

  it('renders favourite star when is_favorite is true', async () => {
    mockedFetch.mockResolvedValue([makeHandleConvo({ name: 'Alice', is_favorite: true })])
    renderList()
    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())
    // The ★ glyph is rendered as &#9733; (Unicode star) in a sibling span.
    expect(screen.getByText('Alice').closest('button')).toHaveTextContent('★')
  })

  // NOTE: "Mark all read" CheckCheck icon lives in Layout.tsx sidebar footer (moved Phase 33 Chunk 3).
  // ConversationList no longer renders it — Layout tests cover that behaviour.

  it('"Mark all read" icon is absent from ConversationList regardless of unseen state', async () => {
    mockedFetch.mockResolvedValue([makeHandleConvo({ name: 'Alice', unseen: false, n: 0 })])
    renderList()
    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /mark all read/i })).not.toBeInTheDocument()
  })

  it('Shift+Escape triggers markAllSeen', async () => {
    const user = userEvent.setup()
    mockedFetch.mockResolvedValue([makeHandleConvo({ name: 'Alice', unseen: true, n: 1 })])
    renderList()
    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())
    await user.keyboard('{Shift>}{Escape}{/Shift}')
    await waitFor(() => expect(mockedMarkAllSeen).toHaveBeenCalledOnce())
  })

  it('renders an avatar img with /avatar?handle= src for 1:1 conversations (#34)', async () => {
    mockedFetch.mockResolvedValue([makeHandleConvo({ handle: '+15550001111', name: 'Alice' })])
    const { container } = renderList()
    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())
    const img = container.querySelector('img[src*="/avatar?handle="]')
    expect(img).not.toBeNull()
    expect(img!.getAttribute('src')).toContain(encodeURIComponent('+15550001111'))
  })

  it('does not render an avatar img for group conversations (#34)', async () => {
    mockedFetch.mockResolvedValue([makeGroupConvo({ name: 'Team Chat' })])
    const { container } = renderList()
    await waitFor(() => expect(screen.getByText('Team Chat')).toBeInTheDocument())
    expect(container.querySelector('img[src*="/avatar"]')).toBeNull()
  })

  // ---------------------------------------------------------------------------
  // Theme variable consumption — ensures sidebar uses CSS vars, not hardcoded
  // ---------------------------------------------------------------------------

  it('conversation row buttons use --spacing-sidebar CSS variable for padding', async () => {
    mockedFetch.mockResolvedValue([makeHandleConvo({ name: 'Alice' })])
    renderList()
    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())

    const btn = screen.getByRole('button', { name: /alice/i })
    const style = btn.getAttribute('style')
    expect(style).toContain('--spacing-sidebar')
  })

  it('preview text uses --font-size-sidebar CSS variable for font size', async () => {
    mockedFetch.mockResolvedValue([makeHandleConvo({ name: 'Alice', preview: 'Hello there' })])
    const { container } = renderList()
    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())

    const preview = container.querySelector('[style*="--font-size-sidebar"]')
    expect(preview).not.toBeNull()
  })
})
