/**
 * useTheme — applies and persists the active color scheme and structural style.
 *
 * Color scheme  → data-theme attribute on <html>  (Layer 2)
 * Structural style → data-style attribute on <html>  (Layer 1)
 *
 * Priority for initial scheme:
 *   1. localStorage key "chatwire-theme"
 *   2. Server setting from GET /api/ui/themes (reconciled on mount)
 *   3. Fall back to "dracula"
 */
import { useState, useEffect, useCallback } from 'react'

const LS_KEY_THEME = 'chatwire-theme'
const LS_KEY_STYLE = 'chatwire-style'
const LS_KEY_ACCENT = 'chatwire-accent'
const LS_KEY_CUSTOM_CSS = 'chatwire-custom-css'

/** ID of the injected <style> element that overrides --color-accent. */
const _ACCENT_STYLE_ID = 'chatwire-accent-override'

/** ID of the injected <style> element for user-defined custom CSS. */
const _CUSTOM_CSS_STYLE_ID = 'chatwire-custom-css'

// ---------------------------------------------------------------------------
// Scheme metadata (used by the theme picker UI)
// ---------------------------------------------------------------------------

export interface SchemeInfo {
  name: string
  label: string
  isLight: boolean
  /** Accent hex swatch (used as color dot in picker) */
  swatch: string
}

export const allSchemes: SchemeInfo[] = [
  { name: 'dracula',              label: 'Dracula',              isLight: false, swatch: '#bd93f9' },
  { name: 'default',              label: 'Default',              isLight: true,  swatch: '#3b82f6' },
  { name: 'catppuccin-frappe',    label: 'Catppuccin Frappé',    isLight: false, swatch: '#ca9ee6' },
  { name: 'catppuccin-latte',     label: 'Catppuccin Latte',     isLight: true,  swatch: '#8839ef' },
  { name: 'catppuccin-macchiato', label: 'Catppuccin Macchiato', isLight: false, swatch: '#c6a0f6' },
  { name: 'catppuccin-mocha',     label: 'Catppuccin Mocha',     isLight: false, swatch: '#cba6f7' },
  { name: 'github-dark',          label: 'GitHub Dark',          isLight: false, swatch: '#4493f8' },
  { name: 'github-light',         label: 'GitHub Light',         isLight: true,  swatch: '#0969da' },
  { name: 'gruvbox',              label: 'Gruvbox',              isLight: false, swatch: '#d65d0e' },
  { name: 'gruvbox-light',        label: 'Gruvbox Light',        isLight: true,  swatch: '#af3a03' },
  { name: 'night-owl',            label: 'Night Owl',            isLight: false, swatch: '#82aaff' },
  { name: 'nord',                 label: 'Nord',                 isLight: false, swatch: '#88c0d0' },
  { name: 'one-dark',             label: 'One Dark',             isLight: false, swatch: '#61afef' },
  { name: 'one-light',            label: 'One Light',            isLight: true,  swatch: '#4078f2' },
  { name: 'rose-pine',            label: 'Rosé Pine',            isLight: false, swatch: '#c4a7e7' },
  { name: 'rose-pine-dawn',       label: 'Rosé Pine Dawn',       isLight: true,  swatch: '#907aa9' },
  { name: 'rose-pine-moon',       label: 'Rosé Pine Moon',       isLight: false, swatch: '#c4a7e7' },
  { name: 'solarized-dark',       label: 'Solarized Dark',       isLight: false, swatch: '#268bd2' },
  { name: 'solarized-light',      label: 'Solarized Light',      isLight: true,  swatch: '#268bd2' },
  { name: 'tokyo-night',          label: 'Tokyo Night',          isLight: false, swatch: '#7aa2f7' },
  { name: 'system',               label: 'System',               isLight: false, swatch: '#888888' },
]

// ---------------------------------------------------------------------------
// Style metadata
// ---------------------------------------------------------------------------

export interface StyleInfo {
  name: string
  label: string
  description: string
}

