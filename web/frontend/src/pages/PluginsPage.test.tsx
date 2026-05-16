/**
 * Vitest unit tests for PluginsPage — installed-plugins filter tabs.
 *
 * Covers:
 *   - "All" and "Themes" tabs render in the installed section
 *   - Default tab is "All" — all installed plugins visible
 *   - Clicking "Themes" tab shows only plugins tagged "theme"
 *   - Clicking "All" after "Themes" restores the full list
 *   - "No theme plugins installed" message when Themes tab is active
 *     but no installed plugin carries the "theme" tag
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { PluginsPage } from './PluginsPage'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}))

/** Minimal plugin shape returned by GET /api/ui/plugins */
function makePlugin(
  overrides: Partial<{
    name: string
    display_name: string
    description: string
    tier: string
    tags: string[]
    enabled: boolean
  }> = {},
) {
  return {
    name: 'test-plugin',
    display_name: 'Test Plugin',
    description: 'A test plugin',
    icon: null,
    tier: 'ui',
    version: '1.0.0',
    min_sdk: null,
    max_sdk: null,
    tags: [],
    settings_schema: {},
    enabled: true,
    health: { last_run: null, last_success: null, last_error: null, errors_24h: 0, total_runs: 0, status: 'healthy' },
    needs_config: false,
    dist_name: null,
    sdk_compat: true,
    sdk_warning: null,
    ...overrides,
  }
}

const THEME_PLUGIN = makePlugin({ name: 'theme-rose', display_name: 'Rose Pine', tags: ['theme'] })
const NOTIFY_PLUGIN = makePlugin({ name: 'notify-slack', display_name: 'Slack Notify', tags: ['notify'], tier: 'notify' })

function mockFetch(plugins: ReturnType<typeof makePlugin>[]) {
  globalThis.fetch = vi.fn().mockImplementation((url: string) => {
    if (url.includes('/api/ui/plugins/updates')) {
      return Promise.resolve({ ok: true, json: async () => ({ updates: [] }) } as Response)
    }
    if (url.includes('/api/ui/plugins/marketplace')) {
      return Promise.resolve({ ok: true, json: async () => ({ plugins: [] }) } as Response)
    }
    if (url.includes('/api/ui/plugins')) {
      return Promise.resolve({ ok: true, json: async () => ({ plugins }) } as Response)
    }
    return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
  }) as unknown as typeof fetch
}

function renderPage(plugins: ReturnType<typeof makePlugin>[] = []) {
  mockFetch(plugins)
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PluginsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PluginsPage — installed filter tabs', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders "All" and "Themes" tab buttons', async () => {
    renderPage([NOTIFY_PLUGIN])
    // Tabs are rendered immediately (before data loads)
    expect(screen.getByRole('tab', { name: 'All' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Themes' })).toBeInTheDocument()
  })

  it('"All" tab is selected by default', async () => {
    renderPage([NOTIFY_PLUGIN])
    expect(screen.getByRole('tab', { name: 'All' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'Themes' })).toHaveAttribute('aria-selected', 'false')
  })

  it('shows all installed plugins when "All" tab is active', async () => {
    renderPage([THEME_PLUGIN, NOTIFY_PLUGIN])
    await waitFor(() => {
      expect(screen.getByText('Rose Pine')).toBeInTheDocument()
      expect(screen.getByText('Slack Notify')).toBeInTheDocument()
    })
  })

  it('shows only theme-tagged plugins after clicking "Themes"', async () => {
    const user = userEvent.setup()
    renderPage([THEME_PLUGIN, NOTIFY_PLUGIN])

    await waitFor(() => expect(screen.getByText('Rose Pine')).toBeInTheDocument())

    await user.click(screen.getByRole('tab', { name: 'Themes' }))

    await waitFor(() => {
      expect(screen.getByText('Rose Pine')).toBeInTheDocument()
      expect(screen.queryByText('Slack Notify')).not.toBeInTheDocument()
    })

    expect(screen.getByRole('tab', { name: 'Themes' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'All' })).toHaveAttribute('aria-selected', 'false')
  })

  it('restores full list when switching back to "All"', async () => {
    const user = userEvent.setup()
    renderPage([THEME_PLUGIN, NOTIFY_PLUGIN])

    await waitFor(() => expect(screen.getByText('Rose Pine')).toBeInTheDocument())

    await user.click(screen.getByRole('tab', { name: 'Themes' }))
    await waitFor(() => expect(screen.queryByText('Slack Notify')).not.toBeInTheDocument())

    await user.click(screen.getByRole('tab', { name: 'All' }))
    await waitFor(() => {
      expect(screen.getByText('Rose Pine')).toBeInTheDocument()
      expect(screen.getByText('Slack Notify')).toBeInTheDocument()
    })
  })

  it('shows "No theme plugins installed" when Themes tab is active but none are tagged theme', async () => {
    const user = userEvent.setup()
    renderPage([NOTIFY_PLUGIN])

    await waitFor(() => expect(screen.getByText('Slack Notify')).toBeInTheDocument())

    await user.click(screen.getByRole('tab', { name: 'Themes' }))

    await waitFor(() => {
      expect(screen.getByText('No theme plugins installed.')).toBeInTheDocument()
      expect(screen.queryByText('Slack Notify')).not.toBeInTheDocument()
    })
  })

  it('shows "No plugins installed." when plugin list is empty (not the theme-specific message)', async () => {
    renderPage([])
    await waitFor(() => {
      expect(screen.getByText('No plugins installed.')).toBeInTheDocument()
    })
    // Theme-specific message should not appear — the outer empty check fires first
    expect(screen.queryByText('No theme plugins installed.')).not.toBeInTheDocument()
  })
})
