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
import { useState, useEffect, useCallback, useRef } from 'react'

const LS_KEY_THEME = 'chatwire-theme'
const LS_KEY_STYLE = 'chatwire-style'
const LS_KEY_ACCENT = 'chatwire-accent'
/** Per-theme custom CSS map: JSON-encoded Record<slug, rawCss>. Supersedes legacy 'chatwire-custom-css' key. */
const LS_KEY_CUSTOM_CSS_THEMES = 'chatwire-custom-css-themes'
const LS_KEY_AUTO_DARK = 'chatwire-auto-dark'
const LS_KEY_AUTO_LIGHT = 'chatwire-auto-light'
const LS_KEY_THEME_MODE = 'chatwire-theme-mode'
const LS_KEY_DECORATIONS = 'chatwire-decorations'
const LS_KEY_THEME_PACK = 'chatwire-theme-pack'

/** Per-theme custom CSS map (slug → raw user CSS, not yet scoped). */
export type CustomCssThemeMap = Record<string, string>

/** ID of the injected <style> element that overrides --color-accent. */
const _ACCENT_STYLE_ID = 'chatwire-accent-override'

/** ID of the injected <style> element for user-defined custom CSS. */
const _CUSTOM_CSS_STYLE_ID = 'chatwire-custom-css'

/** ID of the injected <style> element for the active theme pack CSS. */
const _THEME_PACK_STYLE_ID = 'chatwire-theme-pack'

/** ID of the injected <style> element for per-theme color overrides. */
const _THEME_OVERRIDE_STYLE_ID = 'chatwire-theme-override'

/** ID of the injected <style> element for CSS contributed by theme plugins. */
const _PLUGIN_THEMES_STYLE_ID = 'chatwire-plugin-themes'

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
  { name: 'solarized-dark',       label: 'Solarized Dark',       isLight: false, swatch: '#268bd2' },
  { name: 'solarized-light',      label: 'Solarized Light',      isLight: true,  swatch: '#268bd2' },
  { name: 'tokyo-night',          label: 'Tokyo Night',          isLight: false, swatch: '#7aa2f7' },
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
 * Inject (or clear) the combined per-theme custom CSS block.
 *
 * When `css` is non-empty, a `<style id="chatwire-custom-css">` element is
 * appended to `<head>` containing the pre-scoped CSS string.  Each rule is
 * already wrapped in ``[data-theme="slug"] { … }`` by the caller, so it
 * only applies when that theme is active on ``<html>``.
 *
 * When `css` is empty the element is removed and no custom overrides are active.
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

/** Load the per-theme custom CSS map from localStorage, or return {}. */
function _loadCustomCssMap(): CustomCssThemeMap {
  try {
    const raw = localStorage.getItem(LS_KEY_CUSTOM_CSS_THEMES)
    if (raw) return JSON.parse(raw) as CustomCssThemeMap
  } catch {
    // corrupted — ignore
  }
  return {}
}

/**
 * Build combined scoped CSS from a per-theme map.
 *
 * Each entry is wrapped with ``[data-theme="slug"] { rawCss }`` using CSS
 * nesting so the rules only activate when that theme is active on ``<html>``.
 * Slugs that don't match ``/^[a-z0-9][a-z0-9-]*$/`` are skipped for safety.
 */
export function buildCombinedCustomCss(map: CustomCssThemeMap): string {
  const blocks: string[] = []
  for (const [slug, css] of Object.entries(map)) {
    if (css && css.trim() && /^[a-z0-9][a-z0-9-]*$/.test(slug)) {
      blocks.push(`[data-theme="${slug}"] {\n${css}\n}`)
    }
  }
  return blocks.join('\n\n')
}

// ---------------------------------------------------------------------------
// Decoration slots
// ---------------------------------------------------------------------------

/** Known decoration CSS variable names (matches themes.css). */
export type DecorationKey =
  | 'avatar-shape'
  | 'avatar-size'
  | 'avatar-border'
  | 'bubble-shadow'
  | 'bubble-tail'
  | 'header-shadow'
  | 'header-border'
  | 'sidebar-divider'
  | 'border-width'
  | 'transition-speed'

export type DecorationMap = Partial<Record<DecorationKey, string>>

/**
 * Apply one or more decoration CSS variable overrides on :root.
 * Pass an empty map to clear all overrides.
 */
export function applyDecorations(overrides: DecorationMap): void {
  const root = document.documentElement
  for (const [key, value] of Object.entries(overrides) as [DecorationKey, string][]) {
    if (value) {
      root.style.setProperty(`--${key}`, value)
    } else {
      root.style.removeProperty(`--${key}`)
    }
  }
}

