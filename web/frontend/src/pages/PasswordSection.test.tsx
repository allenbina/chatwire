/**
 * Vitest unit tests for PasswordSection (exported from SettingsPage).
 *
 * PasswordSection uses react-query (useQuery + fetch) so it needs a
 * QueryClientProvider. It does NOT need Layout, Router, or any other
 * heavy context.
 *
 * Covers:
 *   - auth_enabled: false → "Set password" button, no current-password field
 *   - auth_enabled: true  → "Change password" + "Remove password" buttons,
 *                           current-password field present
 *   - mismatch: shows "Passwords do not match." without a network call
 *   - success (set):  shows "Password set." flash
 *   - success (change): shows "Password changed." flash
 *   - API error: shows detail message from response
 *   - clear (remove) success: shows "Password removed. Auth is now disabled."
 *   - confirm dialog: cancel aborts the POST
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { toast } from 'sonner'
import { PasswordSection } from './SettingsPage'

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}))

// ---------------------------------------------------------------------------
// Helper: wrap in QueryClientProvider with retry disabled
// ---------------------------------------------------------------------------

function renderPasswordSection(fetchImpl: typeof fetch) {
  vi.stubGlobal('fetch', fetchImpl)
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <PasswordSection />
    </QueryClientProvider>,
  )
}

/** Return a fake Response-shaped object for stubbing fetch. */
function jsonResponse(body: object, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  }
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

const user = userEvent.setup()

beforeEach(() => {
  vi.restoreAllMocks()
  // Suppress window.confirm (used by "Remove password") — default allow.
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})

// ---------------------------------------------------------------------------
// auth_enabled: false — "Set password" mode
// ---------------------------------------------------------------------------

describe('PasswordSection — auth disabled (no password set)', () => {
  function mockFetch(postResponse = jsonResponse({})) {
    return vi.fn().mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === '/api/ui/settings/password' && !init?.method) {
        return jsonResponse({ auth_enabled: false })
      }
      if (url === '/api/ui/settings/password') {
        return postResponse
      }
      return jsonResponse({}, 404)
    }) as unknown as typeof fetch
  }

  it('shows "Set password" button and no current-password field', async () => {
    renderPasswordSection(mockFetch())
    expect(await screen.findByRole('button', { name: /set password/i })).toBeInTheDocument()
    // No current-password label/input rendered
    expect(screen.queryByLabelText(/current password/i)).toBeNull()
    // Two labelled fields: new + confirm
    expect(screen.getByLabelText('New password')).toBeInTheDocument()
    expect(screen.getByLabelText(/confirm new password/i)).toBeInTheDocument()
  })

  it('calls toast.error "Passwords do not match." when new ≠ confirm, no POST made', async () => {
    const fetchMock = mockFetch()
    renderPasswordSection(fetchMock)

    await screen.findByRole('button', { name: /set password/i })

    await user.type(screen.getByLabelText('New password'), 'abc123')
    await user.type(screen.getByLabelText(/confirm new password/i), 'different')
    await user.click(screen.getByRole('button', { name: /set password/i }))

    await waitFor(() => {
      expect(vi.mocked(toast.error)).toHaveBeenCalledWith('Passwords do not match.')
    })
    // Only the initial GET — no POST
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('calls toast.success "Password set." on successful submit', async () => {
    renderPasswordSection(mockFetch(jsonResponse({ ok: true })))

    await screen.findByRole('button', { name: /set password/i })

    await user.type(screen.getByLabelText('New password'), 'newpass1')
    await user.type(screen.getByLabelText(/confirm new password/i), 'newpass1')
    await user.click(screen.getByRole('button', { name: /set password/i }))

    await waitFor(() => {
      expect(vi.mocked(toast.success)).toHaveBeenCalledWith('Password set.')
    })
  })

  it('calls toast.error with API error detail on non-ok response', async () => {
    renderPasswordSection(
      mockFetch(jsonResponse({ detail: 'Current password is wrong.' }, 400)),
    )

    await screen.findByRole('button', { name: /set password/i })

    await user.type(screen.getByLabelText('New password'), 'newpass1')
    await user.type(screen.getByLabelText(/confirm new password/i), 'newpass1')
    await user.click(screen.getByRole('button', { name: /set password/i }))

    await waitFor(() => {
      expect(vi.mocked(toast.error)).toHaveBeenCalledWith('Current password is wrong.')
    })
  })
})

