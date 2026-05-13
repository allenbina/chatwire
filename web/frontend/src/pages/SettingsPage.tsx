/**
 * Settings page — full port of the Jinja2 _settings.html accordion UI.
 *
 * Phase 3: All settings sections are implemented here. Each section maps
 * directly to the corresponding accordion section in the Jinja2 template.
 * Settings are fetched from / persisted to the existing /api/settings/*
 * and /api/ui/* endpoints.
 */
import { useState, useRef, useEffect } from 'react'
import { LogOut, Pin, PinOff } from 'lucide-react'
import { usePinnedSettings, type PinnableKey } from '../hooks/usePinnedSettings'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useLocation } from 'react-router-dom'
import { toast } from 'sonner'
import { Layout } from '../components/Layout'
import {
  useTheme,
  applyThemeOverride,
  applyThemePackCss,
  restoreThemeOverride,
} from '../hooks/useTheme'
import { configureSounds, type SoundsConfig, type SoundMode } from '../hooks/useSounds'
import { SlotRenderer } from '../plugins/SlotRenderer'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

// ---------------------------------------------------------------------------
// Shared primitives
// ---------------------------------------------------------------------------

function SaveButton({ pending }: { pending?: boolean }) {
  return (
    <Button type="submit" disabled={pending} size="sm">
      {pending ? 'Saving…' : 'Save'}
    </Button>
  )
}

function SaveOk({ visible }: { visible: boolean }) {
  if (!visible) return null
  return <span className="text-xs text-success">Saved</span>
}

/**
 * Pin / unpin a setting toggle to the sidebar footer.
 * Rendered inline in section labels inside SettingsPage.
 */
function PinButton({ settingKey }: { settingKey: PinnableKey }) {
  const { isPinned, togglePin } = usePinnedSettings()
  const pinned = isPinned(settingKey)
  return (
    <button
      type="button"
      onClick={() => togglePin(settingKey)}
      className={`ml-1.5 p-0.5 rounded transition-colors ${
        pinned
          ? 'text-primary hover:text-primary/70'
          : 'text-muted-foreground/40 hover:text-muted-foreground'
      }`}
      title={pinned ? 'Remove from sidebar' : 'Pin to sidebar'}
      aria-label={pinned ? 'Remove from sidebar' : 'Pin to sidebar'}
      aria-pressed={pinned}
    >
      {pinned ? <PinOff className="w-3 h-3" /> : <Pin className="w-3 h-3" />}
    </button>
  )
}

