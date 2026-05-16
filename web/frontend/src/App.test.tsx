/**
 * Smoke tests for the Phase 2 React app.
 *
 * Tests verify that the router renders without crashing and that key
 * page-level elements appear on the expected routes. Network calls are
 * mocked via global fetch stubs so tests don't need a live server.
 *
 * We use MemoryRouter instead of BrowserRouter to control the initial
 * URL and avoid basename issues in the test environment.
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { ChatPage } from './pages/ChatPage'
import type { HandleConversation } from './api'

// Stub global fetch so react-query and api.ts don't hit the network.
beforeEach(() => {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      ok: true,
      release: '2.0.0-alpha.1',
      conversations: [],
      messages: [],
      has_more: false,
      themes: ['dracula'],
      current: 'dracula',
    }),
    text: async () => '{}',
  }) as unknown as typeof fetch
})

function renderWithProviders(initialPath = '/') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/chat/:handle" element={<ChatPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('App', () => {
  it('renders without crashing', () => {
    // jsdom has no layout, so set innerWidth to trigger desktop path
    Object.defineProperty(window, 'innerWidth', { value: 1024, configurable: true })
    renderWithProviders()
    // ChatPage should render (Layout wraps it)
    expect(document.querySelector('[aria-label="Chat"]')).not.toBeNull()
  })

  it('shows the empty-state message on the index route when no conversations exist', async () => {
    renderWithProviders()
    // conversations: [] → AutoRedirect falls back to EmptyState
    await screen.findByText(/select a conversation/i)
  })

  it('auto-redirects to the first conversation when conversations exist (desktop)', async () => {
    // Ensure desktop viewport so AutoRedirect doesn't skip
    Object.defineProperty(window, 'innerWidth', { value: 1024, configurable: true })
    const mockConv: HandleConversation = {
      kind: 'handle',
      handle: '+15551234567',
      name: 'Alice',
      preview: 'Hello there',
      has_media: false,
      last_dt: 1_700_000_000,
      last_rowid: 100,
      last_seen_rowid: 0,
      n: 1,
      unseen: true,
      all_handles: ['+15551234567'],
      is_favorite: false,
      last: 'handle',
    }

    vi.mocked(globalThis.fetch).mockImplementation((url) => {
      const u = String(url)
      if (u.includes('/conversations')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ conversations: [mockConv] }),
          text: async () => '{}',
        } as unknown as Response)
      }
      // messages, update-check, etc.
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({
          messages: [],
          has_more: false,
          ok: true,
          release: '1.0.0',
          themes: [],
          current: '',
        }),
        text: async () => '{}',
      } as unknown as Response)
    })

    renderWithProviders('/')

    // After the redirect, the conversation header should show Alice's name.
    await screen.findByText('Alice')

    // EmptyState should be gone.
    await waitFor(() => {
      expect(screen.queryByText(/select a conversation/i)).not.toBeInTheDocument()
    })
  })
})