/** Read stored decoration overrides from localStorage. */
export function loadStoredDecorations(): DecorationMap {
  try {
    const raw = localStorage.getItem(LS_KEY_DECORATIONS)
    if (raw) return JSON.parse(raw) as DecorationMap
  } catch {
    // corrupted — ignore
  }
  return {}
}

/** Persist decoration overrides to localStorage. */
export function saveDecorations(overrides: DecorationMap): void {
  localStorage.setItem(LS_KEY_DECORATIONS, JSON.stringify(overrides))
}

// ---------------------------------------------------------------------------
// Theme pack
// ---------------------------------------------------------------------------

/**
 * Inject theme-pack CSS into `<head>` and set data-theme-pack on <html>.
 * Pass empty string to clear.
 */
export function applyThemePackCss(name: string, css: string): void {
  // Update data attribute
  if (name) {
    document.documentElement.setAttribute('data-theme-pack', name)
  } else {
    document.documentElement.removeAttribute('data-theme-pack')
  }
  // Inject/remove style element
  let el = document.getElementById(_THEME_PACK_STYLE_ID) as HTMLStyleElement | null
  if (!css) {
    el?.remove()
    return
  }
  if (!el) {
    el = document.createElement('style')
    el.id = _THEME_PACK_STYLE_ID
    document.head.appendChild(el)
  }
  el.textContent = css
}

/**
 * Inject (or clear) per-theme color override CSS.
 *
 * The CSS is generated by the backend (``GET /api/ui/theme-override/css``) and
 * contains ``[data-theme="<slug>"] { --var: value; … }`` blocks.  These sit
 * above the built-in schemes.css in cascade order and therefore override the
 * theme defaults without needing the active theme pack to be set.
 */
export function applyThemeOverride(css: string): void {
  let el = document.getElementById(_THEME_OVERRIDE_STYLE_ID) as HTMLStyleElement | null
  if (!css) {
    el?.remove()
    return
  }
  if (!el) {
    el = document.createElement('style')
    el.id = _THEME_OVERRIDE_STYLE_ID
    document.head.appendChild(el)
  }
  el.textContent = css
}

/** Fetch and apply all stored theme color overrides on page load. */
export async function restoreThemeOverride(): Promise<void> {
  try {
    const r = await fetch('/api/ui/theme-override/css', { credentials: 'same-origin' })
    if (r.ok) {
      const data = (await r.json()) as { css: string }
      applyThemeOverride(data.css)
    }
  } catch {
    // offline — skip
  }
}

/** Restore the persisted theme pack on page load. */
export async function restoreThemePack(): Promise<void> {
  const name = localStorage.getItem(LS_KEY_THEME_PACK)
  if (!name) return
  try {
    const fd = new FormData()
    fd.append('name', name)
    const r = await fetch('/api/ui/theme-packages/apply', {
      method: 'POST',
      body: fd,
      credentials: 'same-origin',
    })
    if (r.ok) {
      const data = (await r.json()) as { name: string; css: string }
      applyThemePackCss(data.name, data.css)
    }
  } catch {
    // offline — skip
  }
}

/**
 * Restore CSS contributed by installed theme plugins on page load.
 *
 * Fetches ``GET /api/ui/plugin-themes`` and injects the returned CSS into
 * a ``<style id="chatwire-plugin-themes">`` element.  Call this early (before
 * React mounts) to avoid a flash of unstyled plugin schemes.
 */
export async function restorePluginThemes(): Promise<void> {
  try {
    const r = await fetch('/api/ui/plugin-themes', { credentials: 'same-origin' })
    if (r.ok) {
      const data = (await r.json()) as { schemes: SchemeInfo[]; css: string }
      let el = document.getElementById(_PLUGIN_THEMES_STYLE_ID) as HTMLStyleElement | null
      if (data.css) {
        if (!el) {
          el = document.createElement('style')
          el.id = _PLUGIN_THEMES_STYLE_ID
          document.head.appendChild(el)
        }
        el.textContent = data.css
      } else {
        el?.remove()
      }
    }
  } catch {
    // offline — skip
  }
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

/** Persist per-theme custom CSS to the server. */
async function persistCustomCss(theme: string, css: string): Promise<void> {
  try {
    await fetch('/api/settings/custom_css', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme, custom_css: css }),
    })
  } catch {
    // Best-effort — the local override is already applied.
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/** Persist the theme_mode setting to localStorage and server. */
async function persistThemeMode(mode: string): Promise<void> {
  localStorage.setItem(LS_KEY_THEME_MODE, mode)
  try {
    await fetch('/api/ui/settings', {
      method: 'PATCH',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme_mode: mode }),
    })
  } catch {
    // Best-effort — local state is already updated.
  }
}