export const allStyles: StyleInfo[] = [
  { name: 'default', label: 'Default', description: 'Rounded, comfortable spacing' },
  { name: 'compact', label: 'Compact', description: 'Tight spacing, small radius' },
  { name: 'flat',    label: 'Flat',    description: 'No radius, flat shadows' },
]

// ---------------------------------------------------------------------------
// Imperative helpers (usable outside React, e.g. in main.tsx)
// ---------------------------------------------------------------------------

/** Apply a color scheme by setting data-theme on <html>. */
export function applyTheme(name: string): void {
  document.documentElement.setAttribute('data-theme', name)
}

/** Apply a structural style by setting data-style on <html>. */
export function applyStyle(name: string): void {
  document.documentElement.setAttribute('data-style', name)
}

/**
 * Apply (or clear) a user accent color override.
 *
 * When `color` is non-empty, a `<style id="chatwire-accent-override">` element
 * is injected into `<head>` that overrides `--primary` on `:root` with the
 * HSL-converted value of the hex color. This sits above schemes.css in cascade
 * order, so it wins regardless of which theme is active.
 *
 * When `color` is empty the injected element is removed and the theme default
 * takes over again.
 */
export function applyAccentColor(color: string): void {
  let el = document.getElementById(_ACCENT_STYLE_ID) as HTMLStyleElement | null
  if (!color) {
    el?.remove()
    return
  }
  if (!el) {
    el = document.createElement('style')
    el.id = _ACCENT_STYLE_ID
    document.head.appendChild(el)
  }
  // Convert hex to HSL triplet and override --primary (shadcn accent var).
  const hsl = _hexToHsl(color)
  el.textContent = `:root { --primary: ${hsl}; }`
}

/**
 * Inject (or clear) a user-defined custom CSS block.
 *
 * When `css` is non-empty, a `<style id="chatwire-custom-css">` element is
 * appended to `<head>` containing the raw CSS string.  This sits above all
 * theme CSS in cascade order, so users can use `[data-theme="X"] { }` selectors
 * to scope rules to a specific theme.
 *
 * When `css` is empty the element is removed and no overrides are active.
 */
export function applyCustomCss(css: string): void {
  let el = document.getElementById(_CUSTOM_CSS_STYLE_ID) as HTMLStyleElement | null
  if (!css) {
    el?.remove()
    return
  }
  if (!el) {
    el = document.createElement('style')
    el.id = _CUSTOM_CSS_STYLE_ID
    document.head.appendChild(el)
  }
  el.textContent = css
}

/** Convert a 6-digit hex color (#rrggbb) to "H S% L%" HSL string. */
function _hexToHsl(hex: string): string {
  const h = hex.replace('#', '')
  const r = parseInt(h.slice(0, 2), 16) / 255
  const g = parseInt(h.slice(2, 4), 16) / 255
  const b = parseInt(h.slice(4, 6), 16) / 255
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b)
  const l = (mx + mn) / 2
  if (mx === mn) return `0 0% ${Math.round(l * 100)}%`
  const d = mx - mn
  const s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn)
  let hue: number
  if (mx === r) hue = ((g - b) / d + (g < b ? 6 : 0)) / 6
  else if (mx === g) hue = ((b - r) / d + 2) / 6
  else hue = ((r - g) / d + 4) / 6
  return `${Math.round(hue * 360)} ${Math.round(s * 100)}% ${Math.round(l * 100)}%`
}

/** Persist the scheme choice in localStorage and on the server. */
async function persistTheme(name: string): Promise<void> {
  localStorage.setItem(LS_KEY_THEME, name)
  try {
    const fd = new FormData()
    fd.append('theme', name)
    await fetch('/api/ui/themes', { method: 'POST', body: fd, credentials: 'same-origin' })
  } catch {
    // Best-effort — the local theme is already applied; server sync is non-blocking.
  }
}

/** Persist the style choice in localStorage. */
function persistStyle(name: string): void {
  localStorage.setItem(LS_KEY_STYLE, name)
}