// ---------------------------------------------------------------------------
// auth_enabled: true — "Change password" mode
// ---------------------------------------------------------------------------

describe('PasswordSection — auth enabled (password already set)', () => {
  function mockFetch(postResponse = jsonResponse({})) {
    return vi.fn().mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === '/api/ui/settings/password' && !init?.method) {
        return jsonResponse({ auth_enabled: true })
      }
      if (url === '/api/ui/settings/password') {
        return postResponse
      }
      return jsonResponse({}, 404)
    }) as unknown as typeof fetch
  }

  it('shows "Change password" and "Remove password" buttons with 3 inputs', async () => {
    renderPasswordSection(mockFetch())
    expect(await screen.findByRole('button', { name: /change password/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /remove password/i })).toBeInTheDocument()
    // All three fields labelled and accessible
    expect(screen.getByLabelText(/current password/i)).toBeInTheDocument()
    expect(screen.getByLabelText('New password')).toBeInTheDocument()
    expect(screen.getByLabelText(/confirm new password/i)).toBeInTheDocument()
  })

  it('calls toast.success "Password changed." on successful change', async () => {
    renderPasswordSection(mockFetch(jsonResponse({ ok: true })))

    await screen.findByRole('button', { name: /change password/i })

    await user.type(screen.getByLabelText(/current password/i), 'oldpass')
    await user.type(screen.getByLabelText('New password'), 'newpass1')
    await user.type(screen.getByLabelText(/confirm new password/i), 'newpass1')
    await user.click(screen.getByRole('button', { name: /change password/i }))

    await waitFor(() => {
      expect(vi.mocked(toast.success)).toHaveBeenCalledWith('Password changed.')
    })
  })

  it('calls toast.success with "Password removed." when clearing the password', async () => {
    renderPasswordSection(mockFetch(jsonResponse({ ok: true })))

    await screen.findByRole('button', { name: /remove password/i })

    await user.type(screen.getByLabelText(/current password/i), 'oldpass')
    await user.click(screen.getByRole('button', { name: /remove password/i }))

    await waitFor(() => {
      expect(vi.mocked(toast.success)).toHaveBeenCalledWith(
        expect.stringMatching(/password removed/i),
      )
    })
  })

  it('calls toast.error with API error detail on failed change', async () => {
    renderPasswordSection(
      mockFetch(jsonResponse({ detail: 'Wrong current password.' }, 403)),
    )

    await screen.findByRole('button', { name: /change password/i })

    await user.type(screen.getByLabelText('New password'), 'newpass1')
    await user.type(screen.getByLabelText(/confirm new password/i), 'newpass1')
    await user.click(screen.getByRole('button', { name: /change password/i }))

    await waitFor(() => {
      expect(vi.mocked(toast.error)).toHaveBeenCalledWith('Wrong current password.')
    })
  })

  it('calls toast.error "Passwords do not match." on mismatch without POSTing', async () => {
    const fetchMock = mockFetch()
    renderPasswordSection(fetchMock)

    await screen.findByRole('button', { name: /change password/i })

    await user.type(screen.getByLabelText('New password'), 'abc')
    await user.type(screen.getByLabelText(/confirm new password/i), 'xyz')
    await user.click(screen.getByRole('button', { name: /change password/i }))

    await waitFor(() => {
      expect(vi.mocked(toast.error)).toHaveBeenCalledWith('Passwords do not match.')
    })
    expect(fetchMock).toHaveBeenCalledTimes(1) // only the initial GET
  })
})

// ---------------------------------------------------------------------------
// "Remove password" — confirm dialog
// ---------------------------------------------------------------------------

describe('PasswordSection — remove password confirm dialog', () => {
  it('does NOT call the API when confirm returns false', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)

    const fetchMock = vi.fn().mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === '/api/ui/settings/password' && !init?.method) {
        return jsonResponse({ auth_enabled: true })
      }
      return jsonResponse({}, 404)
    })
    renderPasswordSection(fetchMock as unknown as typeof fetch)

    await screen.findByRole('button', { name: /remove password/i })
    await user.click(screen.getByRole('button', { name: /remove password/i }))

    // Only the initial status GET — no POST should have been made.
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
  })
})
