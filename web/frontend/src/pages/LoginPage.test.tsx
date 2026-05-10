/**
 * Vitest unit tests for LoginPage.
 *
 * Covers:
 *   - renders form elements
 *   - password field and button are present
 *   - busy state during submission ("Signing in…")
 *   - toast.error on 403 (wrong password)
 *   - toast.error with JSON detail field
 *   - "Network error" toast on fetch rejection
 *   - window.location.href redirect on success
 *   - ?next= param is forwarded to the login endpoint and used for redirect
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { toast } from 'sonner'
import { LoginPage } from './LoginPage'

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}))

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderLogin(search = '') {
  return render(
    <MemoryRouter initialEntries={[`/login${search}`]}>
      <LoginPage />
    </MemoryRouter>,
  )
}

const user = userEvent.setup()

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

let locationHref: string

beforeEach(() => {
  locationHref = ''
  // jsdom doesn't let you assign window.location.href directly; use Object.defineProperty.
  Object.defineProperty(window, 'location', {
    value: { href: '' },
    writable: true,
    configurable: true,
  })
  Object.defineProperty(window.location, 'href', {
    get: () => locationHref,
    set: (v: string) => { locationHref = v },
    configurable: true,
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

describe('LoginPage — rendering', () => {
  it('renders the heading and sign-in form', () => {
    vi.stubGlobal('fetch', vi.fn())
    renderLogin()
    expect(screen.getByText('iMessage bridge')).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
  })

  it('does not call toast.error by default', () => {
    vi.stubGlobal('fetch', vi.fn())
    renderLogin()
    expect(vi.mocked(toast.error)).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------------
// Success — redirect
// ---------------------------------------------------------------------------

describe('LoginPage — success', () => {
  it('redirects to data.next on 200', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true, next: '/app/' }),
    }))

    renderLogin()
    await user.type(screen.getByLabelText(/password/i), 'secret')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(locationHref).toBe('/app/'))
  })

  it('falls back to /app/ when data.next is absent', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true }),
    }))

    renderLogin()
    await user.type(screen.getByLabelText(/password/i), 'secret')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(locationHref).toBe('/app/'))
  })

  it('forwards ?next= to the redirect target', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true, next: '/app/settings' }),
    }))

    renderLogin('?next=/app/settings')
    await user.type(screen.getByLabelText(/password/i), 'secret')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(locationHref).toBe('/app/settings'))
  })

  it('sends ?next= param in the POST body', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true, next: '/app/chat/alice' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    renderLogin('?next=/app/chat/alice')
    await user.type(screen.getByLabelText(/password/i), 'hunter2')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body.next).toBe('/app/chat/alice')
    expect(body.password).toBe('hunter2')
  })
})

// ---------------------------------------------------------------------------
// Busy state
// ---------------------------------------------------------------------------

describe('LoginPage — busy state', () => {
  it('shows "Signing in…" while the request is in-flight', async () => {
    // Promise that never resolves — keeps the button in busy state.
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})))

    renderLogin()
    await user.type(screen.getByLabelText(/password/i), 'secret')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByRole('button', { name: /signing in/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /signing in/i })).toBeDisabled()
  })
})

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

describe('LoginPage — errors', () => {
  it('calls toast.error with "Sign in failed." on 403 with no detail field', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({}),
    }))

    renderLogin()
    await user.type(screen.getByLabelText(/password/i), 'wrong')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(vi.mocked(toast.error)).toHaveBeenCalledWith('Sign in failed.')
    })
  })

  it('calls toast.error with the detail message from a 403 JSON body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({ detail: 'Invalid password.' }),
    }))

    renderLogin()
    await user.type(screen.getByLabelText(/password/i), 'wrong')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(vi.mocked(toast.error)).toHaveBeenCalledWith('Invalid password.')
    })
  })

  it('calls toast.error with the detail message from a 429 rate-limit response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      json: async () => ({ detail: 'Too many attempts. Try again in 60 s.' }),
    }))

    renderLogin()
    await user.type(screen.getByLabelText(/password/i), 'bots')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(vi.mocked(toast.error)).toHaveBeenCalledWith(
        expect.stringContaining('Too many attempts'),
      )
    })
  })

  it('calls toast.error with "Network error" when fetch rejects', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    renderLogin()
    await user.type(screen.getByLabelText(/password/i), 'secret')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(vi.mocked(toast.error)).toHaveBeenCalledWith(
        expect.stringContaining('Network error'),
      )
    })
  })

  it('does not call toast.error on a successful re-submission after an error', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 403,
        json: async () => ({ detail: 'Bad password.' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ ok: true, next: '/app/' }),
      })
    vi.stubGlobal('fetch', fetchMock)

    renderLogin()
    const input = screen.getByLabelText(/password/i)
    await user.type(input, 'wrong')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(vi.mocked(toast.error)).toHaveBeenCalledTimes(1)
    })

    // Re-submit with correct password — no additional error toast
    await user.clear(input)
    await user.type(input, 'correct')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(locationHref).toBe('/app/'))
    expect(vi.mocked(toast.error)).toHaveBeenCalledTimes(1)
  })
})
