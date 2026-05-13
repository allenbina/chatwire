/**
 * Vitest unit tests for ComposeBox.
 *
 * Covers:
 *   - renders textarea with placeholder and Send / Attach buttons
 *   - Send button is disabled when textarea is empty
 *   - Send button is enabled after typing text
 *   - pressing Enter calls sendMessage with correct args and clears textarea
 *   - clicking the Send button calls sendMessage and clears textarea
 *   - Shift+Enter inserts a newline and does NOT send
 *   - textarea and Send button are disabled while a send is in-flight
 *   - API error fires toast.error and restores original text
 *   - optimistic message is added to the zustand store on send
 *   - optimistic message is cleared from the store after send completes
 *   - cooldown banner is shown when fuse is locked (steps 1-3)
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ComposeBox } from './ComposeBox'
import { sendMessage, getFuseStatus } from '../api'
import { useChatStore } from '../store'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    sendMessage: vi.fn(),
    sendFile: vi.fn(),
    getFuseStatus: vi.fn(),
  }
})

// SlotRenderer renders nothing in tests (no plugins registered).
vi.mock('../plugins/SlotRenderer', () => ({
  SlotRenderer: () => null,
}))

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}))

const mockedSendMessage = vi.mocked(sendMessage)
const mockedGetFuseStatus = vi.mocked(getFuseStatus)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const HANDLE = '+15550001111'

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderComposeBox(handle = HANDLE, qc = makeQC()) {
  return render(
    <QueryClientProvider client={qc}>
      <ComposeBox handle={handle} />
    </QueryClientProvider>,
  )
}

/** Resolves immediately with a success payload. */
function sendOk() {
  return Promise.resolve({ status: 'ok', hint: '', service: 'iMessage' })
}

const FUSE_INACTIVE = {
  locked: false, step: 0, cooldown_remaining_s: null, unlock_code: null,
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks()
  useChatStore.setState({ optimistic: {}, activeHandle: null, sidebarOpen: false })
  // Default: fuse inactive
  mockedGetFuseStatus.mockResolvedValue(FUSE_INACTIVE)
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ComposeBox', () => {
  it('renders textarea and Send button', () => {
    renderComposeBox()
    expect(screen.getByRole('textbox', { name: /type a message/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /send message/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /attach file/i })).toBeInTheDocument()
  })

  it('shows the "Message…" placeholder', () => {
    renderComposeBox()
    expect(screen.getByPlaceholderText('Message…')).toBeInTheDocument()
  })

  it('Send button is disabled when textarea is empty', () => {
    renderComposeBox()
    expect(screen.getByRole('button', { name: /send message/i })).toBeDisabled()
  })

  it('Send button becomes enabled after typing text', async () => {
    const user = userEvent.setup()
    renderComposeBox()
    await user.type(screen.getByRole('textbox', { name: /type a message/i }), 'hello')
    expect(screen.getByRole('button', { name: /send message/i })).not.toBeDisabled()
  })

  it('pressing Enter calls sendMessage with correct handle and text', async () => {
    const user = userEvent.setup()
    mockedSendMessage.mockReturnValue(sendOk())
    renderComposeBox()

    await user.type(screen.getByRole('textbox', { name: /type a message/i }), 'hello{Enter}')

    expect(mockedSendMessage).toHaveBeenCalledOnce()
    expect(mockedSendMessage).toHaveBeenCalledWith(HANDLE, 'hello', false, '')
  })

  it('pressing Enter clears the textarea after send', async () => {
    const user = userEvent.setup()
    mockedSendMessage.mockReturnValue(sendOk())
    renderComposeBox()

    const textarea = screen.getByRole('textbox', { name: /type a message/i })
    await user.type(textarea, 'hello{Enter}')

    await waitFor(() => {
      expect(textarea).toHaveValue('')
    })
  })

  it('clicking the Send button calls sendMessage and clears textarea', async () => {
    const user = userEvent.setup()
    mockedSendMessage.mockReturnValue(sendOk())
    renderComposeBox()

    const textarea = screen.getByRole('textbox', { name: /type a message/i })
    await user.type(textarea, 'world')
    await user.click(screen.getByRole('button', { name: /send message/i }))

    expect(mockedSendMessage).toHaveBeenCalledOnce()
    expect(mockedSendMessage).toHaveBeenCalledWith(HANDLE, 'world', false, '')
    await waitFor(() => {
      expect(textarea).toHaveValue('')
    })
  })

  it('Shift+Enter inserts a newline and does NOT call sendMessage', async () => {
    const user = userEvent.setup()
    mockedSendMessage.mockReturnValue(sendOk())
    renderComposeBox()

    const textarea = screen.getByRole('textbox', { name: /type a message/i })
    await user.type(textarea, 'line1')
    await user.keyboard('{Shift>}{Enter}{/Shift}')
    await user.type(textarea, 'line2')

    expect(mockedSendMessage).not.toHaveBeenCalled()
    // Value should contain both lines (userEvent inserts \n for Shift+Enter).
    expect(textarea).toHaveValue('line1\nline2')
  })

  it('textarea and Send button are disabled while send is in-flight', async () => {
    const user = userEvent.setup()

    // Never-resolving promise keeps the component in the sending state.
    let resolveSend!: () => void
    mockedSendMessage.mockReturnValue(
      new Promise((resolve) => {
        resolveSend = () => resolve({ status: 'ok', hint: '', service: 'iMessage' })
      }),
    )
    renderComposeBox()

    const textarea = screen.getByRole('textbox', { name: /type a message/i })
    await user.type(textarea, 'hello{Enter}')

    // While the promise is pending the UI should be locked.
    expect(textarea).toBeDisabled()
    expect(screen.getByRole('button', { name: /send message/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /attach file/i })).toBeDisabled()

    // Resolve the send so the component can clean up.
    resolveSend()
    await waitFor(() => expect(textarea).not.toBeDisabled())
  })

  it('calls toast.error when sendMessage rejects', async () => {
    const user = userEvent.setup()
    mockedSendMessage.mockRejectedValue(new Error('Rate limited'))
    renderComposeBox()

    await user.type(screen.getByRole('textbox', { name: /type a message/i }), 'hello{Enter}')

    await waitFor(() => {
      expect(vi.mocked(toast.error)).toHaveBeenCalledWith('Rate limited')
    })
  })

  it('restores textarea text when sendMessage rejects', async () => {
    const user = userEvent.setup()
    mockedSendMessage.mockRejectedValue(new Error('Network error'))
    renderComposeBox()

    const textarea = screen.getByRole('textbox', { name: /type a message/i })
    await user.type(textarea, 'unsent message{Enter}')

    await waitFor(() => {
      expect(textarea).toHaveValue('unsent message')
    })
  })

  it('adds an optimistic message to the zustand store on send', async () => {
    const user = userEvent.setup()
    // Keep the send in-flight so the optimistic entry is still present.
    let resolveSend!: () => void
    mockedSendMessage.mockReturnValue(
      new Promise((resolve) => {
        resolveSend = () => resolve({ status: 'ok', hint: '', service: 'iMessage' })
      }),
    )
    renderComposeBox()

    await user.type(screen.getByRole('textbox', { name: /type a message/i }), 'opt msg{Enter}')

    // The store should have one optimistic entry for HANDLE while send is pending.
    const optimistic = useChatStore.getState().optimistic[HANDLE]
    expect(optimistic).toHaveLength(1)
    expect(optimistic[0].text).toBe('opt msg')
    expect(optimistic[0].from_me).toBe(true)
    expect(optimistic[0].pending).toBe(true)

    resolveSend()
    await waitFor(() => {
      expect(useChatStore.getState().optimistic[HANDLE]).toHaveLength(0)
    })
  })

  it('passes isGroup=true to sendMessage for group conversations', async () => {
    const user = userEvent.setup()
    mockedSendMessage.mockReturnValue(sendOk())

    const qc = makeQC()
    render(
      <QueryClientProvider client={qc}>
        <ComposeBox handle="group-guid-abc" isGroup={true} />
      </QueryClientProvider>,
    )

    await user.type(
      screen.getByRole('textbox', { name: /type a message/i }),
      'group message{Enter}',
    )

    expect(mockedSendMessage).toHaveBeenCalledWith('group-guid-abc', 'group message', true, '')
  })
})

