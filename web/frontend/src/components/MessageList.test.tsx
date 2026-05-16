/**
 * Vitest unit tests for MessageList.
 *
 * Key regression guarded: the EMPTY_OPTIMISTIC fix (commit d1d21fe).
 * Before the fix, `useChatStore((s) => s.optimistic[handle] ?? [])` returned a
 * new [] on every render when no optimistic messages existed, causing React's
 * "Maximum update depth exceeded" crash.  After the fix, a stable sentinel
 * reference is returned, so no re-renders are triggered.
 *
 * Covers:
 *   - renders loading state initially
 *   - renders "No messages yet." when server returns empty list (no crash)
 *   - renders message bubbles when server returns messages
 *   - renders "Failed to load messages." on network error
 *   - renders with optimistic messages appended after server messages
 *   - EMPTY_OPTIMISTIC: handle absent from store uses stable reference (no loop)
 *   - message rows use --spacing-message CSS variable for vertical padding
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MessageList } from './MessageList'
import { useChatStore } from '../store'
import type { Message } from '../api'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderMessageList(handle: string, qc = makeQC()) {
  return render(
    <QueryClientProvider client={qc}>
      <MessageList handle={handle} />
    </QueryClientProvider>,
  )
}

/** Minimal valid Message fixture (DM, text only). */
function makeMessage(overrides: Partial<Message> & { rowid: number; text: string }): Message {
  return {
    date: 1_000_000,
    from_me: false,
    ts: '12:00 PM',
    attachments: [],
    link_preview: null,
    service: 'iMessage',
    ...overrides,
  }
}

/** Return a minimal fake Response for stubbing fetch. */
function messagesResponse(messages: Message[] = [], has_more = false) {
  return {
    ok: true,
    status: 200,
    json: async () => ({ messages, has_more }),
    text: async () => JSON.stringify({ messages, has_more }),
  } as unknown as Response
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.restoreAllMocks()
  // Reset the zustand store between tests so optimistic state doesn't leak.
  useChatStore.setState({ optimistic: {}, activeHandle: null })
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('MessageList', () => {
  it('shows loading state before fetch resolves', () => {
    // Never-resolving fetch keeps the component in loading state.
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
    renderMessageList('+15550001111')
    expect(screen.getByText(/loading messages/i)).toBeInTheDocument()
  })

  it('shows "No messages yet." when server returns empty list — no infinite loop', async () => {
    // REGRESSION TEST: the EMPTY_OPTIMISTIC fix.
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(messagesResponse([])))

    renderMessageList('+15550001111')

    await waitFor(() => {
      expect(screen.getByText(/no messages yet/i)).toBeInTheDocument()
    })

    expect(screen.queryByText(/loading messages/i)).not.toBeInTheDocument()
  })

  it('renders message bubbles returned by the server', async () => {
    const messages = [
      makeMessage({ rowid: 1, text: 'Hello from server', from_me: false }),
      makeMessage({ rowid: 2, text: 'Reply from me', from_me: true }),
    ]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(messagesResponse(messages)))

    renderMessageList('+15550001111')

    await waitFor(() => {
      expect(screen.getByText('Hello from server')).toBeInTheDocument()
    })
    expect(screen.getByText('Reply from me')).toBeInTheDocument()
  })

  it('shows error state when fetch rejects', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')))

    renderMessageList('+15550001111')

    await waitFor(() => {
      expect(screen.getByText(/failed to load messages/i)).toBeInTheDocument()
    })
  })

  it('renders optimistic messages from the store after server messages', async () => {
    const handle = '+15550002222'
    const serverMsg = makeMessage({ rowid: 10, text: 'Server message', from_me: false })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(messagesResponse([serverMsg])))

    // Seed the store with an optimistic message before rendering.
    useChatStore.setState({
      optimistic: {
        [handle]: [
          {
            ...makeMessage({ rowid: -1, text: 'Optimistic message', from_me: true }),
            pending: true,
          },
        ],
      },
    })

    renderMessageList(handle)

    await waitFor(() => {
      expect(screen.getByText('Server message')).toBeInTheDocument()
    })
    expect(screen.getByText('Optimistic message')).toBeInTheDocument()
  })

  it('message rows use --spacing-message CSS variable for vertical padding', async () => {
    const messages = [
      makeMessage({ rowid: 1, text: 'Check spacing', from_me: false }),
    ]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(messagesResponse(messages)))
    const { container } = renderMessageList('+15550001111')

    await waitFor(() => {
      expect(screen.getByText('Check spacing')).toBeInTheDocument()
    })

    const rowDiv = container.querySelector('[data-rowid]')
    expect(rowDiv).not.toBeNull()
    const style = rowDiv!.getAttribute('style')!
    expect(style).toContain('--spacing-message')
  })

  it('uses stable EMPTY_OPTIMISTIC reference for handles absent from store', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(messagesResponse([])))

    const handle = '+15550003333'
    expect(useChatStore.getState().optimistic[handle]).toBeUndefined()

    renderMessageList(handle)

    await waitFor(() => {
      expect(screen.getByText(/no messages yet/i)).toBeInTheDocument()
    })
  })
})
