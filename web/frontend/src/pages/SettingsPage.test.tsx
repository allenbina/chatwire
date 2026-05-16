/**
 * SettingsPage.test.tsx — Phase 86 (automations tests removed Phase 88)
 *
 * Tests cover:
 *   - AccentColorPicker (UI component — React state only)
 *   - PasswordSection  (UI component — fetch + react-query)
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// ---------------------------------------------------------------------------
// Mocks required so the module can be imported without side-effects
// ---------------------------------------------------------------------------
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }))
vi.mock('../components/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))
vi.mock('../hooks/usePinnedSettings', () => ({
  usePinnedSettings: () => ({ isPinned: () => false, togglePin: vi.fn() }),
  PINNABLE_LABELS: {},
}))
vi.mock('../hooks/useTheme', () => ({
  useTheme: () => ({}),
  applyThemeOverride: vi.fn(),
  applyThemePackCss: vi.fn(),
  restoreThemeOverride: vi.fn(),
}))
vi.mock('../hooks/useSounds', () => ({
  configureSounds: vi.fn(),
  SoundMode: {},
}))
vi.mock('../plugins/SlotRenderer', () => ({ SlotRenderer: () => null }))
vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
  useLocation: () => ({ hash: '', pathname: '/settings' }),
}))

import { toast } from 'sonner'
import {
  AccentColorPicker,
  PasswordSection,
} from './SettingsPage'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderWithQC(ui: React.ReactElement, qc = makeQC()) {
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

// Automation rule tests (_formToApiRule, _apiRuleToForm) removed — see docs/stashed/automations/

// AccentColorPicker
// ===========================================================================
describe('AccentColorPicker', () => {
  it('renders text input with provided hex value', () => {
    render(<AccentColorPicker value="#bd93f9" onChange={() => {}} />)
    const input = screen.getByLabelText('Accent color hex value') as HTMLInputElement
    expect(input.value).toBe('#bd93f9')
  })

  it('renders with empty value (shows placeholder)', () => {
    render(<AccentColorPicker value="" onChange={() => {}} />)
    const input = screen.getByLabelText('Accent color hex value') as HTMLInputElement
    expect(input.value).toBe('')
    expect(input.placeholder).toBe('theme default')
  })

  it('calls onChange with valid hex when typed', () => {
    const onChange = vi.fn()
    render(<AccentColorPicker value="" onChange={onChange} />)
    const input = screen.getByLabelText('Accent color hex value')
    fireEvent.change(input, { target: { value: '#ff0000' } })
    expect(onChange).toHaveBeenCalledWith('#ff0000')
  })

  it('does not call onChange when hex is invalid', () => {
    const onChange = vi.fn()
    render(<AccentColorPicker value="" onChange={onChange} />)
    const input = screen.getByLabelText('Accent color hex value')
    fireEvent.change(input, { target: { value: 'notahex' } })
    expect(onChange).not.toHaveBeenCalled()
  })

  it('reverts invalid draft to saved value on blur', () => {
    render(<AccentColorPicker value="#ff0000" onChange={() => {}} />)
    const input = screen.getByLabelText('Accent color hex value') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'bad' } })
    expect(input.value).toBe('bad')
    fireEvent.blur(input)
    expect(input.value).toBe('#ff0000')
  })

  it('does not revert valid draft on blur', () => {
    render(<AccentColorPicker value="#ff0000" onChange={() => {}} />)
    const input = screen.getByLabelText('Accent color hex value') as HTMLInputElement
    fireEvent.change(input, { target: { value: '#00ff00' } })
    fireEvent.blur(input)
    expect(input.value).toBe('#00ff00')
  })

  it('native picker change calls onChange', () => {
    const onChange = vi.fn()
    render(<AccentColorPicker value="#bd93f9" onChange={onChange} />)
    const native = document.querySelector('input[type="color"]') as HTMLInputElement
    fireEvent.change(native, { target: { value: '#123456' } })
    expect(onChange).toHaveBeenCalledWith('#123456')
  })

  it('swatch button is labeled "Open color picker"', () => {
    render(<AccentColorPicker value="#bd93f9" onChange={() => {}} />)
    expect(screen.getByRole('button', { name: 'Open color picker' })).toBeInTheDocument()
  })

  it('updates draft when parent resets value via prop change', () => {
    const { rerender } = render(<AccentColorPicker value="#ff0000" onChange={() => {}} />)
    const input = screen.getByLabelText('Accent color hex value') as HTMLInputElement
    expect(input.value).toBe('#ff0000')
    rerender(<AccentColorPicker value="#00ff00" onChange={() => {}} />)
    expect(input.value).toBe('#00ff00')
  })
})

// ===========================================================================
// PasswordSection
// ===========================================================================
describe('PasswordSection', () => {
  beforeEach(() => {
    vi.spyOn(toast, 'error').mockImplementation(() => '')
    vi.spyOn(toast, 'success').mockImplementation(() => '')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  function renderSection(fetchData: unknown, fetchOk = true) {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: fetchOk,
      json: async () => fetchData,
    })
    vi.stubGlobal('fetch', fetchMock)
    const qc = makeQC()
    render(
      <QueryClientProvider client={qc}>
        <PasswordSection />
      </QueryClientProvider>
    )
    return fetchMock
  }

  it('shows "No password is set" when auth disabled', async () => {
    renderSection({ auth_enabled: false })
    await waitFor(() =>
      expect(screen.getByText(/No password is set/i)).toBeInTheDocument()
    )
    // current password field should NOT appear
    expect(screen.queryByLabelText(/current password/i)).not.toBeInTheDocument()
  })

  it('shows "A password is currently set" when auth enabled', async () => {
    renderSection({ auth_enabled: true })
    await waitFor(() =>
      expect(screen.getByText(/A password is currently set/i)).toBeInTheDocument()
    )
    // current password field IS shown
    expect(screen.getByLabelText(/current password/i)).toBeInTheDocument()
  })

  it('shows toast.error when passwords do not match', async () => {
    renderSection({ auth_enabled: false })
    await waitFor(() => screen.getByText(/No password is set/i))

    fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'pass1234' } })
    fireEvent.change(screen.getByLabelText('Confirm new password'), { target: { value: 'pass9999' } })
    fireEvent.click(screen.getByRole('button', { name: /set password/i }))

    expect(toast.error).toHaveBeenCalledWith('Passwords do not match.')
  })

  it('calls POST and shows toast.success on successful set', async () => {
    const fetchMock = vi.fn()
      // First call: GET /api/ui/settings/password (query)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ auth_enabled: false }) })
      // Second call: POST /api/ui/settings/password (submit)
      .mockResolvedValueOnce({ ok: true, json: async () => ({}) })
    vi.stubGlobal('fetch', fetchMock)

    renderWithQC(<PasswordSection />)
    await waitFor(() => screen.getByText(/No password is set/i))

    fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'correct-horse' } })
    fireEvent.change(screen.getByLabelText('Confirm new password'), { target: { value: 'correct-horse' } })
    fireEvent.click(screen.getByRole('button', { name: /set password/i }))

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Password set.'))
    // Fields cleared after success
    const newPw = screen.getByLabelText('New password') as HTMLInputElement
    expect(newPw.value).toBe('')
  })

  it('shows toast.error from API detail on failure', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ auth_enabled: false }) })
      .mockResolvedValueOnce({ ok: false, json: async () => ({ detail: 'Wrong password' }) })
    vi.stubGlobal('fetch', fetchMock)

    renderWithQC(<PasswordSection />)
    await waitFor(() => screen.getByText(/No password is set/i))

    fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'abc123' } })
    fireEvent.change(screen.getByLabelText('Confirm new password'), { target: { value: 'abc123' } })
    fireEvent.click(screen.getByRole('button', { name: /set password/i }))

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Wrong password'))
  })

  it('Remove password button absent when auth disabled', async () => {
    renderSection({ auth_enabled: false })
    await waitFor(() => screen.getByText(/No password is set/i))
    expect(screen.queryByRole('button', { name: /remove password/i })).not.toBeInTheDocument()
  })

  it('Remove password button present when auth enabled', async () => {
    renderSection({ auth_enabled: true })
    await waitFor(() => screen.getByText(/A password is currently set/i))
    expect(screen.getByRole('button', { name: /remove password/i })).toBeInTheDocument()
  })

  it('handleClear: confirm=false → no fetch POST', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ auth_enabled: true }) })
    vi.stubGlobal('fetch', fetchMock)

    renderWithQC(<PasswordSection />)
    await waitFor(() => screen.getByText(/A password is currently set/i))

    fireEvent.click(screen.getByRole('button', { name: /remove password/i }))
    // Only the initial GET should have been called; no POST
    expect(fetchMock).toHaveBeenCalledTimes(1)
    vi.mocked(window.confirm).mockRestore()
  })

  it('handleClear: confirm=true → calls POST with clear:true', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ auth_enabled: true }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({}) })
    vi.stubGlobal('fetch', fetchMock)

    renderWithQC(<PasswordSection />)
    await waitFor(() => screen.getByText(/A password is currently set/i))

    fireEvent.click(screen.getByRole('button', { name: /remove password/i }))
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Password removed. Auth is now disabled.'))

    const postCall = fetchMock.mock.calls[1]
    expect(postCall[1].method).toBe('POST')
    const body = JSON.parse(postCall[1].body)
    expect(body.clear).toBe(true)
    vi.mocked(window.confirm).mockRestore()
  })
})
