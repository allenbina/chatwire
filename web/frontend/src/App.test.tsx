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
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { ChatPage } from './pages/ChatPage'

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
    renderWithProviders()
    // The Layout sidebar header should always be present.
    expect(screen.getAllByText('Chatwire').length).toBeGreaterThan(0)
  })

  it('shows the empty-state message on the index route', () => {
    renderWithProviders()
    expect(
      screen.getByText(/select a conversation/i),
    ).toBeInTheDocument()
  })
})
