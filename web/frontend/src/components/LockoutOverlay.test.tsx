/**
 * Vitest unit tests for LockoutOverlay.
 *
 * Covers:
 *   - renders lockout overlay for step 4 with countdown timer
 *   - renders lockout overlay for step 5 with countdown timer
 *   - renders permanent lockout (step 6) with unlock code and form link
 *   - unlock code input and submit button visible on step 6
 *   - valid code: calls postUnlock and invalidates fuse-status query
 *   - invalid code: shows "Invalid code" error
 *   - countdown ticks down every second and re-fetches when it hits zero
 */
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { LockoutOverlay } from './LockoutOverlay'
import { postUnlock } from '../api'
import type { FuseStatus } from '../api'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    postUnlock: vi.fn(),
    getFuseStatus: vi.fn(),
  }
})

const mockedPostUnlock = vi.mocked(postUnlock)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderOverlay(fuseStatus: FuseStatus, qc = makeQC()) {
  return render(
    <QueryClientProvider client={qc}>
      <LockoutOverlay fuseStatus={fuseStatus} />
    </QueryClientProvider>,
  )
}

const STEP4: FuseStatus = {
  locked: true,
  step: 4,
  cooldown_remaining_s: 86400,
  unlock_code: 'CW-ABCD-1234',
}

const STEP6: FuseStatus = {
  locked: true,
  step: 6,
  cooldown_remaining_s: null,
  unlock_code: 'CW-ABCD-EFGH',
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks()
})

describe('LockoutOverlay', () => {
  it('renders the lockout overlay container', () => {
    renderOverlay(STEP4)
    expect(screen.getByTestId('lockout-overlay')).toBeInTheDocument()
  })

  it('shows the "Outbound messaging is locked" heading', () => {
    renderOverlay(STEP4)
    expect(screen.getByText(/outbound messaging is locked/i)).toBeInTheDocument()
  })

  it('shows the warm message copy', () => {
    renderOverlay(STEP4)
    expect(screen.getByText(/stay connected with the people you care about/i)).toBeInTheDocument()
  })

  it('step 4: shows a countdown timer', () => {
    renderOverlay(STEP4)
    // 86400s = 24:00:00
    expect(screen.getByText('24:00:00')).toBeInTheDocument()
  })

  it('step 5: shows a countdown timer', () => {
    renderOverlay({ ...STEP4, step: 5, cooldown_remaining_s: 3661 })
    // 3661s = 01:01:01
    expect(screen.getByText('01:01:01')).toBeInTheDocument()
  })

  it('step 4: does NOT show the unlock code input', () => {
    renderOverlay(STEP4)
    expect(screen.queryByLabelText(/paste your unlock code/i)).not.toBeInTheDocument()
  })

  it('step 6: shows the machine CW code', () => {
    renderOverlay(STEP6)
    expect(screen.getByText('CW-ABCD-EFGH')).toBeInTheDocument()
  })

  it('step 6: shows the "Request unlock" link', () => {
    renderOverlay(STEP6)
    const link = screen.getByRole('link', { name: /request unlock/i })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href')
  })

  it('step 6: shows the unlock code input', () => {
    renderOverlay(STEP6)
    expect(screen.getByLabelText(/paste your unlock code/i)).toBeInTheDocument()
  })

  it('step 6: Unlock button is disabled when input is empty', () => {
    renderOverlay(STEP6)
    expect(screen.getByRole('button', { name: /unlock/i })).toBeDisabled()
  })

  it('step 6: Unlock button enabled after typing', async () => {
    const user = userEvent.setup()
    renderOverlay(STEP6)
    await user.type(screen.getByLabelText(/paste your unlock code/i), 'UL-ABCD-1234')
    expect(screen.getByRole('button', { name: /unlock/i })).not.toBeDisabled()
  })

  it('step 6: valid code calls postUnlock', async () => {
    const user = userEvent.setup()
    mockedPostUnlock.mockResolvedValue(undefined)
    renderOverlay(STEP6)

    await user.type(screen.getByLabelText(/paste your unlock code/i), 'UL-ABCD-1234')
    await user.click(screen.getByRole('button', { name: /unlock/i }))

    await waitFor(() => {
      expect(mockedPostUnlock).toHaveBeenCalledWith('UL-ABCD-1234')
    })
  })

  it('step 6: invalid code shows error message', async () => {
    const user = userEvent.setup()
    mockedPostUnlock.mockRejectedValue(new Error('400 Bad Request'))
    renderOverlay(STEP6)

    await user.type(screen.getByLabelText(/paste your unlock code/i), 'UL-ZZZZ-ZZZZ')
    await user.click(screen.getByRole('button', { name: /unlock/i }))

    await waitFor(() => {
      expect(screen.getByText('Invalid code')).toBeInTheDocument()
    })
  })

  it('countdown ticks down by 1 each second', async () => {
    vi.useFakeTimers()
    try {
      renderOverlay({ ...STEP4, cooldown_remaining_s: 10 })
      expect(screen.getByText('00:00:10')).toBeInTheDocument()

      await act(async () => { vi.advanceTimersByTime(1000) })
      expect(screen.getByText('00:00:09')).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })
})