/** Persist the accent color to localStorage and on the server. */
async function persistAccentColor(color: string): Promise<void> {
  localStorage.setItem(LS_KEY_ACCENT, color)
  try {
    const fd = new FormData()
    fd.append('color', color)
    await fetch('/api/ui/settings/accent_color', { method: 'POST', body: fd, credentials: 'same-origin' })
  } catch {
    // Best-effort — the local override is already applied.
  }
}

/** Persist the custom CSS to localStorage and on the server. */
async function persistCustomCss(css: string): Promise<void> {
  localStorage.setItem(LS_KEY_CUSTOM_CSS, css)
  try {
    await fetch('/api/settings/custom_css', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ custom_css: css }),
    })
  } catch {
    // Best-effort — the local override is already applied.
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useTheme() {
  const [current, setCurrent] = useState<string>(
    () => localStorage.getItem(LS_KEY_THEME) ?? 'dracula',
  )
  const [currentStyle, setCurrentStyle] = useState<string>(
    () => localStorage.getItem(LS_KEY_STYLE) ?? 'default',
  )
  const [currentAccent, setCurrentAccent] = useState<string>(
    () => localStorage.getItem(LS_KEY_ACCENT) ?? '',
  )
  const [customCss, setCustomCssState] = useState<string>(
    () => localStorage.getItem(LS_KEY_CUSTOM_CSS) ?? '',
  )
  const [loading, setLoading] = useState(true)

  // Apply scheme/style/accent/customCss from localStorage immediately; reconcile with server on mount.
  useEffect(() => {
    applyTheme(current)
    applyStyle(currentStyle)
    applyAccentColor(currentAccent)
    applyCustomCss(customCss)

    const themeP = fetch('/api/ui/themes', { credentials: 'same-origin' })
      .then((r) => r.json())
      .then((data: { themes: string[]; current: string }) => {
        const fromServer = data.current
        const fromLocal = localStorage.getItem(LS_KEY_THEME)
        const effective = fromLocal ?? fromServer
        if (effective !== current) {
          setCurrent(effective)
          applyTheme(effective)
        }
      })
      .catch(() => {/* offline or unauthenticated — keep current */})

    const accentP = fetch('/api/ui/settings/accent_color', { credentials: 'same-origin' })
      .then((r) => r.json())
      .then((data: { accent_color: string }) => {
        const fromServer = data.accent_color
        const fromLocal = localStorage.getItem(LS_KEY_ACCENT)
        // localStorage takes priority (user changed it in this browser)
        const effective = fromLocal !== null ? fromLocal : fromServer
        if (effective !== currentAccent) {
          setCurrentAccent(effective)
          applyAccentColor(effective)
        }
      })
      .catch(() => {/* best-effort */})

    const customCssP = fetch('/api/ui/settings/custom_css', { credentials: 'same-origin' })
      .then((r) => r.json())
      .then((data: { custom_css: string }) => {
        const fromServer = data.custom_css ?? ''
        const fromLocal = localStorage.getItem(LS_KEY_CUSTOM_CSS)
        // localStorage takes priority (user changed it in this browser)
        const effective = fromLocal !== null ? fromLocal : fromServer
        if (effective !== customCss) {
          setCustomCssState(effective)
          applyCustomCss(effective)
        }
      })
      .catch(() => {/* best-effort */})

    Promise.all([themeP, accentP, customCssP]).finally(() => setLoading(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const setTheme = useCallback(async (name: string) => {
    setCurrent(name)
    applyTheme(name)
    await persistTheme(name)
  }, [])

  const setStyle = useCallback((name: string) => {
    setCurrentStyle(name)
    applyStyle(name)
    persistStyle(name)
  }, [])

  const setAccentColor = useCallback(async (color: string) => {
    setCurrentAccent(color)
    applyAccentColor(color)
    await persistAccentColor(color)
  }, [])

  const setCustomCss = useCallback(async (css: string) => {
    setCustomCssState(css)
    applyCustomCss(css)
    await persistCustomCss(css)
  }, [])

  return { current, currentStyle, currentAccent, customCss, setTheme, setStyle, setAccentColor, setCustomCss, allSchemes, allStyles, loading }
}