/** POST a FormData to an endpoint; shows the ok flash briefly on success. */
function useSettingsMutation(url: string) {
  const [saved, setSaved] = useState(false)
  const mutation = useMutation({
    mutationFn: (fd: FormData) =>
      fetch(url, { method: 'POST', body: fd, credentials: 'same-origin' }).then((r) => {
        if (!r.ok) throw new Error(`${r.status}`)
        return r
      }),
    onSuccess: () => {
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })
  return { mutation, saved }
}

// ---------------------------------------------------------------------------
// Theme section
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Accent color picker — hex text input + swatch; native picker as fallback
// ---------------------------------------------------------------------------

const HEX_RE = /^#[0-9a-fA-F]{6}$/

interface AccentColorPickerProps {
  /** Current saved accent color ("#rrggbb") or "" for theme default. */
  value: string
  /** Called with a valid "#rrggbb" or "" (reset). */
  onChange: (color: string) => void
}

export function AccentColorPicker({ value, onChange }: AccentColorPickerProps) {
  const [draft, setDraft] = useState(value)
  const nativeRef = useRef<HTMLInputElement>(null)

  // Keep draft in sync when parent resets the value (e.g. "Reset" click).
  useEffect(() => {
    setDraft(value)
  }, [value])

  // The swatch shows draft color when valid, else the saved value, else CSS var.
  const swatchColor = HEX_RE.test(draft)
    ? draft
    : HEX_RE.test(value)
      ? value
      : 'hsl(var(--primary))'

  const isDraftInvalid = draft !== '' && !HEX_RE.test(draft)

  function handleTextChange(e: React.ChangeEvent<HTMLInputElement>) {
    const v = e.target.value
    setDraft(v)
    if (HEX_RE.test(v)) {
      onChange(v)
    }
  }

  function handleTextBlur() {
    if (isDraftInvalid) {
      // Revert to last good value on blur.
      setDraft(value)
    }
  }

  function handleTextKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      (e.target as HTMLInputElement).blur()
    }
  }

  function handleNativeChange(e: React.ChangeEvent<HTMLInputElement>) {
    const v = e.target.value
    setDraft(v)
    onChange(v)
  }

  return (
    <div className="flex items-center gap-2">
      {/* Color swatch — clicking opens the hidden native picker */}
      <button
        type="button"
        aria-label="Open color picker"
        title="Click to open color picker"
        onClick={() => nativeRef.current?.click()}
        className="w-7 h-7 flex-shrink-0 rounded border border-border cursor-pointer
                   transition-transform hover:scale-110 focus:outline-none focus-visible:ring-2
                   focus-visible:ring-primary"
        style={{ background: swatchColor }}
      />
      {/* Hidden native color input — fallback for picking */}
      <input
        ref={nativeRef}
        type="color"
        tabIndex={-1}
        aria-hidden="true"
        value={HEX_RE.test(value) ? value : '#bd93f9'}
        onChange={handleNativeChange}
        className="sr-only"
      />
      {/* Hex text input */}
      <input
        type="text"
        value={draft}
        onChange={handleTextChange}
        onBlur={handleTextBlur}
        onKeyDown={handleTextKeyDown}
        placeholder="theme default"
        maxLength={7}
        spellCheck={false}
        aria-label="Accent color hex value"
        className={cn(
          'w-28 py-1.5 px-2 text-sm font-mono bg-muted',
          'border rounded focus:outline-none transition-colors',
          'placeholder:text-muted-foreground placeholder:italic',
          isDraftInvalid
            ? 'border-destructive text-destructive'
            : 'border-border text-foreground focus:border-primary',
        )}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Notification sounds section
// ---------------------------------------------------------------------------

const SOUND_LABELS: Record<string, string> = {
  sent: 'Message Sent',
  received: 'Message Received',
}
const SOUND_DEFAULT_VOLUMES: Record<string, number> = { sent: 0.4, received: 0.5 }

function NotificationSoundsSection() {
  const queryClient = useQueryClient()
  const [uploading, setUploading] = useState<Record<string, boolean>>({})
  const [msg, setMsg] = useState<Record<string, string>>({})

  const { data, isLoading } = useQuery<SoundsConfig>({
    queryKey: ['sounds-config'],
    queryFn: () =>
      fetch('/api/ui/sounds/config', { credentials: 'same-origin' }).then((r) => r.json()),
    staleTime: 30_000,
  })

  const sentMode: SoundMode = data?.sent ?? 'default'
  const receivedMode: SoundMode = data?.received ?? 'default'

  function modeFor(type: 'sent' | 'received'): SoundMode {
    return type === 'sent' ? sentMode : receivedMode
  }

  function flashMsg(type: string, text: string) {
    setMsg((prev) => ({ ...prev, [type]: text }))
    setTimeout(() => setMsg((prev) => ({ ...prev, [type]: '' })), 2000)
  }

  async function setMode(type: 'sent' | 'received', mode: SoundMode) {
    const body: Partial<SoundsConfig> = { [type]: mode }
    await fetch('/api/ui/sounds/config', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    queryClient.invalidateQueries({ queryKey: ['sounds-config'] })
    const newCfg: SoundsConfig = {
      sent: type === 'sent' ? mode : sentMode,
      received: type === 'received' ? mode : receivedMode,
    }
    configureSounds(newCfg)
  }

  async function uploadSound(type: 'sent' | 'received', file: File) {
    setUploading((prev) => ({ ...prev, [type]: true }))
    try {
      const fd = new FormData()
      fd.append('sound_type', type)
      fd.append('file', file)
      const r = await fetch('/api/ui/sounds/upload', {
        method: 'POST', body: fd, credentials: 'same-origin',
      })
      if (!r.ok) {
        const err = await r.json().catch(() => ({}))
        toast.error(String((err as { detail?: string }).detail ?? 'Upload failed'))
        return
      }
      queryClient.invalidateQueries({ queryKey: ['sounds-config'] })
      const newCfg: SoundsConfig = {
        sent: type === 'sent' ? 'custom' : sentMode,
        received: type === 'received' ? 'custom' : receivedMode,
      }
      configureSounds(newCfg)
      flashMsg(type, 'Uploaded')
    } finally {
      setUploading((prev) => ({ ...prev, [type]: false }))
    }
  }

  async function resetSound(type: 'sent' | 'received') {
    await fetch(`/api/ui/sounds/custom-${type}`, {
      method: 'DELETE', credentials: 'same-origin',
    })
    queryClient.invalidateQueries({ queryKey: ['sounds-config'] })
    const newCfg: SoundsConfig = {
      sent: type === 'sent' ? 'default' : sentMode,
      received: type === 'received' ? 'default' : receivedMode,
    }
    configureSounds(newCfg)
    flashMsg(type, 'Reset')
  }

  function previewSound(type: 'sent' | 'received') {
    const mode = modeFor(type)
    if (mode === 'none') return
    const url = mode === 'custom' ? `/api/ui/sounds/custom-${type}` : `/static/sounds/${type}.wav`
    const audio = new Audio(url)
    audio.volume = SOUND_DEFAULT_VOLUMES[type]
    audio.play().catch(() => {/* autoplay blocked */})
  }

  if (isLoading) return <p className="text-xs text-muted-foreground">Loading…</p>

  return (
    <div className="space-y-5">
      {(['sent', 'received'] as const).map((type) => {
        const mode = modeFor(type)
        const label = SOUND_LABELS[type]
        return (
          <div key={type} className="space-y-2">
            <p className="text-xs font-medium text-foreground">{label}</p>

            {/* Mode radio group */}
            <div className="flex flex-wrap gap-4">
              {(['default', 'none', 'custom'] as const).map((m) => (
                <label key={m} className="flex items-center gap-1.5 text-xs cursor-pointer select-none">
                  <input
                    type="radio"
                    name={`sound-mode-${type}`}
                    checked={mode === m}
                    onChange={() => {
                      if (m === 'custom') return  // custom is set via upload
                      setMode(type, m)
                    }}
                    disabled={m === 'custom'}
                  />
                  {m === 'default' ? 'Default' : m === 'none' ? 'None' : 'Custom'}
                </label>
              ))}
            </div>

            {/* Action buttons */}
            <div className="flex gap-2 items-center flex-wrap">
              <Button
                size="sm"
                variant="outline"
                type="button"
                onClick={() => previewSound(type)}
                disabled={mode === 'none'}
              >
                ▶ Preview
              </Button>

              {/* Upload button — wraps a hidden file input */}
              <label className="cursor-pointer">
                <Button
                  size="sm"
                  variant="outline"
                  type="button"
                  disabled={uploading[type]}
                  asChild
                >
                  <span>{uploading[type] ? 'Uploading…' : 'Upload…'}</span>
                </Button>
                <input
                  type="file"
                  accept="audio/wav,audio/mpeg,audio/ogg,audio/mp4,audio/aac,.wav,.mp3,.ogg,.m4a,.aac"
                  className="sr-only"
                  onChange={(e) => {
                    const f = e.target.files?.[0]
                    if (f) uploadSound(type, f)
                    e.target.value = ''
                  }}
                />
              </label>

              {mode === 'custom' && (
                <Button
                  size="sm"
                  variant="outline"
                  type="button"
                  onClick={() => resetSound(type)}
                >
                  Reset to default
                </Button>
              )}

              {msg[type] && <span className="text-xs text-success">{msg[type]}</span>}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------

function CustomCssSection() {
  const { customCss, setCustomCss, activeScheme, allSchemes } = useTheme()
  const [draft, setDraft] = useState(customCss)
  const [saved, setSaved] = useState(false)

  // Keep draft in sync when switching themes or if another tab changes the value.
  useEffect(() => {
    setDraft(customCss)
  }, [customCss])

  async function handleSave() {
    await setCustomCss(draft)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const schemeLabel =
    allSchemes.find((s) => s.name === activeScheme)?.label ?? activeScheme

  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">
        CSS scoped automatically to the active theme (
        <strong>{schemeLabel}</strong>). Switch themes to edit CSS for a
        different theme. Write selectors as if scoping is already applied —
        e.g.{' '}
        <code className="bg-muted px-1 rounded">.my-widget &#123; &#125;</code>{' '}
        applies only when <strong>{schemeLabel}</strong> is active.
      </p>
      <Textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder={`.my-widget {\n  color: hsl(var(--primary));\n}`}
        rows={6}
        className="font-mono text-xs resize-y"
        spellCheck={false}
      />
      <div className="flex items-center gap-2">
        <Button type="button" size="sm" onClick={handleSave}>
          Save
        </Button>
        {draft !== '' && (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => { setDraft(''); setCustomCss('') }}
            className="text-destructive border-destructive hover:bg-muted"
          >
            Clear
          </Button>
        )}
        <SaveOk visible={saved} />
      </div>
    </div>
  )
}

function ThemeSection() {
  const { themeMode, setThemeMode, setAccentColor, allSchemes, autoDark, setAutoDark, setAutoLight } = useTheme()

  const isDayNight = themeMode === 'auto'
  const darkSchemes = allSchemes.filter((s) => !s.isLight)
  const lightSchemes = allSchemes.filter((s) => s.isLight)
  const currentScheme = document.documentElement.getAttribute('data-theme') || autoDark

  function handleMainSchemeChange(name: string) {
    const scheme = allSchemes.find((s) => s.name === name)
    if (!scheme) return
    setAccentColor('')
    applyThemeOverride('')
    if (scheme.isLight) {
      setAutoLight(name)
      if (!isDayNight) setThemeMode('light')
    } else {
      setAutoDark(name)
      if (!isDayNight) setThemeMode('dark')
    }
  }

  function toggleDayNight(checked: boolean) {
    if (checked) {
      setThemeMode('auto')
    } else {
      const scheme = allSchemes.find((s) => s.name === currentScheme)
      setThemeMode(scheme?.isLight ? 'light' : 'dark')
    }
  }

  return (
    <div className="space-y-4">
      {/* Main theme picker — all schemes */}
      <div>
        <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
          Theme
        </label>
        <select
          value={currentScheme}
          onChange={(e) => handleMainSchemeChange(e.target.value)}
          className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
        >
          <optgroup label="Dark">
            {darkSchemes.map((s) => (
              <option key={s.name} value={s.name}>{s.label}</option>
            ))}
          </optgroup>
          <optgroup label="Light">
            {lightSchemes.map((s) => (
              <option key={s.name} value={s.name}>{s.label}</option>
            ))}
          </optgroup>
        </select>
      </div>

      {/* Day / Night toggle */}
      <label className="flex items-center gap-2 cursor-pointer select-none">
        <input
          type="checkbox"
          checked={isDayNight}
          onChange={(e) => toggleDayNight(e.target.checked)}
          className="rounded border-border"
        />
        <span className="text-sm text-foreground">Day / Night</span>
        <span className="text-xs text-muted-foreground">
          (auto-switch with OS dark mode)
        </span>
      </label>

      {/* Night scheme picker — only when day/night is on */}
      {isDayNight && (
        <div className="p-3 border border-border rounded-lg bg-muted/30">
          <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">
            Night scheme
          </label>
          <select
            value={autoDark}
            onChange={(e) => { setAutoDark(e.target.value); setAccentColor(''); applyThemeOverride('') }}
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
          >
            {darkSchemes.map((s) => (
              <option key={s.name} value={s.name}>{s.label}</option>
            ))}
          </select>
          <p className="text-xs text-muted-foreground mt-1.5">
            The main theme is used during the day. This one activates when your OS switches to dark mode.
          </p>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Decoration slots editor
// ---------------------------------------------------------------------------

// DecorationDropdown removed — decorations are theme-pack controlled only.

// ---------------------------------------------------------------------------
// Color variable editor
// ---------------------------------------------------------------------------

type ColorVarDef = { key: string; label: string; group: string }

const COLOR_VAR_DEFS: ColorVarDef[] = [
  { key: 'background',          label: 'Background',       group: 'Core' },
  { key: 'foreground',          label: 'Text',             group: 'Core' },
  { key: 'primary',             label: 'Primary/Accent',   group: 'Core' },
  { key: 'primary-foreground',  label: 'Primary text',     group: 'Core' },
  { key: 'secondary',           label: 'Secondary',        group: 'Core' },
  { key: 'secondary-foreground',label: 'Secondary text',   group: 'Core' },
  { key: 'muted',               label: 'Muted surface',    group: 'Core' },
  { key: 'muted-foreground',    label: 'Muted text',       group: 'Core' },
  { key: 'card',                label: 'Card',             group: 'Surfaces' },
  { key: 'card-foreground',     label: 'Card text',        group: 'Surfaces' },
  { key: 'accent',              label: 'Accent surface',   group: 'Surfaces' },
  { key: 'border',              label: 'Border',           group: 'Surfaces' },
  { key: 'input',               label: 'Input bg',         group: 'Surfaces' },
  { key: 'destructive',         label: 'Destructive',      group: 'Semantic' },
  { key: 'success',             label: 'Success',          group: 'Semantic' },
  { key: 'warning',             label: 'Warning',          group: 'Semantic' },
  { key: 'info',                label: 'Info',             group: 'Semantic' },
  { key: 'msg-me',              label: 'My bubble',        group: 'Chat' },
  { key: 'msg-them',            label: 'Their bubble',     group: 'Chat' },
  { key: 'msg-sms',             label: 'SMS accent',       group: 'Chat' },
]

/** Convert "H S% L%" HSL string to #rrggbb hex. */
function _hslStrToHex(hsl: string): string {
  const parts = hsl.trim().split(/\s+/)
  if (parts.length < 3) return '#808080'
  const h = parseFloat(parts[0]) / 360
  const s = parseFloat(parts[1]) / 100
  const l = parseFloat(parts[2]) / 100
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s
  const p = 2 * l - q
  const toC = (t: number) => {
    const n = t < 0 ? t + 1 : t > 1 ? t - 1 : t
    if (n < 1 / 6) return p + (q - p) * 6 * n
    if (n < 1 / 2) return q
    if (n < 2 / 3) return p + (q - p) * (2 / 3 - n) * 6
    return p
  }
  const r = Math.round(toC(h + 1 / 3) * 255)
  const g = Math.round(toC(h) * 255)
  const b = Math.round(toC(h - 1 / 3) * 255)
  return '#' + [r, g, b].map((n) => n.toString(16).padStart(2, '0')).join('')
}

/** Convert #rrggbb hex to "H S% L%" HSL string. */
function _hexToHslStr(hex: string): string {
  const h2 = hex.replace('#', '')
  if (h2.length !== 6) return '0 0% 50%'
  const r = parseInt(h2.slice(0, 2), 16) / 255
  const g = parseInt(h2.slice(2, 4), 16) / 255
  const b = parseInt(h2.slice(4, 6), 16) / 255
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

/** Convert #rrggbb hex to WCAG relative luminance. */
function _hexToLuminance(hex: string): number {
  const h2 = hex.replace('#', '')
  if (h2.length !== 6) return 0
  const toLinear = (c: number) => {
    const v = c / 255
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)
  }
  const r = toLinear(parseInt(h2.slice(0, 2), 16))
  const g = toLinear(parseInt(h2.slice(2, 4), 16))
  const b = toLinear(parseInt(h2.slice(4, 6), 16))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

/** WCAG contrast ratio between two hex colors (range 1–21). */
function _contrastRatio(hex1: string, hex2: string): number {
  const l1 = _hexToLuminance(hex1)
  const l2 = _hexToLuminance(hex2)
  const lighter = Math.max(l1, l2)
  const darker = Math.min(l1, l2)
  return (lighter + 0.05) / (darker + 0.05)
}

/**
 * For each editable color variable, the variable it should be contrasted
 * against for the WCAG badge (typically its semantic background partner).
 */
const CONTRAST_PAIRS: Record<string, string> = {
  'foreground':           'background',
  'primary':              'background',
  'primary-foreground':   'primary',
  'secondary':            'background',
  'secondary-foreground': 'secondary',
  'muted':                'background',
  'muted-foreground':     'muted',
  'card':                 'background',
  'card-foreground':      'card',
  'accent':               'background',
  'border':               'background',
  'input':                'background',
  'destructive':          'background',
  'success':              'background',
  'warning':              'background',
  'info':                 'background',
  'msg-me':               'background',
  'msg-them':             'background',
  'msg-sms':              'background',
}

/** Small WCAG AA / AAA compliance pill. */
function ContrastBadge({ ratio }: { ratio: number }) {
  let label: string
  let cls: string
  if (ratio >= 7) {
    label = 'AAA'; cls = 'text-success'
  } else if (ratio >= 4.5) {
    label = 'AA'; cls = 'text-primary'
  } else if (ratio >= 3) {
    label = 'AA⁺'; cls = 'text-warning'
  } else {
    label = '✗'; cls = 'text-destructive'
  }
  return (
    <span
      className={cn('text-[9px] font-bold shrink-0 w-7 text-right', cls)}
      title={`Contrast ratio ${ratio.toFixed(1)}:1 (paired background)`}
    >
      {label}
    </span>
  )
}

function ColorEditorSection() {
  const [theme, setTheme] = useState<string>('')
  const [overrides, setOverrides] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const importRef = useRef<HTMLInputElement>(null)
  const importZipRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    function loadForScheme() {
      const slug = document.documentElement.getAttribute('data-theme') || 'dracula'
      setTheme(slug)
      fetch(`/api/ui/theme-override?theme=${encodeURIComponent(slug)}`, { credentials: 'same-origin' })
        .then((r) => r.json())
        .then((data: { theme: string; colors: Record<string, string> }) => {
          setOverrides(data.colors || {})
        })
        .catch(() => {})
    }
    loadForScheme()
    // Re-load when user switches color scheme
    const observer = new MutationObserver((mutations) => {
      for (const m of mutations) {
        if (m.attributeName === 'data-theme') loadForScheme()
      }
    })
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => observer.disconnect()
  }, [])

  async function handleChange(key: string, hex: string) {
    const hsl = _hexToHslStr(hex)
    const next = { ...overrides, [key]: hsl }
    setOverrides(next)
    document.documentElement.style.setProperty(`--${key}`, hsl)
    setSaving(true)
    try {
      await fetch('/api/ui/theme-override', {
        method: 'PATCH',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theme, colors: { [key]: hsl } }),
      })
      const r = await fetch('/api/ui/theme-override/css', { credentials: 'same-origin' })
      if (r.ok) {
        const data = (await r.json()) as { css: string }
        applyThemeOverride(data.css)
      }
    } catch {
      // best-effort
    } finally {
      setSaving(false)
    }
  }

  async function resetOverrides() {
    if (!theme) return
    try {
      await fetch(`/api/ui/theme-override?theme=${encodeURIComponent(theme)}`, {
        method: 'DELETE',
        credentials: 'same-origin',
      })
    } catch {
      // best-effort
    }
    setOverrides({})
    for (const { key } of COLOR_VAR_DEFS) {
      document.documentElement.style.removeProperty(`--${key}`)
    }
    applyThemeOverride('')
    toast.success('Theme overrides cleared')
  }

  function exportJson() {
    const blob = new Blob(
      [JSON.stringify({ theme, colors: overrides }, null, 2)],
      { type: 'application/json' },
    )
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `chatwire-override-${theme}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  async function handleImportJson(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const text = await file.text()
      const data = JSON.parse(text) as { theme?: string; colors?: Record<string, string> }
      const colors = data.colors
      if (!colors || typeof colors !== 'object') {
        toast.error('Invalid format: missing "colors" field')
        return
      }
      // Apply overrides locally
      const next = { ...overrides }
      for (const [k, v] of Object.entries(colors)) {
        if (typeof v === 'string' && v.trim()) {
          next[k] = v
          document.documentElement.style.setProperty(`--${k}`, v)
        }
      }
      setOverrides(next)
      // Persist to server
      await fetch('/api/ui/theme-override', {
        method: 'PATCH',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theme, colors }),
      })
      const r = await fetch('/api/ui/theme-override/css', { credentials: 'same-origin' })
      if (r.ok) {
        const cssData = (await r.json()) as { css: string }
        applyThemeOverride(cssData.css)
      }
      toast.success(`Imported ${Object.keys(colors).length} color overrides`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Import failed')
    } finally {
      if (importRef.current) importRef.current.value = ''
    }
  }

  function exportSkin() {
    if (!theme) return
    const a = document.createElement('a')
    a.href = `/api/ui/theme-skin/download?theme=${encodeURIComponent(theme)}`
    a.download = `chatwire-override-${theme}.zip`
    a.click()
  }

  async function handleImportZip(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const form = new FormData()
      form.append('file', file)
      const r = await fetch('/api/ui/theme-skin/upload', {
        method: 'POST',
        credentials: 'same-origin',
        body: form,
      })
      if (!r.ok) {
        const err = (await r.json().catch(() => ({ detail: 'Upload failed' }))) as { detail?: string }
        toast.error(err.detail ?? 'Upload failed')
        return
      }
      const data = (await r.json()) as { theme: string; colors_imported: number }
      // If the skin is for the active theme, reload overrides immediately
      if (data.theme === theme) {
        const r2 = await fetch(`/api/ui/theme-override?theme=${encodeURIComponent(theme)}`, {
          credentials: 'same-origin',
        })
        if (r2.ok) {
          const d2 = (await r2.json()) as { theme: string; colors: Record<string, string> }
          setOverrides(d2.colors || {})
          for (const [k, v] of Object.entries(d2.colors || {})) {
            document.documentElement.style.setProperty(`--${k}`, v)
          }
        }
        const r3 = await fetch('/api/ui/theme-override/css', { credentials: 'same-origin' })
        if (r3.ok) {
          const cssData = (await r3.json()) as { css: string }
          applyThemeOverride(cssData.css)
        }
      }
      toast.success(`Imported skin for "${data.theme}" (${data.colors_imported} colors)`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Import failed')
    } finally {
      if (importZipRef.current) importZipRef.current.value = ''
    }
  }

  const groups = Array.from(new Set(COLOR_VAR_DEFS.map((v) => v.group)))

  return (
    <div className="space-y-4">
      {theme && (
        <p className="text-xs text-muted-foreground">
          Editing:{' '}
          <span className="font-mono text-foreground">{theme}</span>
          {saving && <span className="ml-2 italic">Saving…</span>}
        </p>
      )}
      {groups.map((group) => (
        <div key={group}>
          <p className="text-xs font-semibold text-muted-foreground mb-2">{group}</p>
          <div className="grid grid-cols-1 gap-y-0.5">
            {COLOR_VAR_DEFS.filter((v) => v.group === group).map(({ key, label }) => {
              const currentHsl =
                overrides[key] ||
                getComputedStyle(document.documentElement).getPropertyValue(`--${key}`).trim()
              const hex = _hslStrToHex(currentHsl)
              const isOverridden = !!overrides[key]
              const pairKey = CONTRAST_PAIRS[key]
              let ratio = 0
              if (pairKey) {
                const pairHsl =
                  overrides[pairKey] ||
                  getComputedStyle(document.documentElement).getPropertyValue(`--${pairKey}`).trim()
                ratio = _contrastRatio(hex, _hslStrToHex(pairHsl))
              }
              return (
                <div key={key} className="flex items-center gap-2 py-0.5">
                  <input
                    type="color"
                    value={hex}
                    onChange={(e) => handleChange(key, e.target.value)}
                    className="w-6 h-6 rounded cursor-pointer border border-border bg-transparent p-0 shrink-0"
                    title={`--${key}: ${currentHsl}`}
                  />
                  <span
                    className={cn(
                      'text-xs flex-1 truncate min-w-0',
                      isOverridden ? 'text-foreground font-medium' : 'text-muted-foreground',
                    )}
                  >
                    {label}
                    {isOverridden && <span className="ml-1 text-primary">•</span>}
                  </span>
                  <span className="text-[10px] font-mono text-muted-foreground/60 shrink-0 tabular-nums">
                    {hex}
                  </span>
                  {pairKey && <ContrastBadge ratio={ratio} />}
                </div>
              )
            })}
          </div>
        </div>
      ))}
      <div className="flex gap-3 pt-1 flex-wrap">
        <button
          type="button"
          onClick={exportJson}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          Export JSON
        </button>
        <button
          type="button"
          onClick={() => importRef.current?.click()}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          Import JSON
        </button>
        <button
          type="button"
          onClick={exportSkin}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          Export Skin (.zip)
        </button>
        <button
          type="button"
          onClick={() => importZipRef.current?.click()}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          Import Skin (.zip)
        </button>
        <button
          type="button"
          onClick={resetOverrides}
          className="text-xs text-muted-foreground hover:text-destructive transition-colors"
        >
          Reset to defaults
        </button>
        <input
          ref={importRef}
          type="file"
          accept=".json"
          className="hidden"
          onChange={handleImportJson}
          aria-label="Import color overrides JSON"
        />
        <input
          ref={importZipRef}
          type="file"
          accept=".zip"
          className="hidden"
          onChange={handleImportZip}
          aria-label="Import color overrides skin ZIP"
        />
      </div>
    </div>
  )
}

// DecorationsSection removed — decorations are theme-pack controlled only.
// Users edit colors; structural properties come from the theme.

// ---------------------------------------------------------------------------
// Theme pack selector
// ---------------------------------------------------------------------------

interface ThemePackMeta {
  name: string
  author: string
  version: string
  scheme_dark?: string | null
  scheme_light?: string | null
  has_colors: boolean
  has_structure: boolean
  has_decorations: boolean
  has_custom_css: boolean
  custom_css_sanitized: boolean
}

function ThemePackSection() {
  const { data, isLoading } = useQuery<{ packages: ThemePackMeta[] }>({
    queryKey: ['theme-packages'],
    queryFn: () =>
      fetch('/api/ui/theme-packages', { credentials: 'same-origin' }).then((r) => r.json()),
    staleTime: 60_000,
  })
  const [active, setActive] = useState<string>(
    () => localStorage.getItem('chatwire-theme-pack') ?? '',
  )
  const [applying, setApplying] = useState(false)
  const { themeMode, setThemeMode, setAutoDark, setAutoLight } = useTheme()

  const packages = data?.packages ?? []

  if (isLoading) return <p className="text-xs text-muted-foreground">Loading theme packs…</p>
  if (packages.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        No theme packs installed. Drop a <code className="bg-muted px-1 rounded">.json</code> file
        into <code className="bg-muted px-1 rounded">~/.chatwire/themes/</code> to add one.
      </p>
    )
  }

  async function applyPack(name: string) {
    if (applying) return
    if (!name) {
      // Clear active pack
      applyThemePackCss('', '')
      localStorage.removeItem('chatwire-theme-pack')
      setActive('')
      return
    }
    setApplying(true)
    try {
      const fd = new FormData()
      fd.append('name', name)
      const r = await fetch('/api/ui/theme-packages/apply', {
        method: 'POST',
        body: fd,
        credentials: 'same-origin',
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const result = (await r.json()) as {
        name: string
        css: string
        scheme_dark?: string | null
        scheme_light?: string | null
      }
      applyThemePackCss(result.name, result.css)
      localStorage.setItem('chatwire-theme-pack', result.name)
      setActive(result.name)

      // --- Theme import preference cascade ---
      // Determine which scheme(s) the pack prefers and apply cascade rules.
      const hasDark = !!result.scheme_dark
      const hasLight = !!result.scheme_light
      const schemesToClear: string[] = []

      if (hasDark && hasLight) {
        // Pack ships both schemes: update both, respect user's current mode.
        setAutoDark(result.scheme_dark!)
        setAutoLight(result.scheme_light!)
        schemesToClear.push(result.scheme_dark!, result.scheme_light!)
      } else if (hasDark && !hasLight) {
        // Dark-only pack: switch to dark mode.
        setAutoDark(result.scheme_dark!)
        if (themeMode !== 'dark') await setThemeMode('dark')
        schemesToClear.push(result.scheme_dark!)
      } else if (!hasDark && hasLight) {
        // Light-only pack: switch to light mode.
        setAutoLight(result.scheme_light!)
        if (themeMode !== 'light') await setThemeMode('light')
        schemesToClear.push(result.scheme_light!)
      }
      // else: no scheme info → keep user's current scheme untouched.

      // Clear per-scheme color overrides for affected schemes so the pack's
      // colors are not masked by the user's previously-saved tweaks.
      for (const slug of schemesToClear) {
        await fetch(`/api/ui/theme-override?theme=${encodeURIComponent(slug)}`, {
          method: 'DELETE',
          credentials: 'same-origin',
        }).catch(() => {/* best-effort */})
      }
      // Re-inject the remaining override CSS (other themes still have their overrides).
      if (schemesToClear.length > 0) {
        await restoreThemeOverride().catch(() => {/* best-effort */})
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to apply theme pack')
    } finally {
      setApplying(false)
    }
  }

  const activePack = packages.find((p) => p.name === active)

  return (
    <div className="space-y-2">
      <select
        value={active}
        onChange={(e) => applyPack(e.target.value)}
        disabled={applying}
        className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
        aria-label="Theme pack"
      >
        <option value="">— none —</option>
        {packages.map((p) => (
          <option key={p.name} value={p.name}>
            {p.name}{p.author ? ` by ${p.author}` : ''}{p.version ? ` v${p.version}` : ''}
          </option>
        ))}
      </select>
      {activePack?.has_custom_css && (
        <p className="text-xs text-warning">
          ⚠ This theme includes custom CSS.
          {activePack.custom_css_sanitized && ' Some external references were sanitized.'}
        </p>
      )}
      <p className="text-xs text-muted-foreground">
        Applies all variables from the selected pack. Individual overrides below still take precedence.
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Theme export / import / save-as-new
// ---------------------------------------------------------------------------

/** Collect all active CSS variable values for a given set of var names. */
function collectVarValues(names: string[]): Record<string, string> {
  const style = getComputedStyle(document.documentElement)
  const result: Record<string, string> = {}
  for (const name of names) {
    const val = style.getPropertyValue(`--${name}`).trim()
    if (val) result[name] = val
  }
  return result
}

const COLOR_VARS = [
  'background', 'foreground', 'card', 'card-foreground', 'primary', 'primary-foreground',
  'secondary', 'secondary-foreground', 'muted', 'muted-foreground', 'accent', 'accent-foreground',
  'destructive', 'destructive-foreground', 'border', 'input', 'ring', 'sidebar-bg',
  'msg-me', 'msg-me-text', 'msg-them', 'msg-them-text', 'msg-sms', 'msg-sms-text',
]
const STRUCTURE_VARS = [
  'radius', 'radius-bubble', 'radius-input', 'spacing-message', 'spacing-sidebar',
  'font-size-message', 'font-size-sidebar', 'shadow-card', 'sidebar-width',
]
const DECORATION_VARS = [
  'avatar-shape', 'avatar-size', 'avatar-border', 'bubble-shadow', 'bubble-tail',
  'header-shadow', 'header-border', 'sidebar-divider', 'border-width', 'transition-speed',
]

interface ThemePackPayload {
  name: string
  author: string
  version: string
  colors: Record<string, string>
  structure: Record<string, string>
  decorations: Record<string, string>
  custom_css: string
  scheme_dark?: string
  scheme_light?: string
}

function ThemeExportSection() {
  const qc = useQueryClient()
  const importRef = useRef<HTMLInputElement>(null)
  const [saving, setSaving] = useState(false)
  const [namePrompt, setNamePrompt] = useState(false)
  const [newName, setNewName] = useState('')
  const [newAuthor, setNewAuthor] = useState('')
  const { autoDark, autoLight } = useTheme()

  function buildCurrentPackage(name: string, author: string): ThemePackPayload {
    return {
      name,
      author,
      version: '1.0.0',
      colors: collectVarValues(COLOR_VARS),
      structure: collectVarValues(STRUCTURE_VARS),
      decorations: collectVarValues(DECORATION_VARS),
      custom_css: localStorage.getItem('chatwire-custom-css') ?? '',
      scheme_dark: autoDark,
      scheme_light: autoLight,
    }
  }

  function handleExport() {
    const pkg = buildCurrentPackage('my-theme', '')
    const blob = new Blob([JSON.stringify(pkg, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `chatwire-theme-${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const text = await file.text()
      const data = JSON.parse(text) as ThemePackPayload
      if (!data.name || typeof data.name !== 'string') {
        toast.error('Invalid theme pack: missing name')
        return
      }
      await savePackage(data)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to import theme pack')
    } finally {
      if (importRef.current) importRef.current.value = ''
    }
  }

  async function savePackage(pkg: ThemePackPayload) {
    setSaving(true)
    try {
      const r = await fetch('/api/ui/theme-packages/save', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(pkg),
      })
      if (!r.ok) {
        const detail = await r.text()
        throw new Error(detail || `HTTP ${r.status}`)
      }
      const result = (await r.json()) as { name: string }
      toast.success(`Theme pack "${result.name}" saved`)
      qc.invalidateQueries({ queryKey: ['theme-packages'] })
    } finally {
      setSaving(false)
    }
  }

  async function handleSaveAsNew(e: React.FormEvent) {
    e.preventDefault()
    if (!newName.trim()) return
    const pkg = buildCurrentPackage(newName.trim(), newAuthor.trim())
    await savePackage(pkg)
    setNamePrompt(false)
    setNewName('')
    setNewAuthor('')
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-2 flex-wrap">
        <Button type="button" variant="outline" size="sm" onClick={handleExport}>
          Export current theme
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => importRef.current?.click()}
          disabled={saving}
        >
          Import .json
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setNamePrompt(true)}
          disabled={saving}
        >
          Save as new theme pack
        </Button>
        <input
          ref={importRef}
          type="file"
          accept=".json"
          className="hidden"
          onChange={handleImport}
          aria-label="Import theme pack file"
        />
      </div>
      <p className="text-xs text-muted-foreground">
        Export collects all active CSS variables. Import/Save writes to{' '}
        <code className="bg-muted px-1 rounded">~/.chatwire/themes/</code>.
      </p>

      {namePrompt && (
        <form onSubmit={handleSaveAsNew} className="space-y-2 pt-2 border-t border-border">
          <p className="text-xs font-medium text-foreground">Save current state as a theme pack</p>
          <div className="flex gap-2">
            <Input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="pack-name (kebab-case)"
              pattern="[a-z0-9][a-z0-9\-]*"
              required
              className="flex-1 h-8 text-sm"
            />
            <Input
              type="text"
              value={newAuthor}
              onChange={(e) => setNewAuthor(e.target.value)}
              placeholder="Author (optional)"
              className="flex-1 h-8 text-sm"
            />
          </div>
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={saving || !newName.trim()}>
              {saving ? 'Saving…' : 'Save'}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => { setNamePrompt(false); setNewName(''); setNewAuthor('') }}
            >
              Cancel
            </Button>
          </div>
        </form>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Style (structural theme) section
// ---------------------------------------------------------------------------

function StyleSection() {
  const { currentStyle, setStyle, allStyles } = useTheme()

  return (
    <select
      value={currentStyle}
      onChange={(e) => setStyle(e.target.value)}
      className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
      aria-label="Structural style"
    >
      {allStyles.map((s) => (
        <option key={s.name} value={s.name}>{s.label} — {s.description}</option>
      ))}
    </select>
  )
}

// ---------------------------------------------------------------------------
// Whitelist section
// ---------------------------------------------------------------------------

interface WlContact {
  name: string
  all_handles: string[]
  whitelisted_handles: string[]
  whitelisted: boolean
}
interface WlGroup {
  guid: string
  name: string
  members: number
  whitelisted: boolean
}
interface WlGroupedData {
  contacts: WlContact[]
  unknown: string[]
  groups: WlGroup[]
}
interface WlFlatData {
  rows: { label: string; value: string }[]
  contact_names: string[]
}

function ContactCard({ contact, onAddHandle, onRemoveHandle }: {
  contact: WlContact
  onAddHandle: (h: string) => void
  onRemoveHandle: (h: string) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const initials = contact.name.split(' ').map((w) => w[0]).join('').toUpperCase().slice(0, 2)
  const allWl = contact.all_handles.every((h) => contact.whitelisted_handles.includes(h))

  return (
    <div className="border border-border rounded-md p-2 space-y-1">
      <div className="flex items-center gap-2">
        {/* avatar */}
        <div className="w-8 h-8 rounded-full bg-primary/20 text-primary flex items-center justify-center
                        text-xs font-semibold shrink-0 select-none">
          {initials || '?'}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium leading-tight truncate">{contact.name}</p>
          <p className="text-xs text-muted-foreground">
            {contact.whitelisted_handles.length}/{contact.all_handles.length} handle
            {contact.all_handles.length !== 1 ? 's' : ''} allowed
          </p>
        </div>
        {/* add-all / remove-all */}
        {allWl ? (
          <Button type="button" variant="ghost" size="sm"
            className="text-destructive hover:text-destructive text-xs h-auto py-0.5 px-2 shrink-0"
            onClick={() => contact.all_handles.forEach((h) => onRemoveHandle(h))}>
            Remove all
          </Button>
        ) : (
          <Button type="button" variant="ghost" size="sm"
            className="text-primary hover:text-primary text-xs h-auto py-0.5 px-2 shrink-0"
            onClick={() => contact.all_handles.forEach((h) => onAddHandle(h))}>
            Add all
          </Button>
        )}
        {/* expand toggle */}
        <button type="button"
          className="text-muted-foreground hover:text-foreground text-xs px-1"
          onClick={() => setExpanded((v) => !v)}
          aria-label={expanded ? 'Collapse' : 'Expand'}>
          {expanded ? '▲' : '▼'}
        </button>
      </div>
      {expanded && (
        <ul className="pl-10 space-y-0.5">
          {contact.all_handles.map((h) => {
            const wl = contact.whitelisted_handles.includes(h)
            return (
              <li key={h} className="flex items-center gap-2 text-xs">
                <span className={cn('font-mono flex-1 truncate', wl ? 'text-foreground' : 'text-muted-foreground')}>
                  {h}
                </span>
                {wl ? (
                  <Button type="button" variant="ghost" size="sm"
                    className="text-destructive hover:text-destructive h-auto py-0 px-1"
                    onClick={() => onRemoveHandle(h)}>
                    ✕
                  </Button>
                ) : (
                  <Button type="button" variant="ghost" size="sm"
                    className="text-primary hover:text-primary h-auto py-0 px-1"
                    onClick={() => onAddHandle(h)}>
                    +
                  </Button>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

function WhitelistSection() {
  const qc = useQueryClient()

  const { data: grouped } = useQuery<WlGroupedData>({
    queryKey: ['settings-whitelist-grouped'],
    queryFn: () =>
      fetch('/api/ui/settings/whitelist/grouped', { credentials: 'same-origin' }).then((r) => r.json()),
    staleTime: 30_000,
  })
  const { data: flat } = useQuery<WlFlatData>({
    queryKey: ['settings-whitelist'],
    queryFn: () =>
      fetch('/api/ui/settings/whitelist', { credentials: 'same-origin' }).then((r) => r.json()),
    staleTime: 30_000,
  })

  const [input, setInput] = useState('')
  const [syncMsg, setSyncMsg] = useState('')
  const [showGroups, setShowGroups] = useState(false)

  function invalidate() {
    qc.invalidateQueries({ queryKey: ['settings-whitelist'] })
    qc.invalidateQueries({ queryKey: ['settings-whitelist-grouped'] })
  }

  async function addHandle(h: string) {
    await fetch(`/api/ui/whitelist?handle=${encodeURIComponent(h)}`, {
      method: 'POST', credentials: 'same-origin',
    })
    invalidate()
  }

  async function removeHandle(h: string) {
    await fetch(`/api/ui/whitelist?handle=${encodeURIComponent(h)}`, {
      method: 'DELETE', credentials: 'same-origin',
    })
    invalidate()
  }

  async function toggleGroup(guid: string, wl: boolean) {
    if (wl) {
      await fetch(`/api/ui/whitelist?guid=${encodeURIComponent(guid)}`, {
        method: 'DELETE', credentials: 'same-origin',
      })
    } else {
      await fetch(`/api/ui/whitelist?guid=${encodeURIComponent(guid)}`, {
        method: 'POST', credentials: 'same-origin',
      })
    }
    invalidate()
  }

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    const v = input.trim()
    if (!v) return
    const fd = new FormData()
    fd.append('input', v)
    const r = await fetch('/whitelist/add', { method: 'POST', body: fd, credentials: 'same-origin' })
    if (r.ok) {
      setInput('')
      invalidate()
    }
  }

  async function handleSync() {
    const r = await fetch('/refresh_contacts', { method: 'POST', credentials: 'same-origin' })
    setSyncMsg(r.ok ? 'Synced' : 'Failed')
    setTimeout(() => setSyncMsg(''), 2000)
    invalidate()
  }

  const contactNames = flat?.contact_names ?? []
  const contacts = grouped?.contacts ?? []
  const unknown = grouped?.unknown ?? []
  const groups = grouped?.groups ?? []
  const totalWl = contacts.length + unknown.length + groups.filter((g) => g.whitelisted).length

  return (
    <div className="space-y-3">
      {/* Add input */}
      <form onSubmit={handleAdd} className="flex gap-2">
        <Input
          list="wl-contact-names"
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="handle, contact, or [Group] name"
          required
          className="flex-1"
        />
        <datalist id="wl-contact-names">
          {contactNames.map((n) => <option key={n} value={n} />)}
        </datalist>
        <Button type="submit" size="sm">Add</Button>
      </form>
      <p className="text-xs text-muted-foreground">
        Phone (<code className="bg-muted px-1 rounded">+15551234567</code>), email, a
        Contacts name, or a named group chat.
      </p>

      {/* Sync + summary */}
      <div className="flex items-center gap-2 flex-wrap">
        <Button type="button" variant="outline" size="sm" onClick={handleSync}>
          ↻ Sync contacts
        </Button>
        {syncMsg && <span className="text-xs text-success">{syncMsg}</span>}
        {totalWl > 0 && (
          <span className="text-xs text-muted-foreground">{totalWl} contact{totalWl !== 1 ? 's' : ''} allowed</span>
        )}
      </div>

      {/* Contact cards */}
      {contacts.length > 0 && (
        <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
          {contacts.map((c) => (
            <ContactCard
              key={c.name}
              contact={c}
              onAddHandle={addHandle}
              onRemoveHandle={removeHandle}
            />
          ))}
        </div>
      )}

      {/* Unknown handles (no contact name) */}
      {unknown.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs text-muted-foreground font-medium">Unknown handles</p>
          <ul className="space-y-0.5">
            {unknown.map((h) => (
              <li key={h} className="flex items-center gap-2 text-xs">
                <span className="font-mono flex-1 truncate text-foreground">{h}</span>
                <Button type="button" variant="ghost" size="sm"
                  className="text-destructive hover:text-destructive h-auto py-0 px-1"
                  onClick={() => removeHandle(h)}>
                  Remove
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Groups (collapsible) */}
      {groups.length > 0 && (
        <div className="space-y-1">
          <button
            type="button"
            className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
            onClick={() => setShowGroups((v) => !v)}
          >
            {showGroups ? '▲' : '▼'} Group chats ({groups.filter((g) => g.whitelisted).length}/{groups.length} allowed)
          </button>
          {showGroups && (
            <ul className="space-y-1 max-h-48 overflow-y-auto">
              {groups.map((g) => (
                <li key={g.guid}
                  className="flex items-center gap-2 text-xs py-1 border-b border-border last:border-0">
                  <span className={cn('flex-1 truncate', g.whitelisted ? 'text-foreground' : 'text-muted-foreground')}>
                    {g.name !== g.guid ? g.name : g.guid}
                    {g.members > 0 && (
                      <span className="text-muted-foreground ml-1">({g.members})</span>
                    )}
                  </span>
                  <Button type="button" variant="ghost" size="sm"
                    className={cn(
                      'h-auto py-0.5 px-2',
                      g.whitelisted
                        ? 'text-destructive hover:text-destructive'
                        : 'text-primary hover:text-primary',
                    )}
                    onClick={() => toggleGroup(g.guid, g.whitelisted)}>
                    {g.whitelisted ? 'Remove' : 'Add'}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Self handles (read-only)
// ---------------------------------------------------------------------------

function SelfHandlesSection() {
  const { data } = useQuery<{ self_handles: string[] }>({
    queryKey: ['settings-self-handles'],
    queryFn: () =>
      fetch('/api/ui/settings/self_handles', { credentials: 'same-origin' }).then((r) => r.json()),
    staleTime: 60_000,
  })
  const handles = data?.self_handles ?? []
  return (
    <div>
      <ul className="space-y-1 text-sm font-mono mb-2">
        {handles.map((h) => (
          <li key={h} className="px-2 py-1 bg-muted rounded text-foreground">
            {h}
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted-foreground">
        Edit <code className="bg-muted px-1 rounded">SELF_HANDLES</code> in{' '}
        <code className="bg-muted px-1 rounded">~/.chatwire/config.json</code> and
        reload the agent to change.
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Scoped API keys section
// ---------------------------------------------------------------------------

const SCOPE_LABELS: Record<string, string> = {
  trigger_actions: 'Trigger actions',
  read_conversations: 'Read conversations',
  send_messages: 'Send messages',
  manage_settings: 'Manage settings',
}
const ALL_SCOPES = Object.keys(SCOPE_LABELS)

interface ApiKeyInfo {
  name: string
  prefix: string
  scopes: string[]
  created_at: string
}

function ApiKeySection() {
  const qc = useQueryClient()
  const [newName, setNewName] = useState('')
  const [newScopes, setNewScopes] = useState<string[]>([...ALL_SCOPES])
  const [revealed, setRevealed] = useState<{ key: string; prefix: string } | null>(null)
  const [adding, setAdding] = useState(false)
  const [editingPrefix, setEditingPrefix] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [editScopes, setEditScopes] = useState<string[]>([])

  const { data } = useQuery<{ keys: ApiKeyInfo[] }>({
    queryKey: ['ui-api-keys'],
    queryFn: () =>
      fetch('/api/ui/api-keys', { credentials: 'same-origin' }).then((r) => r.json()),
    staleTime: 15_000,
  })
  const keys = data?.keys ?? []

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!newName.trim()) return
    const r = await fetch('/api/ui/api-keys', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newName.trim(), scopes: newScopes }),
    })
    if (!r.ok) {
      const d = await r.json()
      toast.error(d.detail ?? 'Failed to create key.')
      return
    }
    const d = await r.json()
    setRevealed({ key: d.key, prefix: d.info.prefix })
    setNewName('')
    setNewScopes([...ALL_SCOPES])
    setAdding(false)
    qc.invalidateQueries({ queryKey: ['ui-api-keys'] })
  }

  async function handleDelete(prefix: string, name: string) {
    if (!confirm(`Delete API key "${name}"? This cannot be undone.`)) return
    const r = await fetch(`/api/ui/api-keys/${prefix}`, {
      method: 'DELETE',
      credentials: 'same-origin',
    })
    if (r.ok) {
      qc.invalidateQueries({ queryKey: ['ui-api-keys'] })
    } else {
      toast.error('Failed to delete key.')
    }
  }

  function startEdit(k: ApiKeyInfo) {
    setEditingPrefix(k.prefix)
    setEditName(k.name)
    setEditScopes([...k.scopes])
  }

  function cancelEdit() {
    setEditingPrefix(null)
    setEditName('')
    setEditScopes([])
  }

  async function handleUpdate(prefix: string) {
    const name = editName.trim()
    if (!name || editScopes.length === 0) return
    const r = await fetch(`/api/ui/api-keys/${prefix}`, {
      method: 'PATCH',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, scopes: editScopes }),
    })
    if (r.ok) {
      cancelEdit()
      qc.invalidateQueries({ queryKey: ['ui-api-keys'] })
      toast.success('Key updated.')
    } else {
      const d = await r.json()
      toast.error(d.detail ?? 'Failed to update key.')
    }
  }

  function toggleScope(scope: string) {
    setNewScopes((prev) =>
      prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope],
    )
  }

  function toggleEditScope(scope: string) {
    setEditScopes((prev) =>
      prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope],
    )
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">
        Named API keys for programmatic access. Authenticate with{' '}
        <code className="bg-muted px-1 rounded">Authorization: Bearer cwk_…</code> on
        API requests. Each key has its own permission scopes.
      </p>

      {/* Revealed-key flash */}
      {revealed && (
        <div className="p-3 rounded-lg border border-primary/40 bg-primary/5 space-y-2">
          <p className="text-xs font-semibold text-primary">
            New key — copy it now. It will not be shown again.
          </p>
          <div className="flex items-center gap-2">
            <Input
              readOnly
              value={revealed.key}
              onClick={(e) => (e.target as HTMLInputElement).select()}
              className="font-mono text-xs cursor-text flex-1"
            />
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => {
                navigator.clipboard.writeText(revealed.key).catch(() => {})
                toast.success('Copied!')
              }}
            >
              Copy
            </Button>
          </div>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => setRevealed(null)}
            className="text-xs"
          >
            Dismiss
          </Button>
        </div>
      )}

      {/* Key table */}
      {keys.length > 0 && (
        <div className="divide-y divide-border border border-border rounded-lg overflow-hidden">
          {keys.map((k) =>
            editingPrefix === k.prefix ? (
              <div key={k.prefix} className="px-4 py-3 space-y-2 bg-muted/30">
                <Input
                  autoFocus
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  placeholder="Key name"
                  className="text-sm h-8"
                />
                <div className="grid grid-cols-2 gap-1">
                  {ALL_SCOPES.map((scope) => (
                    <label key={scope} className="flex items-center gap-2 cursor-pointer text-xs">
                      <input
                        type="checkbox"
                        checked={editScopes.includes(scope)}
                        onChange={() => toggleEditScope(scope)}
                        className="w-3.5 h-3.5 rounded border-border"
                      />
                      {SCOPE_LABELS[scope]}
                    </label>
                  ))}
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    size="sm"
                    disabled={!editName.trim() || editScopes.length === 0}
                    onClick={() => handleUpdate(k.prefix)}
                    className="h-7 text-xs"
                  >
                    Save
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={cancelEdit}
                    className="h-7 text-xs"
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <div key={k.prefix} className="px-4 py-3 flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground">{k.name}</p>
                  <p className="text-xs text-muted-foreground font-mono">
                    cwk_{k.prefix}…
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {k.scopes.map((s) => SCOPE_LABELS[s] ?? s).join(', ')}
                  </p>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0 mt-0.5">
                  <span className="text-[10px] text-muted-foreground">
                    {k.created_at ? k.created_at.slice(0, 10) : ''}
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => startEdit(k)}
                    className="h-auto py-1 px-2 text-xs"
                  >
                    Edit
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDelete(k.prefix, k.name)}
                    className="text-destructive hover:text-destructive h-auto py-1 px-2"
                  >
                    Delete
                  </Button>
                </div>
              </div>
            )
          )}
        </div>
      )}

      {/* Add key form */}
      {adding ? (
        <form onSubmit={handleCreate} className="space-y-3 p-3 border border-border rounded-lg bg-muted/30">
          <div>
            <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">
              Key name
            </label>
            <Input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="e.g. Home Assistant"
              required
              autoFocus
            />
          </div>
          <div>
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
              Scopes
            </p>
            <div className="grid grid-cols-2 gap-1.5">
              {ALL_SCOPES.map((scope) => (
                <label key={scope} className="flex items-center gap-2 cursor-pointer text-sm">
                  <input
                    type="checkbox"
                    checked={newScopes.includes(scope)}
                    onChange={() => toggleScope(scope)}
                    className="w-4 h-4 rounded border-border"
                  />
                  {SCOPE_LABELS[scope]}
                </label>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button type="submit" size="sm" disabled={!newName.trim() || newScopes.length === 0}>
              Create key
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => { setAdding(false); setNewName(''); setNewScopes([...ALL_SCOPES]) }}
            >
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <Button type="button" size="sm" variant="outline" onClick={() => setAdding(true)}>
          + Add key
        </Button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Notifications section
// ---------------------------------------------------------------------------

const DEPTH_OPTIONS = [
  { value: 'minimal', label: 'Minimal — "New message" (no sender, no content)' },
  { value: 'sender', label: 'Sender — name only (default)' },
  { value: 'preview', label: 'Preview — name + first 50 chars of text' },
] as const

function NotificationsSection() {
  const queryClient = useQueryClient()
  const [consentFor, setConsentFor] = useState<InstalledPlugin | null>(null)
  // Local draft of depth overrides — { pluginName: depth }
  const [depthDraft, setDepthDraft] = useState<Record<string, string>>({})
  const [depthSaved, setDepthSaved] = useState(false)

  const { data } = useQuery<{
    notification_detail: string
    hiatus_enabled: boolean
    hiatus_duration_minutes: number
    hiatus_started_at: number
    reminder_enabled: boolean
    reminder_days: number
    reminder_contacts: string[]
    notification_depth: Record<string, string>
  }>({
    queryKey: ['settings-notifications'],
    queryFn: () =>
      fetch('/api/ui/settings/notifications', { credentials: 'same-origin' }).then((r) => r.json()),
    staleTime: 30_000,
  })

  // Live countdown ticker for the active hiatus — updates every 30 s.
  const hiatusStartedAt = data?.hiatus_started_at ?? 0
  const hiatusDurationMinutes = data?.hiatus_duration_minutes ?? 30
  const [hiatusNow, setHiatusNow] = useState(() => Date.now())
  useEffect(() => {
    if (!data?.hiatus_enabled || hiatusStartedAt <= 0) return
    const tick = () => setHiatusNow(Date.now())
    tick()
    const id = setInterval(tick, 30_000)
    return () => clearInterval(id)
  }, [data?.hiatus_enabled, hiatusStartedAt, hiatusDurationMinutes])
  const hiatusEndsAt = hiatusStartedAt > 0
    ? hiatusStartedAt * 1000 + hiatusDurationMinutes * 60_000
    : 0
  const minutesLeft = hiatusEndsAt > 0
    ? Math.max(1, Math.ceil((hiatusEndsAt - hiatusNow) / 60_000))
    : 0

  // Local state for the reminder contacts picker.
  // Initialised from server data when it first loads; updated by checkbox toggles.
  const [reminderHandles, setReminderHandles] = useState<string[]>([])
  useEffect(() => {
    if (data) setReminderHandles(data.reminder_contacts ?? [])
  }, [data])

  type WhitelistGrouped = {
    contacts: { name: string; all_handles: string[]; whitelisted_handles: string[] }[]
    unknown: string[]
  }
  const { data: wlData } = useQuery<WhitelistGrouped>({
    queryKey: ['whitelist-grouped'],
    queryFn: () =>
      fetch('/api/ui/settings/whitelist/grouped', { credentials: 'same-origin' }).then((r) => r.json()),
    staleTime: 60_000,
  })

  function toggleReminderContact(handles: string[], checked: boolean) {
    setReminderHandles((prev) => {
      const s = new Set(prev)
      handles.forEach((h) => (checked ? s.add(h) : s.delete(h)))
      return [...s]
    })
  }

  const { data: plugins = [] } = useQuery<InstalledPlugin[]>({
    queryKey: ['plugins-installed'],
    queryFn: () => fetch('/api/plugins/installed', { credentials: 'same-origin' }).then((r) => r.json()),
    staleTime: 30_000,
  })
  const notifyPlugins = plugins.filter((p) => p.tier === 'notify')

  const { mutation: detailMut, saved: detailSaved } = useSettingsMutation('/api/settings/notification_detail')
  const { mutation: hiatusMut, saved: hiatusSaved } = useSettingsMutation('/api/settings/hiatus_settings')
  const { mutation: reminderMut, saved: reminderSaved } = useSettingsMutation('/api/settings/reminder_settings')

  const depthMutation = useMutation({
    mutationFn: (depths: Record<string, string>) =>
      fetch('/api/ui/settings/notification_depth', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ depths }),
      }).then((r) => {
        if (!r.ok) throw new Error(`${r.status}`)
        return r.json()
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings-notifications'] })
      setDepthSaved(true)
      setTimeout(() => setDepthSaved(false), 2000)
    },
    onError: () => toast.error('Failed to save depth settings.'),
  })

  const toggleMutation = useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      fetch('/api/plugins/configure', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, enabled }),
      }).then((r) => {
        if (!r.ok) throw new Error(`${r.status}`)
        return r.json()
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['plugins-installed'] }),
    onError: () => toast.error('Failed to update plugin state.'),
  })

  function handleToggle(plugin: InstalledPlugin, targetEnabled: boolean) {
    if (targetEnabled && plugin.tier === 'notify') {
      setConsentFor(plugin)
    } else {
      toggleMutation.mutate({ name: plugin.name, enabled: targetEnabled })
    }
  }

  // Merge server-side depth map with local draft overrides.
  const serverDepths = data?.notification_depth ?? {}
  function effectiveDepth(pluginName: string): string {
    return depthDraft[pluginName] ?? serverDepths[pluginName] ?? serverDepths['default'] ?? 'sender'
  }

  function handleDepthChange(pluginName: string, value: string) {
    setDepthDraft((d) => ({ ...d, [pluginName]: value }))
  }

  function saveDepths() {
    // Merge server map with local draft; remove entries that equal the default
    // to keep the config compact, but always preserve an explicit "default" key.
    const merged = { ...serverDepths, ...depthDraft }
    depthMutation.mutate(merged)
  }

  if (!data) return <p className="text-xs text-muted-foreground">Loading…</p>

  return (
    <div className="space-y-5">
      {/* Detail level */}
      <form onSubmit={(e) => { e.preventDefault(); detailMut.mutate(new FormData(e.currentTarget)) }}>
        <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">
          Notification detail
        </label>
        <select
          name="notification_detail"
          defaultValue={data.notification_detail}
          className="w-full py-2 px-3 text-sm text-foreground bg-muted
                     border border-border rounded-lg focus:outline-none focus:border-primary"
        >
          <option value="rich">Rich — sender name + message text</option>
          <option value="sender_only">Sender only — name, no message text</option>
          <option value="private">Private — no name, no text</option>
        </select>
        <div className="flex items-center gap-2 mt-2">
          <SaveButton pending={detailMut.isPending} />
          <SaveOk visible={detailSaved} />
        </div>
      </form>

      {/* notify-tier plugins with per-plugin depth */}
      {notifyPlugins.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            Notification plugins
          </p>
          <div className="space-y-3">
            {notifyPlugins.map((plugin) => (
              <div
                key={plugin.name}
                className="py-2 border-b border-border last:border-0"
              >
                <div className="flex items-center gap-3">
                  <span className="text-xl flex-shrink-0" aria-hidden="true">{plugin.icon || '🔌'}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-foreground">
                        {plugin.display_name}
                      </span>
                      {plugin.installed_version && (
                        <span className="text-[10px] text-muted-foreground">
                          v{plugin.installed_version}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5 truncate">{plugin.description}</p>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={plugin.enabled}
                    aria-label={`${plugin.enabled ? 'Disable' : 'Enable'} ${plugin.display_name}`}
                    onClick={() => handleToggle(plugin, !plugin.enabled)}
                    disabled={toggleMutation.isPending}
                    className={cn(
                      'flex-shrink-0 w-8 h-4 rounded-full transition-colors',
                      plugin.enabled ? 'bg-primary' : 'bg-border',
                    )}
                  >
                    <span
                      className={cn(
                        'block w-3 h-3 rounded-full bg-white transition-transform mx-0.5',
                        plugin.enabled ? 'translate-x-4' : 'translate-x-0',
                      )}
                    />
                  </button>
                </div>
                {/* Per-plugin depth dropdown — shown for all notify plugins */}
                <div className="mt-2 flex items-center gap-2 pl-9">
                  <label
                    htmlFor={`depth-${plugin.name}`}
                    className="text-xs text-muted-foreground whitespace-nowrap"
                  >
                    Notification depth:
                  </label>
                  <select
                    id={`depth-${plugin.name}`}
                    value={effectiveDepth(plugin.name)}
                    onChange={(e) => handleDepthChange(plugin.name, e.target.value)}
                    className="flex-1 min-w-0 py-1 px-2 text-xs text-foreground bg-muted
                               border border-border rounded focus:outline-none focus:border-primary"
                  >
                    {DEPTH_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>
              </div>
            ))}
          </div>
          {/* Default depth for all unnamed notify plugins */}
          <div className="mt-3 flex items-center gap-2">
            <label
              htmlFor="depth-default"
              className="text-xs text-muted-foreground whitespace-nowrap"
            >
              Default depth (all other plugins):
            </label>
            <select
              id="depth-default"
              value={effectiveDepth('default')}
              onChange={(e) => handleDepthChange('default', e.target.value)}
              className="flex-1 min-w-0 py-1 px-2 text-xs text-foreground bg-muted
                         border border-border rounded focus:outline-none focus:border-primary"
            >
              {DEPTH_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2 mt-2">
            <Button
              type="button"
              size="sm"
              onClick={saveDepths}
              disabled={depthMutation.isPending}
            >
              {depthMutation.isPending ? 'Saving…' : 'Save depth settings'}
            </Button>
            <SaveOk visible={depthSaved} />
          </div>
        </div>
      )}

      {/* Hiatus mode */}
      <form onSubmit={(e) => { e.preventDefault(); hiatusMut.mutate(new FormData(e.currentTarget)) }}>
        <div className="flex items-center mb-1">
          <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Hiatus mode
          </label>
          <PinButton settingKey="hiatus_enabled" />
        </div>
        <p className="text-xs text-muted-foreground mb-2">
          Suppress notifications while you're actively chatting — no buzz if you just sent a message
          to that contact within the last N minutes.
        </p>
        {data.hiatus_enabled && hiatusStartedAt > 0 && (
          <p className="text-xs text-warning mb-2">
            Active — {minutesLeft}m left · Saving will restart the timer from now.
          </p>
        )}
        <label className="flex items-center gap-2 cursor-pointer text-sm mb-2">
          <input
            type="checkbox"
            name="hiatus_enabled"
            value="true"
            defaultChecked={data.hiatus_enabled}
            className="w-4 h-4 rounded border-border"
          />
          Enable hiatus mode
        </label>
        <div className="flex items-center gap-2">
          <label htmlFor="hiatus-mins" className="text-xs text-muted-foreground whitespace-nowrap">
            Silence window (minutes):
          </label>
          <Input
            type="number"
            id="hiatus-mins"
            name="hiatus_duration_minutes"
            defaultValue={data.hiatus_duration_minutes}
            min={1}
            max={1440}
            className="w-20"
          />
        </div>
        <div className="flex items-center gap-2 mt-2">
          <SaveButton pending={hiatusMut.isPending} />
          <SaveOk visible={hiatusSaved} />
        </div>
      </form>

      {/* Reminder timers */}
      <form onSubmit={(e) => {
        e.preventDefault()
        const fd = new FormData(e.currentTarget)
        fd.append('reminder_contacts', JSON.stringify(reminderHandles))
        reminderMut.mutate(fd)
      }}>
        <div className="flex items-center mb-1">
          <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Reminder timers
          </label>
          <PinButton settingKey="reminder_enabled" />
        </div>
        <p className="text-xs text-muted-foreground mb-2">
          Push a daily reminder when you haven't heard from someone in N days.
        </p>
        <label className="flex items-center gap-2 cursor-pointer text-sm mb-2">
          <input
            type="checkbox"
            name="reminder_enabled"
            value="true"
            defaultChecked={data.reminder_enabled}
            className="w-4 h-4 rounded border-border"
          />
          Enable reminders
        </label>
        <div className="flex items-center gap-2">
          <label htmlFor="reminder-days" className="text-xs text-muted-foreground whitespace-nowrap">
            Remind after (days):
          </label>
          <Input
            type="number"
            id="reminder-days"
            name="reminder_days"
            defaultValue={data.reminder_days}
            min={1}
            max={365}
            className="w-20"
          />
        </div>

        {/* Contacts filter */}
        <div className="mt-3">
          <p className="text-xs font-medium text-foreground mb-0.5">Watch specific contacts</p>
          <p className="text-xs text-muted-foreground mb-2">
            Leave all unchecked to watch every contact. Check one or more to limit reminders to those people.
          </p>
          {wlData && (wlData.contacts.length > 0 || wlData.unknown.length > 0) ? (
            <div className="max-h-48 overflow-y-auto space-y-1 rounded border border-border p-2 bg-muted/30">
              {wlData.contacts.map((c) => {
                const handleSet = new Set(reminderHandles)
                const checked = c.all_handles.some((h) => handleSet.has(h))
                return (
                  <label key={c.name} className="flex items-center gap-2 cursor-pointer text-sm select-none">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(e) => toggleReminderContact(c.all_handles, e.target.checked)}
                      className="w-4 h-4 rounded border-border flex-shrink-0"
                    />
                    {c.name}
                  </label>
                )
              })}
              {wlData.unknown.map((h) => {
                const checked = new Set(reminderHandles).has(h)
                return (
                  <label key={h} className="flex items-center gap-2 cursor-pointer text-sm font-mono select-none">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(e) => toggleReminderContact([h], e.target.checked)}
                      className="w-4 h-4 rounded border-border flex-shrink-0"
                    />
                    {h}
                  </label>
                )
              })}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground italic">
              {wlData ? 'No whitelisted contacts found.' : 'Loading contacts…'}
            </p>
          )}
        </div>

        <div className="flex items-center gap-2 mt-3">
          <SaveButton pending={reminderMut.isPending} />
          <SaveOk visible={reminderSaved} />
        </div>
      </form>

      {/* Consent dialog for notify plugins */}
      {consentFor && (
        <ConsentDialog
          plugin={consentFor}
          onConfirm={() => {
            toggleMutation.mutate({ name: consentFor.name, enabled: true })
            setConsentFor(null)
          }}
          onCancel={() => setConsentFor(null)}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Advanced section
// ---------------------------------------------------------------------------

function AdvancedSection() {
  const { data } = useQuery<{ web_port: number; web_bind: string; web_proxy_headers: boolean }>({
    queryKey: ['settings-advanced'],
    queryFn: () =>
      fetch('/api/ui/settings/advanced', { credentials: 'same-origin' }).then((r) => r.json()),
    staleTime: 30_000,
  })
  const [portSaved, setPortSaved] = useState(false)
  const [bindSaved, setBindSaved] = useState(false)
  const [proxySaved, setProxySaved] = useState(false)

  if (!data) return <p className="text-xs text-muted-foreground">Loading…</p>

  async function savePort(value: string) {
    const fd = new FormData(); fd.append('port', value)
    const r = await fetch('/api/settings/port', { method: 'POST', body: fd, credentials: 'same-origin' })
    if (r.ok) { setPortSaved(true); setTimeout(() => setPortSaved(false), 3000) }
  }

  async function saveBind(value: string) {
    const fd = new FormData(); fd.append('bind', value)
    const r = await fetch('/api/settings/bind', { method: 'POST', body: fd, credentials: 'same-origin' })
    if (r.ok) { setBindSaved(true); setTimeout(() => setBindSaved(false), 3000) }
  }

  async function saveProxy(checked: boolean) {
    const fd = new FormData(); fd.append('proxy_headers', checked ? 'true' : 'false')
    const r = await fetch('/api/settings/proxy_headers', { method: 'POST', body: fd, credentials: 'same-origin' })
    if (r.ok) { setProxySaved(true); setTimeout(() => setProxySaved(false), 2000) }
  }

  return (
    <div className="space-y-5">
      {/* Port */}
      <div>
        <label htmlFor="web-port" className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">
          Port
        </label>
        <Input
          type="number"
          id="web-port"
          defaultValue={data.web_port}
          min={1024}
          max={65535}
          onBlur={(e) => savePort(e.target.value)}
          className="w-32"
        />
        {portSaved && (
          <p className="mt-1 text-xs text-warning">
            Port change saved — restart chatwire web for it to take effect.
          </p>
        )}
      </div>

      {/* Listen on */}
      <div>
        <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">
          Listen on
        </label>
        <select
          defaultValue={['127.0.0.1', 'localhost', '0.0.0.0'].includes(data.web_bind) ? data.web_bind : 'custom'}
          onChange={(e) => { if (e.target.value !== 'custom') saveBind(e.target.value) }}
          className="py-2 px-3 text-sm text-foreground bg-background
                     border border-border rounded-lg focus:outline-none focus:border-primary"
        >
          <option value="127.0.0.1">localhost only</option>
          <option value="0.0.0.0">all interfaces</option>
          <option value="custom">custom…</option>
        </select>
        {bindSaved && <span className="ml-2 text-xs text-success">Saved</span>}
      </div>

      {/* Reverse proxy */}
      <div>
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            defaultChecked={data.web_proxy_headers}
            onChange={(e) => saveProxy(e.target.checked)}
            className="w-4 h-4 rounded border-border"
          />
          <span className="text-sm font-medium text-foreground">
            Trust reverse proxy headers
          </span>
        </label>
        <p className="mt-1 text-xs text-muted-foreground ml-7">
          When enabled, chatwire trusts{' '}
          <code className="bg-muted px-1 rounded">X-Forwarded-For</code> and{' '}
          <code className="bg-muted px-1 rounded">X-Forwarded-Proto</code> headers
          from an upstream proxy. Do not enable if exposed directly to the internet.
        </p>
        {proxySaved && <span className="text-xs text-success ml-7">Saved</span>}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Password section
// ---------------------------------------------------------------------------

export function PasswordSection() {
  const qc = useQueryClient()
  const { data } = useQuery<{ auth_enabled: boolean }>({
    queryKey: ['settings-password-status'],
    queryFn: () =>
      fetch('/api/ui/settings/password', { credentials: 'same-origin' }).then((r) => r.json()),
    staleTime: 30_000,
  })

  const [currentPw, setCurrentPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [confirmPw, setConfirmPw] = useState('')
  const [pending, setPending] = useState(false)

  const authEnabled = data?.auth_enabled ?? false

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (newPw !== confirmPw) {
      toast.error('Passwords do not match.')
      return
    }
    setPending(true)
    try {
      const r = await fetch('/api/ui/settings/password', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: currentPw, new_password: newPw }),
      })
      const d = await r.json()
      if (!r.ok) {
        toast.error(d.detail ?? 'Error.')
      } else {
        toast.success(authEnabled ? 'Password changed.' : 'Password set.')
        setCurrentPw('')
        setNewPw('')
        setConfirmPw('')
        qc.invalidateQueries({ queryKey: ['settings-password-status'] })
      }
    } finally {
      setPending(false)
    }
  }

  async function handleClear() {
    if (!confirm('Remove the web UI password? Anyone on the local network can access chatwire without logging in.')) return
    setPending(true)
    try {
      const r = await fetch('/api/ui/settings/password', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: currentPw, clear: true }),
      })
      const d = await r.json()
      if (!r.ok) {
        toast.error(d.detail ?? 'Error.')
      } else {
        toast.success('Password removed. Auth is now disabled.')
        setCurrentPw('')
        qc.invalidateQueries({ queryKey: ['settings-password-status'] })
      }
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">
        {authEnabled
          ? 'A password is currently set. Enter your current password to change or remove it.'
          : 'No password is set — anyone with local network access can use the UI.'}
      </p>
      <form onSubmit={handleSubmit} className="space-y-3">
        {authEnabled && (
          <div>
            <label htmlFor="pw-current" className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">
              Current password
            </label>
            <Input
              id="pw-current"
              type="password"
              value={currentPw}
              onChange={(e) => setCurrentPw(e.target.value)}
              autoComplete="current-password"
            />
          </div>
        )}
        <div>
          <label htmlFor="pw-new" className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">
            New password
          </label>
          <Input
            id="pw-new"
            type="password"
            value={newPw}
            onChange={(e) => setNewPw(e.target.value)}
            autoComplete="new-password"
            minLength={6}
            required
          />
        </div>
        <div>
          <label htmlFor="pw-confirm" className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">
            Confirm new password
          </label>
          <Input
            id="pw-confirm"
            type="password"
            value={confirmPw}
            onChange={(e) => setConfirmPw(e.target.value)}
            autoComplete="new-password"
            minLength={6}
            required
          />
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <Button type="submit" disabled={pending} size="sm">
            {pending ? 'Saving…' : authEnabled ? 'Change password' : 'Set password'}
          </Button>
          {authEnabled && (
            <Button
              type="button"
              disabled={pending}
              onClick={handleClear}
              variant="outline"
              size="sm"
              className="text-destructive border-destructive hover:bg-muted"
            >
              Remove password
            </Button>
          )}
        </div>
      </form>
    </div>
  )
}

// ---------------------------------------------------------------------------
// About / version section
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Plugin tier badges + consent
// ---------------------------------------------------------------------------

type PluginTier = 'core' | 'official' | 'notify' | 'ui'

interface InstalledPlugin {
  name: string
  display_name: string
  description: string
  icon: string
  tier: PluginTier
  enabled: boolean
  dist_name: string | null
  installed_version: string | null
}

const TIER_META: Record<PluginTier, { label: string; badge: string; dot: string; info: string }> = {
  core: {
    label: 'core',
    badge: 'bg-muted text-muted-foreground',
    dot: 'text-muted-foreground',
    info: 'Built-in system component',
  },
  official: {
    label: 'official',
    badge: 'bg-blue-500/10 text-blue-400',
    dot: 'text-blue-400',
    info: 'Reviewed & signed — message forwarding',
  },
  notify: {
    label: 'notify',
    badge: 'bg-yellow-500/10 text-yellow-400',
    dot: 'text-yellow-400',
    info: 'Notifications only (sender name, no message content)',
  },
  ui: {
    label: 'ui',
    badge: 'bg-green-500/10 text-green-400',
    dot: 'text-green-400',
    info: 'No data access — CSS, themes, and UI widgets only',
  },
}

function TierBadge({ tier }: { tier: PluginTier }) {
  const m = TIER_META[tier] ?? TIER_META.core
  return (
    <span
      className={cn('inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded font-mono', m.badge)}
      title={m.info}
    >
      <span aria-hidden="true">{'⚙️🔵🟡🟢'[['core','official','notify','ui'].indexOf(tier)] ?? '⚙️'}</span>
      {m.label}
    </span>
  )
}

function ConsentDialog({
  plugin,
  onConfirm,
  onCancel,
}: {
  plugin: InstalledPlugin
  onConfirm: () => void
  onCancel: () => void
}) {
  const tier = plugin.tier
  if (tier === 'official') {
    return (
      <Dialog open onOpenChange={(open) => { if (!open) onCancel() }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Enable {plugin.display_name}?</DialogTitle>
            <DialogDescription>
              This plugin can read your message content and send messages on your behalf.
              It has been reviewed and signed by the chatwire team.
            </DialogDescription>
          </DialogHeader>
          <p className="text-xs text-muted-foreground px-6">
            Phone numbers and email addresses are never exposed. Plugins receive
            display names only.
          </p>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={onCancel}>Cancel</Button>
            <Button size="sm" onClick={onConfirm}>Enable</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    )
  }
  if (tier === 'notify') {
    return (
      <Dialog open onOpenChange={(open) => { if (!open) onCancel() }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Enable {plugin.display_name}?</DialogTitle>
            <DialogDescription>
              This plugin receives notification events. It only sees the sender's display
              name — it cannot read message content, phone numbers, or email addresses.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={onCancel}>Cancel</Button>
            <Button size="sm" onClick={onConfirm}>Enable</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    )
  }
  // ui tier: no consent required — call onConfirm immediately
  onConfirm()
  return null
}

function PluginsSection() {
  const queryClient = useQueryClient()
  const [consentFor, setConsentFor] = useState<InstalledPlugin | null>(null)

  const { data: plugins = [], isLoading, isError } = useQuery<InstalledPlugin[]>({
    queryKey: ['plugins-installed'],
    queryFn: () => fetch('/api/plugins/installed', { credentials: 'same-origin' }).then((r) => r.json()),
    staleTime: 30_000,
  })

  const toggleMutation = useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      fetch('/api/plugins/configure', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, enabled }),
      }).then((r) => {
        if (!r.ok) throw new Error(`${r.status}`)
        return r.json()
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['plugins-installed'] }),
    onError: () => toast.error('Failed to update plugin state.'),
  })

  function handleToggle(plugin: InstalledPlugin, targetEnabled: boolean) {
    if (targetEnabled && (plugin.tier === 'official' || plugin.tier === 'notify')) {
      setConsentFor(plugin)
    } else {
      toggleMutation.mutate({ name: plugin.name, enabled: targetEnabled })
    }
  }

  if (isLoading) return <p className="text-xs text-muted-foreground">Loading…</p>
  if (isError) return <p className="text-xs text-destructive">Failed to load plugins.</p>

  return (
    <div className="space-y-3">
      {plugins.length === 0 && (
        <p className="text-xs text-muted-foreground">No plugins installed.</p>
      )}
      {plugins.map((plugin) => (
        <div
          key={plugin.name}
          className="flex items-start gap-3 py-2 border-b border-border last:border-0"
        >
          {/* Icon */}
          <span className="text-xl flex-shrink-0" aria-hidden="true">{plugin.icon || '🔌'}</span>

          {/* Info */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-medium text-foreground">
                {plugin.display_name}
              </span>
              <TierBadge tier={plugin.tier} />
              {plugin.installed_version && (
                <span className="text-[10px] text-muted-foreground">
                  v{plugin.installed_version}
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-0.5 truncate">{plugin.description}</p>
            <p className="text-[10px] text-muted-foreground mt-0.5 italic">
              {TIER_META[plugin.tier]?.info ?? ''}
            </p>
          </div>

          {/* Toggle */}
          {plugin.tier !== 'core' && (
            <button
              type="button"
              role="switch"
              aria-checked={plugin.enabled}
              aria-label={`${plugin.enabled ? 'Disable' : 'Enable'} ${plugin.display_name}`}
              onClick={() => handleToggle(plugin, !plugin.enabled)}
              disabled={toggleMutation.isPending}
              className={cn(
                'flex-shrink-0 w-8 h-4 rounded-full transition-colors mt-1',
                plugin.enabled ? 'bg-primary' : 'bg-border',
              )}
            >
              <span
                className={cn(
                  'block w-3 h-3 rounded-full bg-white transition-transform mx-0.5',
                  plugin.enabled ? 'translate-x-4' : 'translate-x-0',
                )}
              />
            </button>
          )}
        </div>
      ))}

      {/* Consent dialog */}
      {consentFor && (
        <ConsentDialog
          plugin={consentFor}
          onConfirm={() => {
            toggleMutation.mutate({ name: consentFor.name, enabled: true })
            setConsentFor(null)
          }}
          onCancel={() => setConsentFor(null)}
        />
      )}
    </div>
  )
}

function AboutSection() {
  const { data } = useQuery({
    queryKey: ['health'],
    queryFn: () => fetch('/healthz').then((r) => r.json()),
    staleTime: 60_000,
  })
  const { data: ghData } = useQuery<{ tag_name?: string } | null>({
    queryKey: ['latest-release'],
    queryFn: () =>
      fetch('https://api.github.com/repos/allenbina/chatwire/releases/latest')
        .then((r) => r.ok ? r.json() : null)
        .catch(() => null),
    staleTime: 10 * 60_000,
  })

  const version = data?.release ?? data?.version ?? ''
  const latest = ghData?.tag_name?.replace(/^v/, '')
  const hasUpdate = latest && version && latest !== version

  return (
    <div className="space-y-3">
      <div>
        <p className="text-sm font-semibold text-foreground">
          chatwire <span className="font-normal text-muted-foreground">v{version}</span>
          {hasUpdate && (
            <span className="ml-2 text-xs text-warning">(v{latest} available)</span>
          )}
        </p>
        <p className="text-xs text-muted-foreground mt-0.5">
          Made by{' '}
          <a href="https://github.com/allenbina" target="_blank" rel="noopener"
             className="text-primary hover:underline">Allen Bina</a>
        </p>
      </div>
      <p className="text-xs text-muted-foreground">
        Released under the{' '}
        <a href="https://github.com/allenbina/chatwire/blob/main/LICENSE" target="_blank" rel="noopener"
           className="text-primary hover:underline">MIT License</a>.
        {' '}Source on{' '}
        <a href="https://github.com/allenbina/chatwire" target="_blank" rel="noopener"
           className="text-primary hover:underline">GitHub</a>.
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main SettingsPage
// ---------------------------------------------------------------------------

export function SettingsPage() {
  const navigate = useNavigate()
  const location = useLocation()

  // Open the accordion section matching the URL hash on first render.
  // e.g. /settings#appearance → open the "appearance" section.
  const initialOpen = location.hash ? [location.hash.slice(1)] : []
  const [openItems, setOpenItems] = useState<string[]>(initialOpen)

  // When the hash changes (e.g. user clicks the Appearance link while already
  // on settings) scroll the matching section into view.
  useEffect(() => {
    const section = location.hash.slice(1)
    if (!section) return
    setOpenItems((prev) => (prev.includes(section) ? prev : [...prev, section]))
    // Give the accordion a frame to expand, then scroll.
    requestAnimationFrame(() => {
      document.getElementById(`accordion-${section}`)?.scrollIntoView({
        behavior: 'smooth', block: 'start',
      })
    })
  }, [location.hash])

  return (
    <Layout>
      <div className="flex-1 overflow-y-auto bg-background">
        {/* Header */}
        <header className="flex items-center gap-2 px-4 py-3 border-b border-border
                           bg-muted flex-shrink-0">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => navigate(-1)}
            aria-label="back to conversations"
            className="p-2 md:hidden"
          >
            ‹
          </Button>
          <h2 className="text-sm font-semibold text-foreground">Settings</h2>
        </header>

        <div className="p-4">
          <div className="border border-border rounded-lg overflow-hidden max-w-2xl mx-auto">
            <Accordion type="multiple" value={openItems} onValueChange={setOpenItems}>
              <AccordionItem value="self-handles">
                <AccordionTrigger className="px-5 py-4 font-medium text-sm text-foreground bg-muted hover:bg-accent hover:no-underline transition-colors">
                  <span className="flex items-center gap-2">
                    <UserIcon />
                    Self handles
                  </span>
                </AccordionTrigger>
                <AccordionContent className="px-5 py-4 bg-background text-sm text-foreground">
                  <SelfHandlesSection />
                </AccordionContent>
              </AccordionItem>

              <AccordionItem value="whitelist">
                <AccordionTrigger className="px-5 py-4 font-medium text-sm text-foreground bg-muted hover:bg-accent hover:no-underline transition-colors">
                  <span className="flex items-center gap-2">
                    <ListIcon />
                    Whitelist
                  </span>
                </AccordionTrigger>
                <AccordionContent className="px-5 py-4 bg-background text-sm text-foreground">
                  <WhitelistSection />
                </AccordionContent>
              </AccordionItem>

              <AccordionItem value="appearance" id="accordion-appearance">
                <AccordionTrigger className="px-5 py-4 font-medium text-sm text-foreground bg-muted hover:bg-accent hover:no-underline transition-colors">
                  <span className="flex items-center gap-2">
                    <SunIcon />
                    Appearance
                  </span>
                </AccordionTrigger>
                <AccordionContent className="px-5 py-4 bg-background text-sm text-foreground">
                  <div className="space-y-5">
                    <div>
                      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                        Style
                      </p>
                      <StyleSection />
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                        Color Scheme
                      </p>
                      <ThemeSection />
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                        Color Editor
                      </p>
                      <ColorEditorSection />
                    </div>
                    {/* Decorations removed from UI — controlled by theme packs only */}
                    <div>
                      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                        Theme Packs
                      </p>
                      <ThemePackSection />
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                        Export / Import
                      </p>
                      <ThemeExportSection />
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                        Notification Sounds
                      </p>
                      <NotificationSoundsSection />
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                        Custom CSS
                      </p>
                      <CustomCssSection />
                    </div>
                  </div>
                </AccordionContent>
              </AccordionItem>

              <AccordionItem value="notifications">
                <AccordionTrigger className="px-5 py-4 font-medium text-sm text-foreground bg-muted hover:bg-accent hover:no-underline transition-colors">
                  <span className="flex items-center gap-2">
                    <BellIcon />
                    Notifications
                  </span>
                </AccordionTrigger>
                <AccordionContent className="px-5 py-4 bg-background text-sm text-foreground">
                  <NotificationsSection />
                </AccordionContent>
              </AccordionItem>

              <AccordionItem value="advanced">
                <AccordionTrigger className="px-5 py-4 font-medium text-sm text-foreground bg-muted hover:bg-accent hover:no-underline transition-colors">
                  <span className="flex items-center gap-2">
                    <SettingsIcon />
                    Advanced
                  </span>
                </AccordionTrigger>
                <AccordionContent className="px-5 py-4 bg-background text-sm text-foreground">
                  <AdvancedSection />
                </AccordionContent>
              </AccordionItem>

              <AccordionItem value="api">
                <AccordionTrigger className="px-5 py-4 font-medium text-sm text-foreground bg-muted hover:bg-accent hover:no-underline transition-colors">
                  <span className="flex items-center gap-2">
                    <CodeIcon />
                    API
                  </span>
                </AccordionTrigger>
                <AccordionContent className="px-5 py-4 bg-background text-sm text-foreground">
                  <ApiKeySection />
                </AccordionContent>
              </AccordionItem>

              <AccordionItem value="password">
                <AccordionTrigger className="px-5 py-4 font-medium text-sm text-foreground bg-muted hover:bg-accent hover:no-underline transition-colors">
                  <span className="flex items-center gap-2">
                    <LockIcon />
                    Password
                  </span>
                </AccordionTrigger>
                <AccordionContent className="px-5 py-4 bg-background text-sm text-foreground">
                  <PasswordSection />
                </AccordionContent>
              </AccordionItem>

              <AccordionItem value="plugins">
                <AccordionTrigger className="px-5 py-4 font-medium text-sm text-foreground bg-muted hover:bg-accent hover:no-underline transition-colors">
                  <span className="flex items-center gap-2">
                    <PuzzleIcon />
                    Plugins
                  </span>
                </AccordionTrigger>
                <AccordionContent className="px-5 py-4 bg-background text-sm text-foreground">
                  <PluginsSection />
                </AccordionContent>
              </AccordionItem>

              <AccordionItem value="automations">
                <AccordionTrigger className="px-5 py-4 font-medium text-sm text-foreground bg-muted hover:bg-accent hover:no-underline transition-colors">
                  <span className="flex items-center gap-2">
                    <ZapIcon />
                    Automations
                  </span>
                </AccordionTrigger>
                <AccordionContent className="px-5 py-4 bg-background text-sm text-foreground">
                  <AutomationsSection />
                </AccordionContent>
              </AccordionItem>

            </Accordion>

            {/* Plugin slot: extra sections injected by installed plugins */}
            <SlotRenderer slot="settings.page" />

            {/* About — always visible, below accordion */}
            <div className="mt-4 px-5 py-4 text-xs text-muted-foreground max-w-2xl mx-auto">
              <AboutSection />
            </div>
          </div>

          {/* Footer */}
          <div className="mt-4 flex items-center justify-center gap-3 text-xs text-muted-foreground max-w-2xl mx-auto">
            <a href="https://github.com/allenbina/chatwire/issues" target="_blank" rel="noopener"
               className="hover:text-foreground">Report a bug</a>
            <span>·</span>
            <a href="https://github.com/sponsors/allenbina" target="_blank" rel="noopener"
               className="hover:text-foreground">♥ Sponsor</a>
            <span>·</span>
            <a href="/logout" className="hover:text-foreground flex items-center gap-1">
              <LogOut className="h-3 w-3" />Sign out
            </a>
          </div>
        </div>
      </div>
    </Layout>
  )
}

// ---------------------------------------------------------------------------
// Automations section — rule builder UI
// ---------------------------------------------------------------------------

type TriggerType = 'text_exact' | 'text_contains' | 'text_regex' | 'always' | 'dsl' | 'on_send' | 'schedule'
type ActionType = 'reply' | 'webhook' | 'log'

interface RuleActionForm {
  type: ActionType
  text: string
  url: string
  method: string
  headers: string
  level: string
  message: string
}

interface AutomationRuleForm {
  name: string
  dslMode: boolean
  dslExpr: string
  triggerType: TriggerType
  pattern: string
  cron: string
  fromHandles: string
  notFromHandles: string
  toHandles: string
  notToHandles: string
  inGroup: 'any' | 'group_only' | 'one_to_one'
  groupGuid: string
  actions: RuleActionForm[]
  stopOnMatch: boolean
}

const _EMPTY_ACTION: RuleActionForm = {
  type: 'reply', text: '', url: '', method: 'POST', headers: '', level: 'info', message: '',
}
const _EMPTY_RULE_FORM: AutomationRuleForm = {
  name: '', dslMode: false, dslExpr: '', triggerType: 'text_contains', pattern: '', cron: '',
  fromHandles: '', notFromHandles: '', toHandles: '', notToHandles: '',
  inGroup: 'any', groupGuid: '',
  actions: [{ ..._EMPTY_ACTION }], stopOnMatch: false,
}

export function _formToApiRule(f: AutomationRuleForm): Record<string, unknown> {
  const actions = f.actions.map((a): Record<string, unknown> => {
    if (a.type === 'reply') return { type: 'reply', text: a.text }
    if (a.type === 'webhook') {
      const act: Record<string, unknown> = { type: 'webhook', url: a.url }
      if (a.method && a.method !== 'POST') act.method = a.method
      if (a.headers.trim()) {
        try { act.headers = JSON.parse(a.headers) } catch { /* skip invalid JSON */ }
      }
      return act
    }
    const act: Record<string, unknown> = { type: 'log', message: a.message }
    if (a.level && a.level !== 'info') act.level = a.level
    return act
  })

  if (f.dslMode) {
    const rule: Record<string, unknown> = {
      name: f.name,
      trigger: { type: 'dsl', expr: f.dslExpr },
      actions,
    }
    if (f.stopOnMatch) rule.stop_on_match = true
    return rule
  }

  const trigger: Record<string, unknown> = { type: f.triggerType }
  if (f.triggerType === 'schedule') {
    trigger.cron = f.cron
  } else if (f.triggerType !== 'always' && f.triggerType !== 'on_send') {
    trigger.pattern = f.pattern
  }

  const conditions: Record<string, unknown> = {}
  if (f.triggerType === 'on_send') {
    const to = f.toHandles.split(',').map(s => s.trim()).filter(Boolean)
    if (to.length) conditions.to_handles = to
    const notTo = f.notToHandles.split(',').map(s => s.trim()).filter(Boolean)
    if (notTo.length) conditions.not_to_handles = notTo
  } else if (f.triggerType !== 'schedule') {
    const from = f.fromHandles.split(',').map(s => s.trim()).filter(Boolean)
    if (from.length) conditions.from_handles = from
    const notFrom = f.notFromHandles.split(',').map(s => s.trim()).filter(Boolean)
    if (notFrom.length) conditions.not_from_handles = notFrom
  }
  if (f.triggerType !== 'schedule') {
    if (f.inGroup === 'group_only') conditions.in_group = true
    if (f.inGroup === 'one_to_one') conditions.in_group = false
    if (f.groupGuid.trim()) conditions.group_guid = f.groupGuid.trim()
  }

  const rule: Record<string, unknown> = { name: f.name, trigger, actions }
  if (Object.keys(conditions).length) rule.conditions = conditions
  if (f.stopOnMatch) rule.stop_on_match = true
  return rule
}

export function _apiRuleToForm(r: Record<string, unknown>): AutomationRuleForm {
  const trigger = (r.trigger as Record<string, unknown>) ?? {}
  const rawActions = (r.actions as Record<string, unknown>[]) ?? []
  const actions: RuleActionForm[] = rawActions.map(a => ({
    type: (a.type as ActionType) ?? 'reply',
    text: (a.text as string) ?? '',
    url: (a.url as string) ?? '',
    method: (a.method as string) ?? 'POST',
    headers: a.headers ? JSON.stringify(a.headers, null, 2) : '',
    level: (a.level as string) ?? 'info',
    message: (a.message as string) ?? '',
  }))

  if (trigger.type === 'dsl') {
    return {
      ..._EMPTY_RULE_FORM,
      name: (r.name as string) ?? '',
      dslMode: true,
      dslExpr: (trigger.expr as string) ?? '',
      actions: actions.length ? actions : [{ ..._EMPTY_ACTION }],
      stopOnMatch: Boolean(r.stop_on_match),
    }
  }

  if (trigger.type === 'schedule') {
    return {
      ..._EMPTY_RULE_FORM,
      name: (r.name as string) ?? '',
      triggerType: 'schedule',
      cron: (trigger.cron as string) ?? '',
      actions: actions.length ? actions : [{ ..._EMPTY_ACTION }],
      stopOnMatch: Boolean(r.stop_on_match),
    }
  }

  const conds = (r.conditions as Record<string, unknown>) ?? {}
  const inGroupRaw = conds.in_group
  let inGroup: AutomationRuleForm['inGroup'] = 'any'
  if (inGroupRaw === true) inGroup = 'group_only'
  else if (inGroupRaw === false) inGroup = 'one_to_one'

  const tt = (trigger.type as TriggerType) ?? 'text_contains'
  return {
    name: (r.name as string) ?? '',
    dslMode: false,
    dslExpr: '',
    triggerType: tt,
    pattern: (trigger.pattern as string) ?? '',
    cron: '',
    fromHandles: tt !== 'on_send' ? ((conds.from_handles as string[]) ?? []).join(', ') : '',
    notFromHandles: tt !== 'on_send' ? ((conds.not_from_handles as string[]) ?? []).join(', ') : '',
    toHandles: tt === 'on_send' ? ((conds.to_handles as string[]) ?? []).join(', ') : '',
    notToHandles: tt === 'on_send' ? ((conds.not_to_handles as string[]) ?? []).join(', ') : '',
    inGroup,
    groupGuid: (conds.group_guid as string) ?? '',
    actions: actions.length ? actions : [{ ..._EMPTY_ACTION }],
    stopOnMatch: Boolean(r.stop_on_match),
  }
}

const _TRIGGER_LABELS: Record<TriggerType, string> = {
  text_contains: 'Contains',
  text_exact: 'Exact match',
  text_regex: 'Regex',
  always: 'Always',
  dsl: 'DSL',
  on_send: 'On send',
  schedule: 'Schedule',
}

function AutomationsSection() {
  const qc = useQueryClient()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const [form, setForm] = useState<AutomationRuleForm>({ ..._EMPTY_RULE_FORM, actions: [{ ..._EMPTY_ACTION }] })
  const [saving, setSaving] = useState(false)

  const { data, isLoading } = useQuery<{ rules: Record<string, unknown>[] }>({
    queryKey: ['settings-automations'],
    queryFn: () =>
      fetch('/api/settings/automations', { credentials: 'same-origin' }).then(r => r.json()),
    staleTime: 30_000,
  })
  const rules = data?.rules ?? []

  function openAdd() {
    setEditingIndex(null)
    setForm({ ..._EMPTY_RULE_FORM, actions: [{ ..._EMPTY_ACTION }] })
    setDialogOpen(true)
  }

  function openEdit(idx: number) {
    setEditingIndex(idx)
    setForm(_apiRuleToForm(rules[idx]))
    setDialogOpen(true)
  }

  async function handleSave() {
    if (!form.name.trim()) { toast.error('Rule name is required'); return }
    if (form.dslMode) {
      if (!form.dslExpr.trim()) { toast.error('DSL expression is required'); return }
    } else if (form.triggerType === 'schedule') {
      if (!form.cron.trim()) { toast.error('Cron expression is required for schedule trigger'); return }
    } else if (form.triggerType !== 'always' && form.triggerType !== 'on_send' && !form.pattern.trim()) {
      toast.error('Pattern is required for this trigger type'); return
    }
    setSaving(true)
    try {
      const rule = _formToApiRule(form)
      const url = editingIndex === null
        ? '/api/settings/automations'
        : `/api/settings/automations/${editingIndex}`
      const method = editingIndex === null ? 'POST' : 'PUT'
      const r = await fetch(url, {
        method,
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(rule),
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      qc.invalidateQueries({ queryKey: ['settings-automations'] })
      setDialogOpen(false)
      toast.success(editingIndex === null ? 'Rule added' : 'Rule updated')
    } catch {
      toast.error('Failed to save rule')
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(idx: number) {
    try {
      const r = await fetch(`/api/settings/automations/${idx}`, {
        method: 'DELETE',
        credentials: 'same-origin',
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      qc.invalidateQueries({ queryKey: ['settings-automations'] })
      toast.success('Rule deleted')
    } catch {
      toast.error('Failed to delete rule')
    }
  }

  async function handleMove(idx: number, dir: -1 | 1) {
    const newIdx = idx + dir
    if (newIdx < 0 || newIdx >= rules.length) return
    const order = rules.map((_, i) => i)
    order.splice(newIdx, 0, order.splice(idx, 1)[0])
    try {
      const r = await fetch('/api/settings/automations/reorder', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ order }),
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      qc.invalidateQueries({ queryKey: ['settings-automations'] })
    } catch {
      toast.error('Failed to reorder rules')
    }
  }

  function updateAction(idx: number, patch: Partial<RuleActionForm>) {
    setForm(f => {
      const actions = [...f.actions]
      actions[idx] = { ...actions[idx], ...patch }
      return { ...f, actions }
    })
  }

  function addAction() {
    setForm(f => ({ ...f, actions: [...f.actions, { ..._EMPTY_ACTION }] }))
  }

  function removeAction(idx: number) {
    setForm(f => ({ ...f, actions: f.actions.filter((_, i) => i !== idx) }))
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        Declarative trigger → action rules evaluated against inbound and outbound iMessages.
        Rules fire in order. Supports <code>reply</code>, <code>webhook</code>, and <code>log</code> actions.
        Use <em>On send</em> trigger for outbound automation.
      </p>

      {isLoading && <p className="text-xs text-muted-foreground">Loading…</p>}

      {!isLoading && rules.length === 0 && (
        <p className="text-xs text-muted-foreground italic">No rules configured yet.</p>
      )}

      <div className="space-y-2">
        {rules.map((rule, idx) => {
          const ruleActions = (rule.actions as unknown[]) ?? []
          const rTrigger = (rule.trigger as Record<string, unknown>) ?? {}
          const triggerType = rTrigger.type as TriggerType
          const pattern = rTrigger.pattern as string | undefined
          const dslExpr = rTrigger.expr as string | undefined
          const cronExpr = rTrigger.cron as string | undefined
          return (
            <div key={idx} className="flex items-center justify-between rounded border border-border px-3 py-2 text-xs gap-2">
              <div className="min-w-0 flex-1 flex items-center gap-2 flex-wrap">
                <span className="font-medium">{(rule.name as string) || <em>unnamed</em>}</span>
                <span className="text-muted-foreground bg-muted rounded px-1.5 py-0.5 text-[10px]">
                  {_TRIGGER_LABELS[triggerType] ?? triggerType}
                </span>
                {triggerType === 'dsl' && dslExpr && (
                  <span className="text-muted-foreground font-mono truncate max-w-[200px]" title={dslExpr}>
                    {dslExpr}
                  </span>
                )}
                {triggerType === 'schedule' && cronExpr && (
                  <span className="text-muted-foreground font-mono truncate max-w-[140px]" title={cronExpr}>
                    {cronExpr}
                  </span>
                )}
                {triggerType !== 'dsl' && triggerType !== 'schedule' && pattern && (
                  <span className="text-muted-foreground font-mono truncate max-w-[140px]">
                    &ldquo;{pattern}&rdquo;
                  </span>
                )}
                <span className="text-muted-foreground">
                  {ruleActions.length} action{ruleActions.length !== 1 ? 's' : ''}
                </span>
              </div>
              <div className="flex gap-1 shrink-0 items-center">
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-6 w-6 p-0 text-xs"
                  disabled={idx === 0}
                  onClick={() => handleMove(idx, -1)}
                  title="Move up"
                >
                  ↑
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-6 w-6 p-0 text-xs"
                  disabled={idx === rules.length - 1}
                  onClick={() => handleMove(idx, 1)}
                  title="Move down"
                >
                  ↓
                </Button>
                <Button size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={() => openEdit(idx)}>
                  Edit
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-6 px-2 text-xs text-destructive hover:text-destructive"
                  onClick={() => handleDelete(idx)}
                >
                  Delete
                </Button>
              </div>
            </div>
          )
        })}
      </div>

      <Button size="sm" variant="outline" onClick={openAdd} className="text-xs">
        + Add rule
      </Button>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingIndex === null ? 'New automation rule' : 'Edit automation rule'}</DialogTitle>
            <DialogDescription>
              Configure a trigger, optional conditions, and one or more actions.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 text-sm">
            {/* Name */}
            <div>
              <label className="block text-xs font-medium mb-1">Rule name</label>
              <Input
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                placeholder="e.g. greeting"
                className="text-xs"
              />
            </div>

            {/* Trigger */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-xs font-medium">Trigger</p>
                <button
                  type="button"
                  className="text-xs text-muted-foreground hover:text-foreground underline"
                  onClick={() => setForm(f => ({ ...f, dslMode: !f.dslMode, dslExpr: '', pattern: '' }))}
                >
                  {form.dslMode ? 'Switch to structured form' : 'Switch to DSL mode'}
                </button>
              </div>
              {form.dslMode ? (
                <div className="space-y-1.5">
                  <Textarea
                    value={form.dslExpr}
                    onChange={e => setForm(f => ({ ...f, dslExpr: e.target.value }))}
                    placeholder="(from:+1 OR from:+2) AND contains:urgent AND NOT in:group"
                    className="text-xs min-h-[80px] font-mono"
                  />
                  <p className="text-xs text-muted-foreground">
                    Predicates: <code>from:+1</code> <code>not_from:+1</code> <code>contains:word</code>{' '}
                    <code>exact:hi</code> <code>regex:"…"</code> <code>in:group</code> <code>in:1to1</code>{' '}
                    <code>always</code> · Operators: <code>AND</code> <code>OR</code> <code>NOT</code> <code>( )</code>
                  </p>
                </div>
              ) : (
                <>
                  <div className="flex gap-2">
                    <select
                      value={form.triggerType}
                      onChange={e => setForm(f => ({ ...f, triggerType: e.target.value as TriggerType }))}
                      className="text-xs border border-border rounded px-2 py-1 bg-background flex-shrink-0"
                    >
                      <option value="text_contains">Contains</option>
                      <option value="text_exact">Exact match</option>
                      <option value="text_regex">Regex</option>
                      <option value="always">Always</option>
                      <option value="on_send">On send (outbound)</option>
                      <option value="schedule">Schedule (cron)</option>
                    </select>
                    {form.triggerType !== 'always' && form.triggerType !== 'on_send' && form.triggerType !== 'schedule' && (
                      <Input
                        value={form.pattern}
                        onChange={e => setForm(f => ({ ...f, pattern: e.target.value }))}
                        placeholder={form.triggerType === 'text_regex' ? 'e.g. hello|hi' : 'e.g. hello'}
                        className="text-xs"
                      />
                    )}
                    {form.triggerType === 'schedule' && (
                      <Input
                        value={form.cron}
                        onChange={e => setForm(f => ({ ...f, cron: e.target.value }))}
                        placeholder="e.g. 0 9 * * 1-5"
                        className="text-xs font-mono"
                      />
                    )}
                  </div>
                  {form.triggerType === 'text_regex' && (
                    <p className="text-xs text-muted-foreground">
                      Case-insensitive regex, searched against the full message text.
                    </p>
                  )}
                  {form.triggerType === 'schedule' && (
                    <p className="text-xs text-muted-foreground">
                      5-field cron: <code>minute hour dom month dow</code> (0 = Sunday).
                      Example: <code>0 9 * * 1-5</code> = 09:00 Mon–Fri.
                      Supports <code>*</code>, ranges (<code>1-5</code>), lists (<code>1,3</code>), steps (<code>*/15</code>).
                    </p>
                  )}
                </>
              )}
            </div>

            {/* Conditions — hidden in DSL mode and schedule mode (no message context) */}
            {!form.dslMode && form.triggerType !== 'schedule' && <div className="space-y-2">
              <p className="text-xs font-medium">
                Conditions{' '}
                <span className="text-muted-foreground font-normal">(optional — absent = unrestricted)</span>
              </p>
              <div className="space-y-2 pl-2 border-l border-border">
                {form.triggerType === 'on_send' ? (
                  <>
                    <div>
                      <label className="block text-xs text-muted-foreground mb-1">
                        To handles (comma-separated)
                      </label>
                      <Input
                        value={form.toHandles}
                        onChange={e => setForm(f => ({ ...f, toHandles: e.target.value }))}
                        placeholder="+15551234567, +15559876543"
                        className="text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-muted-foreground mb-1">
                        Not to handles (comma-separated)
                      </label>
                      <Input
                        value={form.notToHandles}
                        onChange={e => setForm(f => ({ ...f, notToHandles: e.target.value }))}
                        placeholder="+15551234567"
                        className="text-xs"
                      />
                    </div>
                  </>
                ) : (
                  <>
                    <div>
                      <label className="block text-xs text-muted-foreground mb-1">
                        From handles (comma-separated)
                      </label>
                      <Input
                        value={form.fromHandles}
                        onChange={e => setForm(f => ({ ...f, fromHandles: e.target.value }))}
                        placeholder="+15551234567, +15559876543"
                        className="text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-muted-foreground mb-1">
                        Not from handles (comma-separated)
                      </label>
                      <Input
                        value={form.notFromHandles}
                        onChange={e => setForm(f => ({ ...f, notFromHandles: e.target.value }))}
                        placeholder="+15551234567"
                        className="text-xs"
                      />
                    </div>
                  </>
                )}
                <div>
                  <label className="block text-xs text-muted-foreground mb-1">Chat type</label>
                  <select
                    value={form.inGroup}
                    onChange={e => setForm(f => ({ ...f, inGroup: e.target.value as AutomationRuleForm['inGroup'] }))}
                    className="text-xs border border-border rounded px-2 py-1 bg-background"
                  >
                    <option value="any">Any (group or 1:1)</option>
                    <option value="group_only">Group messages only</option>
                    <option value="one_to_one">1:1 messages only</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-muted-foreground mb-1">
                    Group GUID (exact match)
                  </label>
                  <Input
                    value={form.groupGuid}
                    onChange={e => setForm(f => ({ ...f, groupGuid: e.target.value }))}
                    placeholder="iMessage;+;chat..."
                    className="text-xs"
                  />
                </div>
              </div>
            </div>}

            {/* Actions */}
            <div className="space-y-2">
              <p className="text-xs font-medium">Actions</p>
              {form.actions.map((action, aIdx) => (
                <div key={aIdx} className="space-y-2 p-2 border border-border rounded">
                  <div className="flex items-center gap-2">
                    <select
                      value={action.type}
                      onChange={e => updateAction(aIdx, { type: e.target.value as ActionType })}
                      className="text-xs border border-border rounded px-2 py-1 bg-background"
                    >
                      <option value="reply">Reply</option>
                      <option value="webhook">Webhook</option>
                      <option value="log">Log</option>
                    </select>
                    {form.actions.length > 1 && (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-6 px-2 text-xs text-destructive hover:text-destructive ml-auto"
                        onClick={() => removeAction(aIdx)}
                        type="button"
                      >
                        Remove
                      </Button>
                    )}
                  </div>

                  {action.type === 'reply' && (
                    <div>
                      <label className="block text-xs text-muted-foreground mb-1">
                        Reply text — supports{' '}
                        <code>{'{handle}'}</code> <code>{'{name}'}</code> <code>{'{text}'}</code>
                      </label>
                      <Textarea
                        value={action.text}
                        onChange={e => updateAction(aIdx, { text: e.target.value })}
                        placeholder="Hi {name}! You said: {text}"
                        className="text-xs min-h-[60px]"
                      />
                    </div>
                  )}

                  {action.type === 'webhook' && (
                    <div className="space-y-2">
                      <div>
                        <label className="block text-xs text-muted-foreground mb-1">URL</label>
                        <Input
                          value={action.url}
                          onChange={e => updateAction(aIdx, { url: e.target.value })}
                          placeholder="https://example.com/webhook"
                          className="text-xs"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-muted-foreground mb-1">Method</label>
                        <select
                          value={action.method}
                          onChange={e => updateAction(aIdx, { method: e.target.value })}
                          className="text-xs border border-border rounded px-2 py-1 bg-background"
                        >
                          <option value="POST">POST</option>
                          <option value="GET">GET</option>
                          <option value="PUT">PUT</option>
                          <option value="PATCH">PATCH</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs text-muted-foreground mb-1">
                          Headers (JSON, optional)
                        </label>
                        <Textarea
                          value={action.headers}
                          onChange={e => updateAction(aIdx, { headers: e.target.value })}
                          placeholder={'{"Authorization": "Bearer token"}'}
                          className="text-xs min-h-[60px] font-mono"
                        />
                      </div>
                    </div>
                  )}

                  {action.type === 'log' && (
                    <div className="space-y-2">
                      <div>
                        <label className="block text-xs text-muted-foreground mb-1">Level</label>
                        <select
                          value={action.level}
                          onChange={e => updateAction(aIdx, { level: e.target.value })}
                          className="text-xs border border-border rounded px-2 py-1 bg-background"
                        >
                          <option value="debug">debug</option>
                          <option value="info">info</option>
                          <option value="warning">warning</option>
                          <option value="error">error</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs text-muted-foreground mb-1">
                          Message — supports{' '}
                          <code>{'{handle}'}</code> <code>{'{name}'}</code>{' '}
                          <code>{'{text}'}</code> <code>{'{rule}'}</code>
                        </label>
                        <Input
                          value={action.message}
                          onChange={e => updateAction(aIdx, { message: e.target.value })}
                          placeholder="Rule {rule} fired by {name}"
                          className="text-xs"
                        />
                      </div>
                    </div>
                  )}
                </div>
              ))}
              <Button
                size="sm"
                variant="outline"
                onClick={addAction}
                type="button"
                className="text-xs"
              >
                + Add action
              </Button>
            </div>

            {/* Stop on match */}
            <label className="flex items-center gap-2 text-xs cursor-pointer">
              <input
                type="checkbox"
                checked={form.stopOnMatch}
                onChange={e => setForm(f => ({ ...f, stopOnMatch: e.target.checked }))}
                className="rounded border border-border"
              />
              Stop on match — no subsequent rules fire after this one
            </label>
          </div>

          <DialogFooter>
            <Button size="sm" variant="ghost" onClick={() => setDialogOpen(false)} type="button">
              Cancel
            </Button>
            <Button size="sm" onClick={handleSave} disabled={saving} type="button">
              {saving ? 'Saving…' : 'Save rule'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tiny inline SVG icons
// ---------------------------------------------------------------------------

function UserIcon() {
  return (
    <svg className="w-4 h-4 text-muted-foreground" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
    </svg>
  )
}
function ListIcon() {
  return (
    <svg className="w-4 h-4 text-muted-foreground" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2M9 5h6m-3 7v4m-2-2h4"/>
    </svg>
  )
}
function SunIcon() {
  return (
    <svg className="w-4 h-4 text-muted-foreground" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
      <line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
    </svg>
  )
}
function BellIcon() {
  return (
    <svg className="w-4 h-4 text-muted-foreground" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>
    </svg>
  )
}
function SettingsIcon() {
  return (
    <svg className="w-4 h-4 text-muted-foreground" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/>
    </svg>
  )
}
function CodeIcon() {
  return (
    <svg className="w-4 h-4 text-muted-foreground" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 9l3 3-3 3m5 0h3"/><rect x="3" y="3" width="18" height="18" rx="2"/>
    </svg>
  )
}
function LockIcon() {
  return (
    <svg className="w-4 h-4 text-muted-foreground" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
    </svg>
  )
}
function PuzzleIcon() {
  return (
    <svg className="w-4 h-4 text-muted-foreground" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
      <path d="M19.439 7.85c-.049.322.059.648.289.878l1.568 1.568c.47.47.706 1.087.706 1.704s-.235 1.233-.706 1.704l-1.611 1.611a.98.98 0 0 1-.837.276c-.47-.07-.802-.48-.968-.925a2.501 2.501 0 1 0-3.214 3.214c.445.166.855.497.925.968a.979.979 0 0 1-.276.837l-1.61 1.61a2.404 2.404 0 0 1-1.705.707 2.402 2.402 0 0 1-1.704-.706l-1.568-1.568a1.026 1.026 0 0 0-.877-.29c-.493.074-.84.504-1.02.968a2.5 2.5 0 1 1-3.237-3.237c.464-.18.894-.527.967-1.02a1.026 1.026 0 0 0-.289-.877l-1.568-1.568A2.402 2.402 0 0 1 1.998 12c0-.617.236-1.234.706-1.704L4.23 8.77c.24-.24.581-.353.917-.303.515.077.877.528 1.073 1.01a2.5 2.5 0 1 0 3.259-3.259c-.482-.196-.933-.558-1.01-1.073-.05-.336.062-.676.303-.917l1.525-1.525A2.402 2.402 0 0 1 12 2c.617 0 1.234.236 1.704.706l1.568 1.568c.23.23.556.338.877.29.493-.074.84-.504 1.02-.968a2.5 2.5 0 1 1 3.237 3.237c-.464.18-.894.527-.967 1.02z"/>
    </svg>
  )
}
function ZapIcon() {
  return (
    <svg className="w-4 h-4 text-muted-foreground" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
    </svg>
  )
}
