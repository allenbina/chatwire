/**
 * Vitest tests for the useTheme hook and CSS-native theme system.
 *
 * Covers:
 *   - allSchemes has 21 entries with required fields
 *   - allStyles has 3 entries (default / compact / flat)
 *   - applyTheme() sets data-theme attribute on <html>
 *   - applyStyle() sets data-style attribute on <html>
 *   - Switching schemes/styles changes the attribute
 *   - useTheme().setTheme() applies data-theme
 *   - useTheme().setStyle() applies data-style
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { applyTheme, applyStyle, applyAccentColor, applyCustomCss, allSchemes, allStyles, useTheme } from './useTheme'

// ---------------------------------------------------------------------------
// allSchemes
// ---------------------------------------------------------------------------

describe('allSchemes', () => {
  it('has 21 entries', () => {
    expect(allSchemes).toHaveLength(21)
  })

  it('each entry has name, label, isLight, swatch', () => {
    for (const s of allSchemes) {
      expect(typeof s.name).toBe('string')
      expect(typeof s.label).toBe('string')
      expect(typeof s.isLight).toBe('boolean')
      expect(typeof s.swatch).toBe('string')
    }
  })

  it('all scheme names are unique', () => {
    const names = allSchemes.map((s) => s.name)
    expect(new Set(names).size).toBe(names.length)
  })
})

// ---------------------------------------------------------------------------
// allStyles
// ---------------------------------------------------------------------------

describe('allStyles', () => {
  it('has 3 entries', () => {
    expect(allStyles).toHaveLength(3)
  })

  it('contains default, compact, flat', () => {
    const names = allStyles.map((s) => s.name)
    expect(names).toContain('default')
    expect(names).toContain('compact')
    expect(names).toContain('flat')
  })
})

// ---------------------------------------------------------------------------
// applyTheme / applyStyle — DOM attribute setters
// ---------------------------------------------------------------------------

describe('applyTheme', () => {
  it('sets data-theme on <html>', () => {
    applyTheme('dracula')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dracula')
  })

  it('changes data-theme when a different scheme is applied', () => {
    applyTheme('nord')
    expect(document.documentElement.getAttribute('data-theme')).toBe('nord')
    applyTheme('tokyo-night')
    expect(document.documentElement.getAttribute('data-theme')).toBe('tokyo-night')
  })
})

describe('applyStyle', () => {
  it('sets data-style on <html>', () => {
    applyStyle('compact')
    expect(document.documentElement.getAttribute('data-style')).toBe('compact')
  })

  it('changes data-style when a different style is applied', () => {
    applyStyle('flat')
    expect(document.documentElement.getAttribute('data-style')).toBe('flat')
    applyStyle('default')
    expect(document.documentElement.getAttribute('data-style')).toBe('default')
  })
})

// ---------------------------------------------------------------------------
// applyAccentColor — injected <style> override
// ---------------------------------------------------------------------------

describe('applyAccentColor', () => {
  afterEach(() => {
    // Clean up any injected style element between tests
    document.getElementById('chatwire-accent-override')?.remove()
  })

  it('injects a <style> element overriding --primary with HSL value', () => {
    applyAccentColor('#ff0000')
    const el = document.getElementById('chatwire-accent-override')
    expect(el).not.toBeNull()
    // #ff0000 = hsl(0 100% 50%) → "0 100% 50%"
    expect(el?.textContent).toContain('--primary:')
    expect(el?.textContent).toContain('0 100% 50%')
  })

  it('removes the element when color is empty', () => {
    applyAccentColor('#ff0000')
    expect(document.getElementById('chatwire-accent-override')).not.toBeNull()
    applyAccentColor('')
    expect(document.getElementById('chatwire-accent-override')).toBeNull()
  })

  it('updates the existing element on subsequent calls (no duplicates)', () => {
    applyAccentColor('#ff0000')
    applyAccentColor('#00ff00')
    const els = document.querySelectorAll('#chatwire-accent-override')
    expect(els.length).toBe(1)
    // #00ff00 = hsl(120 100% 50%) → contains "120"
    expect(els[0].textContent).toContain('120')
  })

  it('is a no-op when color is empty and element is absent', () => {
    // Should not throw
    applyAccentColor('')
    expect(document.getElementById('chatwire-accent-override')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// applyCustomCss — injected <style> override
// ---------------------------------------------------------------------------

describe('applyCustomCss', () => {
  afterEach(() => {
    document.getElementById('chatwire-custom-css')?.remove()
  })

  it('injects a <style> element with the provided CSS', () => {
    applyCustomCss('.foo { color: red; }')
    const el = document.getElementById('chatwire-custom-css')
    expect(el).not.toBeNull()
    expect(el?.textContent).toBe('.foo { color: red; }')
  })

  it('removes the element when css is empty', () => {
    applyCustomCss('.foo { color: red; }')
    expect(document.getElementById('chatwire-custom-css')).not.toBeNull()
    applyCustomCss('')
    expect(document.getElementById('chatwire-custom-css')).toBeNull()
  })

  it('updates the existing element on subsequent calls (no duplicates)', () => {
    applyCustomCss('.a { color: red; }')
    applyCustomCss('.b { color: blue; }')
    const els = document.querySelectorAll('#chatwire-custom-css')
    expect(els.length).toBe(1)
    expect(els[0].textContent).toBe('.b { color: blue; }')
  })

  it('is a no-op when css is empty and element is absent', () => {
    applyCustomCss('')
    expect(document.getElementById('chatwire-custom-css')).toBeNull()
  })

  it('supports per-theme scoping via [data-theme] selectors', () => {
    const css = '[data-theme="dracula"] .widget { background: #282a36; }'
    applyCustomCss(css)
    expect(document.getElementById('chatwire-custom-css')?.textContent).toBe(css)
  })
})

// ---------------------------------------------------------------------------
// useTheme hook — setTheme / setStyle / setAccentColor / setCustomCss
// ---------------------------------------------------------------------------

describe('useTheme hook', () => {
  beforeEach(() => {
    localStorage.clear()
    document.getElementById('chatwire-accent-override')?.remove()
    document.getElementById('chatwire-custom-css')?.remove()
    vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ themes: [], current: 'dracula', accent_color: '', custom_css: '' }),
    } as Response)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    document.getElementById('chatwire-accent-override')?.remove()
    document.getElementById('chatwire-custom-css')?.remove()
  })

  it('setTheme applies data-theme attribute', async () => {
    const { result } = renderHook(() => useTheme())
    await act(async () => {
      await result.current.setTheme('github-dark')
    })
    expect(document.documentElement.getAttribute('data-theme')).toBe('github-dark')
  })

  it('setStyle applies data-style attribute', async () => {
    const { result } = renderHook(() => useTheme())
    await act(async () => {
      result.current.setStyle('compact')
    })
    expect(document.documentElement.getAttribute('data-style')).toBe('compact')
  })

  it('setAccentColor injects the accent override style with HSL --primary', async () => {
    const { result } = renderHook(() => useTheme())
    await act(async () => {
      await result.current.setAccentColor('#bd93f9')
    })
    const el = document.getElementById('chatwire-accent-override')
    // #bd93f9 ≈ hsl(265 89% 78%) — just verify --primary is set
    expect(el?.textContent).toContain('--primary:')
    expect(result.current.currentAccent).toBe('#bd93f9')
  })

  it('setAccentColor with empty string clears the override', async () => {
    const { result } = renderHook(() => useTheme())
    await act(async () => {
      await result.current.setAccentColor('#ff0000')
    })
    await act(async () => {
      await result.current.setAccentColor('')
    })
    expect(document.getElementById('chatwire-accent-override')).toBeNull()
    expect(result.current.currentAccent).toBe('')
  })

  it('setCustomCss injects a custom <style> element and updates state', async () => {
    const { result } = renderHook(() => useTheme())
    const css = '.test { color: pink; }'
    await act(async () => {
      await result.current.setCustomCss(css)
    })
    expect(document.getElementById('chatwire-custom-css')?.textContent).toBe(css)
    expect(result.current.customCss).toBe(css)
  })

  it('setCustomCss with empty string clears the custom style element', async () => {
    const { result } = renderHook(() => useTheme())
    await act(async () => {
      await result.current.setCustomCss('.x { margin: 0; }')
    })
    await act(async () => {
      await result.current.setCustomCss('')
    })
    expect(document.getElementById('chatwire-custom-css')).toBeNull()
    expect(result.current.customCss).toBe('')
  })
})
