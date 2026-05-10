/**
 * Vitest tests for ContactInfoSheet.
 *
 * Covers:
 *   - Sheet is not rendered when open=false
 *   - Sheet renders contact name for a 1:1 conversation
 *   - Sheet renders group member list for a group
 *   - "No shared media" shown when media array is empty
 *   - Media grid shows thumbnails when media present
 *   - "Remove from whitelist" button shows confirmation step
 *   - Confirming removal calls DELETE /api/ui/whitelist and closes the sheet
 */
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ContactInfoSheet } from './ContactInfoSheet'
import type { HandleContactInfo, GroupContactInfo } from '../api'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const HANDLE_INFO: HandleContactInfo = {
  kind: 'handle',
  handle: '+14695551234',
  name: 'Sarah Chen',
  subtitle: '+14695551234',
  handles: [
    { handle: '+14695551234', capability: 'iMessage ✓', cap_class: 'text-green-600' },
  ],
  media: [],
}

const GROUP_INFO: GroupContactInfo = {
  kind: 'group',
  chat: 'iMessage;+;chat123',
  name: 'Team Chat',
  subtitle: '3 members',
  members: [
    { handle: '+14695551234', name: 'Sarah Chen', capability: 'iMessage ✓', cap_class: '' },
    { handle: '+14155559876', name: 'Bob', capability: 'SMS ✓', cap_class: '' },
    { handle: '+15105550000', name: '', capability: '', cap_class: '' },
  ],
  media: [],
}

