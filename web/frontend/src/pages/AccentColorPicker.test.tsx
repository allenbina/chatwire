/**
 * Vitest unit tests for AccentColorPicker (exported from SettingsPage).
 *
 * AccentColorPicker is a self-contained React component — no context or
 * external hooks required. Tests cover:
 *   - Renders swatch with value color when value is valid hex
 *   - Renders swatch with CSS var fallback when value is empty
 *   - Text input starts with the value prop
 *   - Typing a valid 7-char hex calls onChange
 *   - Typing an incomplete/invalid hex does NOT call onChange
 *   - Blur with invalid draft reverts to last good value
 *   - Enter key on invalid draft reverts (same as blur)
 *   - useEffect syncs draft when value prop changes (simulated via re-render)
 *   - isDraftInvalid class applied to text input on bad input
 */
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { AccentColorPicker } from './SettingsPage'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setup(value = '', onChange = vi.fn()) {
  const result = render(<AccentColorPicker value={value} onChange={onChange} />)
  const swatch = screen.getByRole('button', { name: /open color picker/i })
  const textInput = screen.getByRole('textbox', { name: /accent color hex value/i })
  return { swatch, textInput, onChange, rerender: result.rerender }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('AccentColorPicker', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the swatch with the provided hex color', () => {
    const { swatch } = setup('#ff0000')
    expect(swatch).toHaveStyle({ background: '#ff0000' })
  })

  it('renders the swatch with CSS var fallback when value is empty', () => {
    const { swatch } = setup('')
    expect(swatch).toHaveStyle({ background: 'hsl(var(--primary))' })
  })

  it('text input shows the value prop on mount', () => {
    const { textInput } = setup('#aabbcc')
    expect((textInput as HTMLInputElement).value).toBe('#aabbcc')
  })

  it('text input shows empty string when value is empty', () => {
    const { textInput } = setup('')
    expect((textInput as HTMLInputElement).value).toBe('')
  })

  it('typing a valid 7-char hex calls onChange', async () => {
    const onChange = vi.fn()
    const { textInput } = setup('', onChange)
    await userEvent.clear(textInput)
    await userEvent.type(textInput, '#00ff88')
    expect(onChange).toHaveBeenCalledWith('#00ff88')
  })

  it('does NOT call onChange while typing an incomplete hex', async () => {
    const onChange = vi.fn()
    const { textInput } = setup('', onChange)
    await userEvent.clear(textInput)
    await userEvent.type(textInput, '#00ff')   // only 6 chars total — invalid
    expect(onChange).not.toHaveBeenCalled()
  })

  it('does NOT call onChange for non-hex characters', async () => {
    const onChange = vi.fn()
    const { textInput } = setup('', onChange)
    await userEvent.clear(textInput)
    await userEvent.type(textInput, 'red')
    expect(onChange).not.toHaveBeenCalled()
  })

  it('reverts draft to last good value on blur when draft is invalid', async () => {
    const { textInput } = setup('#123456')
    await userEvent.clear(textInput)
    await userEvent.type(textInput, '#bad')   // partial — invalid
    fireEvent.blur(textInput)
    expect((textInput as HTMLInputElement).value).toBe('#123456')
  })

  it('pressing Enter on invalid draft blurs and reverts', async () => {
    const { textInput } = setup('#abcdef')
    await userEvent.clear(textInput)
    await userEvent.type(textInput, '#xyz')
    await userEvent.keyboard('{Enter}')
    expect((textInput as HTMLInputElement).value).toBe('#abcdef')
  })

  it('applies error styling class when draft is invalid', async () => {
    const { textInput } = setup('#123456')
    await userEvent.clear(textInput)
    await userEvent.type(textInput, '#zz')   // invalid
    expect(textInput.className).toMatch(/destructive/)
  })

  it('no error styling when draft is empty (placeholder state)', async () => {
    const { textInput } = setup('#123456')
    await userEvent.clear(textInput)
    expect(textInput.className).not.toMatch(/destructive/)
  })

  it('syncs draft when value prop changes externally', () => {
    const onChange = vi.fn()
    const { rerender, textInput } = setup('#aaaaaa', onChange)
    rerender(<AccentColorPicker value="#bbbbbb" onChange={onChange} />)
    expect((textInput as HTMLInputElement).value).toBe('#bbbbbb')
  })

  it('swatch updates live to draft color when typing valid hex', async () => {
    const { swatch, textInput } = setup('#000000')
    await userEvent.clear(textInput)
    await userEvent.type(textInput, '#ff1234')
    expect(swatch).toHaveStyle({ background: '#ff1234' })
  })
})