export function useTheme() {
  const [currentStyle, setCurrentStyle] = useState<string>(
    () => localStorage.getItem(LS_KEY_STYLE) ?? 'default',
  )
  const [currentAccent, setCurrentAccent] = useState<string>(
    () => localStorage.getItem(LS_KEY_ACCENT) ?? '',
  )
  /** Per-theme custom CSS map: slug → raw user CSS. */
  const [customCssMap, setCustomCssMapState] = useState<CustomCssThemeMap>(_loadCustomCssMap)
  /** Active color scheme slug (kept in sync with the data-theme attribute). */
  const [activeScheme, setActiveScheme] = useState<string>(
    () => localStorage.getItem(LS_KEY_THEME) ?? 'dracula',
  )
  const [autoDark, setAutoDarkState] = useState<string>(
    () => localStorage.getItem(LS_KEY_AUTO_DARK) ?? 'dracula',
  )
  const [autoLight, setAutoLightState] = useState<string>(
    () => localStorage.getItem(LS_KEY_AUTO_LIGHT) ?? 'github-light',
  )
  const [themeMode, setThemeModeState] = useState<'auto' | 'light' | 'dark'>(() => {
    const stored = localStorage.getItem(LS_KEY_THEME_MODE)
    if (stored === 'light' || stored === 'dark') return stored
    return 'auto'
  })
  const [pluginSchemes, setPluginSchemes] = useState<SchemeInfo[]>([])
  const [loading, setLoading] = useState(true)

  // Stable ref to state setters so the callback below never needs them as deps.
  const _setAutoDarkState = useRef(setAutoDarkState)
  const _setAutoLightState = useRef(setAutoLightState)
  _setAutoDarkState.current = setAutoDarkState
  _setAutoLightState.current = setAutoLightState

  /**
   * Fetch the latest plugin-themes data, re-inject the CSS <style> element,
   * and update `pluginSchemes` state.  Called once on mount and again whenever
   * a `chatwire-plugin-themes-changed` event is dispatched (e.g. after the
   * user installs or removes a theme plugin from the marketplace).
   */
  const refreshPluginThemes = useCallback(async () => {
    try {
      const r = await fetch('/api/ui/plugin-themes', { credentials: 'same-origin' })
      if (!r.ok) return
      const data = (await r.json()) as { schemes: SchemeInfo[]; css: string }
      let el = document.getElementById(_PLUGIN_THEMES_STYLE_ID) as HTMLStyleElement | null
      if (data.css) {
        if (!el) {
          el = document.createElement('style')
          el.id = _PLUGIN_THEMES_STYLE_ID
          document.head.appendChild(el)
        }
        el.textContent = data.css
      } else {
        el?.remove()
      }
      const valid = (data.schemes ?? []).filter(
        (s) => s && typeof s.name === 'string' && typeof s.label === 'string',
      )
      setPluginSchemes(valid)
      // Fallback: if the stored dark/light scheme is not in the merged list,
      // reset to a built-in default so the UI doesn't get stuck on a missing theme.
      const effectiveNames = new Set([
        ...allSchemes.map((s) => s.name),
        ...valid.map((s) => s.name),
      ])
      const storedDark = localStorage.getItem(LS_KEY_AUTO_DARK) ?? 'dracula'
      const storedLight = localStorage.getItem(LS_KEY_AUTO_LIGHT) ?? 'github-light'
      if (!effectiveNames.has(storedDark)) {
        localStorage.setItem(LS_KEY_AUTO_DARK, 'dracula')
        _setAutoDarkState.current('dracula')
      }
      if (!effectiveNames.has(storedLight)) {
        localStorage.setItem(LS_KEY_AUTO_LIGHT, 'github-light')
        _setAutoLightState.current('github-light')
      }
    } catch {
      // offline — skip
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Listen for theme plugin install/uninstall events so the picker refreshes
  // without a full page reload.
  useEffect(() => {
    const handler = () => { void refreshPluginThemes() }
    window.addEventListener('chatwire-plugin-themes-changed', handler)
    return () => window.removeEventListener('chatwire-plugin-themes-changed', handler)
  }, [refreshPluginThemes])

  // Apply the correct scheme based on themeMode, reacting to autoDark/autoLight changes
  // and OS preference changes when in auto mode.
  useEffect(() => {
    if (themeMode === 'auto') {
      const mq = window.matchMedia('(prefers-color-scheme: dark)')
      const apply = () => {
        const scheme = mq.matches ? autoDark : autoLight
        applyTheme(scheme)
        localStorage.setItem(LS_KEY_THEME, scheme)
        setActiveScheme(scheme)
      }
      apply()
      mq.addEventListener('change', apply)
      return () => mq.removeEventListener('change', apply)
    } else if (themeMode === 'light') {
      applyTheme(autoLight)
      localStorage.setItem(LS_KEY_THEME, autoLight)
      setActiveScheme(autoLight)
    } else {
      applyTheme(autoDark)
      localStorage.setItem(LS_KEY_THEME, autoDark)
      setActiveScheme(autoDark)
    }
  }, [themeMode, autoDark, autoLight])

  // Apply style/accent/customCss from localStorage immediately; reconcile with server on mount.
  useEffect(() => {
    applyStyle(currentStyle)
    applyAccentColor(currentAccent)
    applyCustomCss(buildCombinedCustomCss(customCssMap))

    const themeModeP = fetch('/api/ui/settings', { credentials: 'same-origin' })
      .then((r) => r.json())
      .then((data: { theme_mode: string }) => {
        const fromServer = (data.theme_mode === 'light' || data.theme_mode === 'dark')
          ? data.theme_mode as 'light' | 'dark'
          : 'auto'
        const fromLocal = localStorage.getItem(LS_KEY_THEME_MODE)
        const effective: 'auto' | 'light' | 'dark' =
          (fromLocal === 'light' || fromLocal === 'dark' || fromLocal === 'auto')
            ? fromLocal
            : fromServer
        if (effective !== themeMode) {
          setThemeModeState(effective)
        }
      })
      .catch(() => {/* offline or unauthenticated — keep current */})

    const accentP = fetch('/api/ui/settings/accent_color', { credentials: 'same-origin' })
      .then((r) => r.json())
      .then((data: { accent_color: string }) => {
        const fromServer = data.accent_color
        const fromLocal = localStorage.getItem(LS_KEY_ACCENT)
        const effective = fromLocal !== null ? fromLocal : fromServer
        if (effective !== currentAccent) {
          setCurrentAccent(effective)
          applyAccentColor(effective)
        }
      })
      .catch(() => {/* best-effort */})

    // Fetch combined per-theme CSS from server; merge with localStorage (local wins per-slug).
    const customCssP = fetch('/api/ui/custom-css/combined', { credentials: 'same-origin' })
      .then((r) => r.json())
      .then((data: { css: string; themes: CustomCssThemeMap }) => {
        const serverThemes = data.themes ?? {}
        const localMap = _loadCustomCssMap()
        // Local always wins for any slug that exists in both (same semantics as other settings).
        const merged: CustomCssThemeMap = { ...serverThemes, ...localMap }
        setCustomCssMapState(merged)
        // Use server's pre-built combined CSS (authoritative), falling back to locally built.
        applyCustomCss(data.css || buildCombinedCustomCss(merged))
      })
      .catch(() => {/* best-effort — offline or old server */})

    const overrideP = restoreThemeOverride().catch(() => {/* best-effort */})

    // Load CSS and scheme metadata contributed by installed theme plugins.
    const pluginThemesP = refreshPluginThemes()

    Promise.all([themeModeP, accentP, customCssP, overrideP, pluginThemesP]).finally(() => setLoading(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const setThemeMode = useCallback(async (mode: 'auto' | 'light' | 'dark') => {
    setThemeModeState(mode)
    await persistThemeMode(mode)
  }, [])

  const setAutoDark = useCallback((name: string) => {
    setAutoDarkState(name)
    localStorage.setItem(LS_KEY_AUTO_DARK, name)
  }, [])

  const setAutoLight = useCallback((name: string) => {
    setAutoLightState(name)
    localStorage.setItem(LS_KEY_AUTO_LIGHT, name)
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

  /** Save CSS for the active scheme, update the map, and re-inject combined CSS. */
  const setCustomCss = useCallback(async (css: string) => {
    const newMap: CustomCssThemeMap = { ...customCssMap }
    if (css.trim()) {
      newMap[activeScheme] = css
    } else {
      delete newMap[activeScheme]
    }
    setCustomCssMapState(newMap)
    localStorage.setItem(LS_KEY_CUSTOM_CSS_THEMES, JSON.stringify(newMap))
    applyCustomCss(buildCombinedCustomCss(newMap))
    await persistCustomCss(activeScheme, css)
  }, [activeScheme, customCssMap])

  /** Raw CSS for the currently active theme (empty string if none saved). */
  const customCss = customCssMap[activeScheme] ?? ''

  return {
    themeMode, setThemeMode,
    currentStyle, setStyle,
    currentAccent, setAccentColor,
    customCss, setCustomCss,
    activeScheme,
    autoDark, setAutoDark,
    autoLight, setAutoLight,
    allSchemes: pluginSchemes.length > 0 ? [...allSchemes, ...pluginSchemes] : allSchemes,
    allStyles,
    loading,
  }
}
