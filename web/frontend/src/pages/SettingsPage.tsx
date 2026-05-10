/**
 * Settings page — full port of the Jinja2 _settings.html accordion UI.
 *
 * Phase 3: All settings sections are implemented here. Each section maps
 * directly to the corresponding accordion section in the Jinja2 template.
 * Settings are fetched from / persisted to the existing /api/settings/*
 * and /api/ui/* endpoints.
 */
import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useLocation } from 'react-router-dom'
import { toast } from 'sonner'
import { Layout } from '../components/Layout'
import { useTheme } from '../hooks/useTheme'
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
  return <span className="text-xs text-[--success]">Saved</span>
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

function CustomCssSection() {
  const { customCss, setCustomCss } = useTheme()
  const [draft, setDraft] = useState(customCss)
  const [saved, setSaved] = useState(false)

  // Keep draft in sync if another tab changes the value.
  useEffect(() => {
    setDraft(customCss)
  }, [customCss])

  async function handleSave() {
    await setCustomCss(draft)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">
        Raw CSS injected after all theme styles. Use{' '}
        <code className="bg-muted px-1 rounded">[data-theme=&quot;dracula&quot;]&nbsp;&#123;&nbsp;&#125;</code>{' '}
        selectors to scope rules to a specific theme.
      </p>
      <Textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder={"/* Example: scope a rule to Dracula only */\n[data-theme=\"dracula\"] .my-widget {\n  color: #ff79c6;\n}"}
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
  const { current, currentAccent, setTheme, setAccentColor, allSchemes } = useTheme()
  const [applying, setApplying] = useState(false)

  async function handleSelect(name: string) {
    if (applying || name === current) return
    setApplying(true)
    try {
      await setTheme(name)
    } finally {
      setApplying(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {allSchemes.map((t) => {
          const isActive = t.name === current
          return (
            <button
              key={t.name}
              type="button"
              onClick={() => handleSelect(t.name)}
              disabled={applying}
              className={cn(
                'flex items-center gap-2 px-3 py-2 rounded-lg text-sm border transition-colors',
                isActive
                  ? 'border-primary bg-primary text-primary-foreground font-semibold'
                  : 'border-border text-foreground hover:border-primary',
              )}
            >
              <span
                className="w-3 h-3 rounded-full flex-shrink-0"
                style={{ background: t.swatch }}
                aria-hidden="true"
              />
              {t.label}
            </button>
          )
        })}
      </div>

      {/* Accent color override */}
      <div>
        <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
          Accent color
        </label>
        <p className="text-xs text-muted-foreground mb-2">
          Override the theme&apos;s accent color. Leave blank to use the theme default.
        </p>
        <div className="flex items-center gap-3">
          <AccentColorPicker
            value={currentAccent}
            onChange={(color) => setAccentColor(color)}
          />
          {currentAccent && (
            <button
              type="button"
              onClick={() => setAccentColor('')}
              className="text-xs text-muted-foreground hover:text-destructive transition-colors"
            >
              Reset
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Style (structural theme) section
// ---------------------------------------------------------------------------

function StyleSection() {
  const { currentStyle, setStyle, allStyles } = useTheme()

  return (
    <div className="flex flex-wrap gap-3">
      {allStyles.map((s) => {
        const isActive = s.name === currentStyle
        return (
          <button
            key={s.name}
            type="button"
            onClick={() => setStyle(s.name)}
            className={cn(
              'flex flex-col gap-1 px-4 py-3 rounded-lg border text-left transition-colors min-w-[7rem]',
              isActive
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-border text-foreground hover:border-primary',
            )}
          >
            <span className="text-sm font-semibold">{s.label}</span>
            <span className="text-xs text-muted-foreground">{s.description}</span>
          </button>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Whitelist section
// ---------------------------------------------------------------------------

function WhitelistSection() {
  const qc = useQueryClient()
  const { data } = useQuery<{ rows: { label: string; value: string }[]; contact_names: string[] }>({
    queryKey: ['settings-whitelist'],
    queryFn: () =>
      fetch('/api/ui/settings/whitelist', { credentials: 'same-origin' }).then((r) => r.json()),
    staleTime: 30_000,
  })
  const [input, setInput] = useState('')
  const [showList, setShowList] = useState(false)
  const [syncMsg, setSyncMsg] = useState('')

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    if (!input.trim()) return
    const fd = new FormData()
    fd.append('input', input.trim())
    const r = await fetch('/whitelist/add', { method: 'POST', body: fd, credentials: 'same-origin' })
    if (r.ok) {
      setInput('')
      qc.invalidateQueries({ queryKey: ['settings-whitelist'] })
    }
  }

  async function handleSync() {
    const r = await fetch('/refresh_contacts', { method: 'POST', credentials: 'same-origin' })
    setSyncMsg(r.ok ? 'Synced' : 'Failed')
    setTimeout(() => setSyncMsg(''), 2000)
  }

  async function handleRemove(value: string) {
    const fd = new FormData()
    fd.append('input', value)
    await fetch('/whitelist/remove', { method: 'POST', body: fd, credentials: 'same-origin' })
    qc.invalidateQueries({ queryKey: ['settings-whitelist'] })
  }

  const rows = data?.rows ?? []
  const contactNames = data?.contact_names ?? []

  return (
    <div className="space-y-3">
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
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleSync}
        >
          ↻ Sync contacts
        </Button>
        {syncMsg && <span className="text-xs text-[--success]">{syncMsg}</span>}
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setShowList((v) => !v)}
        >
          {showList ? 'Hide contacts' : `Show contacts${rows.length ? ` (${rows.length})` : ''}`}
        </Button>
      </div>
      {showList && rows.length > 0 && (
        <ul className="space-y-1 max-h-48 overflow-y-auto">
          {rows.map((r) => (
            <li key={r.value} className="flex items-center justify-between text-xs py-1
                                         border-b border-border last:border-0">
              <span className="text-foreground font-mono">{r.label || r.value}</span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => handleRemove(r.value)}
                className="text-destructive hover:text-destructive ml-2 h-auto py-0"
              >
                Remove
              </Button>
            </li>
          ))}
        </ul>
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

  function toggleScope(scope: string) {
    setNewScopes((prev) =>
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
          {keys.map((k) => (
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
                  onClick={() => handleDelete(k.prefix, k.name)}
                  className="text-destructive hover:text-destructive h-auto py-1 px-2"
                >
                  Delete
                </Button>
              </div>
            </div>
          ))}
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
    reminder_enabled: boolean
    reminder_days: number
    notification_depth: Record<string, string>
  }>({
    queryKey: ['settings-notifications'],
    queryFn: () =>
      fetch('/api/ui/settings/notifications', { credentials: 'same-origin' }).then((r) => r.json()),
    staleTime: 30_000,
  })

  const { data: spamData } = useQuery<{ ntfy_topic: string }>({
    queryKey: ['settings-antispam'],
    queryFn: () =>
      fetch('/api/ui/settings/antispam', { credentials: 'same-origin' }).then((r) => r.json()),
    staleTime: 30_000,
  })

  const { data: plugins = [] } = useQuery<InstalledPlugin[]>({
    queryKey: ['plugins-installed'],
    queryFn: () => fetch('/api/plugins/installed', { credentials: 'same-origin' }).then((r) => r.json()),
    staleTime: 30_000,
  })
  const notifyPlugins = plugins.filter((p) => p.tier === 'notify')

  const { mutation: detailMut, saved: detailSaved } = useSettingsMutation('/api/settings/notification_detail')
  const { mutation: hiatusMut, saved: hiatusSaved } = useSettingsMutation('/api/settings/hiatus_settings')
  const { mutation: reminderMut, saved: reminderSaved } = useSettingsMutation('/api/settings/reminder_settings')
  const { mutation: ntfyMut, saved: ntfySaved } = useSettingsMutation('/api/settings/ntfy_topic')

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

      {/* ntfy topic */}
      <form onSubmit={(e) => { e.preventDefault(); ntfyMut.mutate(new FormData(e.currentTarget)) }}>
        <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">
          ntfy topic
        </label>
        <p className="text-xs text-muted-foreground mb-2">
          Your ntfy.sh topic for push notifications. Leave blank to suppress.
        </p>
        <Input
          type="text"
          name="ntfy_topic"
          defaultValue={spamData?.ntfy_topic ?? ''}
          placeholder="my-topic-id"
        />
        <div className="flex items-center gap-2 mt-2">
          <SaveButton pending={ntfyMut.isPending} />
          <SaveOk visible={ntfySaved} />
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
                    className="flex-1 py-1 px-2 text-xs text-foreground bg-muted
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
              className="flex-1 py-1 px-2 text-xs text-foreground bg-muted
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
        <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">
          Hiatus mode
        </label>
        <p className="text-xs text-muted-foreground mb-2">
          Suppress notifications while you're actively chatting — no buzz if you just sent a message
          to that contact within the last N minutes.
        </p>
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
      <form onSubmit={(e) => { e.preventDefault(); reminderMut.mutate(new FormData(e.currentTarget)) }}>
        <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">
          Reminder timers
        </label>
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
        <div className="flex items-center gap-2 mt-2">
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
// Anti-spam section
// ---------------------------------------------------------------------------

function AntiSpamSection() {
  const { data } = useQuery<{ spam_whitelist_text: string }>({
    queryKey: ['settings-antispam'],
    queryFn: () =>
      fetch('/api/ui/settings/antispam', { credentials: 'same-origin' }).then((r) => r.json()),
    staleTime: 30_000,
  })

  const { mutation: spamMut, saved: spamSaved } = useSettingsMutation('/api/settings/spam_whitelist')

  if (!data) return <p className="text-xs text-muted-foreground">Loading…</p>

  return (
    <div className="space-y-5">
      <form onSubmit={(e) => { e.preventDefault(); spamMut.mutate(new FormData(e.currentTarget)) }}>
        <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">
          Broadcast-whitelist names
        </label>
        <p className="text-xs text-muted-foreground mb-2">
          Contact names or words stripped from messages before broadcast hashing.
          One entry per line. Prevents false positives for personalised greetings.
        </p>
        <Textarea
          name="spam_whitelist"
          rows={5}
          defaultValue={data.spam_whitelist_text}
          placeholder={"Alice\nBob\n+15551234567"}
          className="font-mono resize-y"
        />
        <div className="flex items-center gap-2 mt-2">
          <SaveButton pending={spamMut.isPending} />
          <SaveOk visible={spamSaved} />
        </div>
      </form>
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
          <p className="mt-1 text-xs text-[--warning]">
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
        {bindSaved && <span className="ml-2 text-xs text-[--success]">Saved</span>}
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
        {proxySaved && <span className="text-xs text-[--success] ml-7">Saved</span>}
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
            <span className="ml-2 text-xs text-[--warning]">(v{latest} available)</span>
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
                        Custom CSS
                      </p>
                      <CustomCssSection />
                    </div>
                  </div>
                </AccordionContent>
              </AccordionItem>

              <AccordionItem value="anti-spam">
                <AccordionTrigger className="px-5 py-4 font-medium text-sm text-foreground bg-muted hover:bg-accent hover:no-underline transition-colors">
                  <span className="flex items-center gap-2">
                    <ShieldIcon />
                    Anti-spam
                  </span>
                </AccordionTrigger>
                <AccordionContent className="px-5 py-4 bg-background text-sm text-foreground">
                  <AntiSpamSection />
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

              <AccordionItem value="about">
                <AccordionTrigger className="px-5 py-4 font-medium text-sm text-foreground bg-muted hover:bg-accent hover:no-underline transition-colors">
                  <span className="flex items-center gap-2">
                    <InfoIcon />
                    About
                  </span>
                </AccordionTrigger>
                <AccordionContent className="px-5 py-4 bg-background text-sm text-foreground">
                  <AboutSection />
                </AccordionContent>
              </AccordionItem>
            </Accordion>

            {/* Plugin slot: extra sections injected by installed plugins */}
            <SlotRenderer slot="settings.page" />
          </div>

          {/* Footer */}
          <div className="mt-4 flex items-center justify-center gap-3 text-xs text-muted-foreground max-w-2xl mx-auto">
            <a href="https://github.com/allenbina/chatwire/issues" target="_blank" rel="noopener"
               className="hover:text-foreground">Report a bug</a>
            <span>·</span>
            <a href="https://github.com/sponsors/allenbina" target="_blank" rel="noopener"
               className="hover:text-foreground">♥ Sponsor</a>
            <span>·</span>
            <a href="/logout" className="hover:text-foreground">Sign out</a>
          </div>
        </div>
      </div>
    </Layout>
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
function ShieldIcon() {
  return (
    <svg className="w-4 h-4 text-muted-foreground" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
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
function InfoIcon() {
  return (
    <svg className="w-4 h-4 text-muted-foreground" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
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