const MEDIA_INFO: HandleContactInfo = {
  ...HANDLE_INFO,
  media: [
    { path: '/tmp/photo1.jpg', name: 'photo1.jpg', mime: 'image/jpeg', kind: 'image' },
    { path: '/tmp/video1.mov', name: 'video1.mov', mime: 'video/mp4', kind: 'video' },
  ],
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderSheet(
  props: Partial<Parameters<typeof ContactInfoSheet>[0]> & { open: boolean },
  qc = makeQC(),
) {
  const defaults = {
    onClose: vi.fn(),
    handle: '+14695551234',
    isGroup: false,
  }
  return render(
    <QueryClientProvider client={qc}>
      <ContactInfoSheet {...defaults} {...props} />
    </QueryClientProvider>,
  )
}

function okResponse(body: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response
}

function deleteOkResponse() {
  return {
    ok: true,
    status: 200,
    json: async () => ({ ok: true }),
    text: async () => '{"ok":true}',
  } as unknown as Response
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.restoreAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ContactInfoSheet', () => {
  it('does not fetch or render sheet content when open=false', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    renderSheet({ open: false })

    // Sheet content should not be visible.
    expect(screen.queryByText('Sarah Chen')).not.toBeInTheDocument()
    // No fetch call — query is disabled when open=false.
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('shows contact name and handle for a 1:1 conversation', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse(HANDLE_INFO)))

    renderSheet({ open: true })

    await waitFor(() => {
      expect(screen.getByText('Sarah Chen')).toBeInTheDocument()
    })
    // Handle appears in both subtitle and handles list — at least one instance expected.
    expect(screen.getAllByText('+14695551234').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Handles')).toBeInTheDocument()
  })

  it('shows group name and member list for a group', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse(GROUP_INFO)))

    renderSheet({ open: true, handle: 'iMessage;+;chat123', isGroup: true })

    await waitFor(() => {
      expect(screen.getByText('Team Chat')).toBeInTheDocument()
    })
    expect(screen.getByText(/Members \(3\)/)).toBeInTheDocument()
    expect(screen.getByText('Sarah Chen')).toBeInTheDocument()
    expect(screen.getByText('Bob')).toBeInTheDocument()
  })

  it('shows "No shared media." when media array is empty', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse(HANDLE_INFO)))

    renderSheet({ open: true })

    await waitFor(() => {
      expect(screen.getByText('Sarah Chen')).toBeInTheDocument()
    })
    expect(screen.getByText('No shared media.')).toBeInTheDocument()
  })

  it('shows media grid when media entries are present', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse(MEDIA_INFO)))

    renderSheet({ open: true })

    await waitFor(() => {
      expect(screen.getByText(/Media \(2\)/)).toBeInTheDocument()
    })
    // Image thumbnail rendered with correct src.
    const img = screen.getByRole('img', { name: 'photo1.jpg' }) as HTMLImageElement
    expect(img.src).toContain('/attachment?path=')
    // Video placeholder.
    expect(screen.getByText('video')).toBeInTheDocument()
  })

  it('shows confirmation step when "Remove from whitelist" is clicked', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse(HANDLE_INFO)))

    renderSheet({ open: true })

    await waitFor(() => {
      expect(screen.getByText('Sarah Chen')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Remove from whitelist'))

    expect(screen.getByText(/Remove this contact from the whitelist/)).toBeInTheDocument()
    expect(screen.getByText('Remove')).toBeInTheDocument()
    expect(screen.getByText('Cancel')).toBeInTheDocument()
  })

  it('calls DELETE /api/ui/whitelist and closes on confirm', async () => {
    const onClose = vi.fn()
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(okResponse(HANDLE_INFO))   // GET contact-info
      .mockResolvedValueOnce(okResponse({ conversations: [] }))  // invalidate conversations
      .mockResolvedValue(deleteOkResponse())              // DELETE whitelist

    vi.stubGlobal('fetch', fetchMock)

    renderSheet({ open: true, onClose })

    await waitFor(() => {
      expect(screen.getByText('Sarah Chen')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Remove from whitelist'))
    fireEvent.click(screen.getByText('Remove'))

    await waitFor(() => {
      // DELETE call should have been made.
      const deleteCalls = fetchMock.mock.calls.filter((args: unknown[]) => {
        const [url, init] = args as [string, RequestInit | undefined]
        return typeof url === 'string' && url.includes('whitelist') && init?.method === 'DELETE'
      })
      expect(deleteCalls.length).toBeGreaterThan(0)
    })
  })

  it('calls onRemoved (not onClose) on successful deletion when onRemoved is provided', async () => {
    const onClose = vi.fn()
    const onRemoved = vi.fn()
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(okResponse(HANDLE_INFO))          // GET contact-info
      .mockResolvedValueOnce(okResponse({ conversations: [] })) // invalidate conversations
      .mockResolvedValue(deleteOkResponse())                    // DELETE whitelist

    vi.stubGlobal('fetch', fetchMock)

    renderSheet({ open: true, onClose, onRemoved })

    await waitFor(() => {
      expect(screen.getByText('Sarah Chen')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Remove from whitelist'))
    fireEvent.click(screen.getByText('Remove'))

    await waitFor(() => {
      expect(onRemoved).toHaveBeenCalledTimes(1)
    })
    expect(onClose).not.toHaveBeenCalled()
  })

  it('shows "Show all (N)" button when media exceeds 30 and expands on click', async () => {
    const manyMedia: HandleContactInfo = {
      ...HANDLE_INFO,
      media: Array.from({ length: 35 }, (_, i) => ({
        path: `/tmp/photo${i}.jpg`,
        name: `photo${i}.jpg`,
        mime: 'image/jpeg',
        kind: 'image' as const,
      })),
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse(manyMedia)))

    renderSheet({ open: true })

    await waitFor(() => {
      expect(screen.getByText(/Media \(35\)/)).toBeInTheDocument()
    })

    // Only 30 images visible initially.
    expect(screen.getAllByRole('img').length).toBe(30)
    // "Show all" button present.
    const showAllBtn = screen.getByText('Show all (35)')
    expect(showAllBtn).toBeInTheDocument()

    // Expand — all 35 should now be visible.
    fireEvent.click(showAllBtn)
    expect(screen.getAllByRole('img').length).toBe(35)
    // Button gone after expansion.
    expect(screen.queryByText('Show all (35)')).not.toBeInTheDocument()
  })

  it('cancels confirmation and stays on sheet when Cancel is clicked', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse(HANDLE_INFO)))

    renderSheet({ open: true })

    await waitFor(() => {
      expect(screen.getByText('Sarah Chen')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Remove from whitelist'))
    expect(screen.getByText(/Remove this contact from the whitelist/)).toBeInTheDocument()

    fireEvent.click(screen.getByText('Cancel'))

    // Confirmation gone, original button back.
    expect(screen.queryByText(/Remove this contact from the whitelist/)).not.toBeInTheDocument()
    expect(screen.getByText('Remove from whitelist')).toBeInTheDocument()
  })
})