// ---------------------------------------------------------------------------
// Cooldown banner (fuse steps 1-3)
// ---------------------------------------------------------------------------

describe('ComposeBox — cooldown banner', () => {
  it('shows cooldown banner when fuse is locked at step 1', async () => {
    mockedGetFuseStatus.mockResolvedValue({
      locked: true,
      step: 1,
      cooldown_remaining_s: 300,
      unlock_code: null,
    })
    renderComposeBox()

    await waitFor(() => {
      expect(screen.getByText(/Sends paused/i)).toBeInTheDocument()
    })
    expect(screen.queryByRole('textbox', { name: /type a message/i })).not.toBeInTheDocument()
  })

  it('shows cooldown banner for steps 2 and 3', async () => {
    for (const step of [2, 3]) {
      mockedGetFuseStatus.mockResolvedValue({
        locked: true,
        step,
        cooldown_remaining_s: 1800,
        unlock_code: null,
      })
      const qc = makeQC()
      const { unmount } = render(
        <QueryClientProvider client={qc}>
          <ComposeBox handle={HANDLE} />
        </QueryClientProvider>,
      )
      await waitFor(() => {
        expect(screen.getByText(/Sends paused/i)).toBeInTheDocument()
      })
      unmount()
    }
  })

  it('shows normal compose box when fuse is not locked', async () => {
    mockedGetFuseStatus.mockResolvedValue(FUSE_INACTIVE)
    renderComposeBox()

    await waitFor(() => {
      expect(screen.getByRole('textbox', { name: /type a message/i })).toBeInTheDocument()
    })
    expect(screen.queryByText(/Sends paused/i)).not.toBeInTheDocument()
  })

  it('shows "broadcast pattern" text in the banner', async () => {
    mockedGetFuseStatus.mockResolvedValue({
      locked: true,
      step: 2,
      cooldown_remaining_s: 1800,
      unlock_code: null,
    })
    renderComposeBox()

    await waitFor(() => {
      expect(screen.getByText(/broadcast pattern/i)).toBeInTheDocument()
    })
  })

  it('shows "Normal chatting resumes soon" in the banner', async () => {
    mockedGetFuseStatus.mockResolvedValue({
      locked: true,
      step: 1,
      cooldown_remaining_s: 60,
      unlock_code: null,
    })
    renderComposeBox()

    await waitFor(() => {
      expect(screen.getByText(/Normal chatting resumes soon/i)).toBeInTheDocument()
    })
  })
})
