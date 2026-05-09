/**
 * Smoke tests for the Phase 2 React app.
 *
 * Tests verify that the router renders without crashing and that key
 * page-level elements appear on the expected routes. Network calls are
 * mocked via MSW or global fetch stubs so tests don't need a live server.
 */
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import App from './App'

// Stub global fetch so react-query and api.ts don't hit the network.
beforeEach(() => {
  global.fetch = vi.fn().mockResolvedValue({
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

describe('App', () => {
  it('renders without crashing', () => {
    render(<App />)
    // The Layout sidebar header should always be present.
    expect(screen.getByText('Chatwire')).toBeInTheDocument()
  })

  it('shows the empty-state message on the index route', () => {
    render(<App />)
    expect(
      screen.getByText(/select a conversation/i),
    ).toBeInTheDocument()
  })
})
