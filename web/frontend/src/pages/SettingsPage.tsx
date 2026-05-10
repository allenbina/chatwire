/**
 * Settings page — full port of the Jinja2 _settings.html accordion UI.
 *
 * Phase 3: All settings sections are implemented here. Each section maps
 * directly to the corresponding accordion section in the Jinja2 template.
 * Settings are fetched from / persisted to the existing /api/settings/*
 * and /api/ui/* endpoints.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Layout } from '../components/Layout'
import { useTheme } from '../hooks/useTheme'
import { SlotRenderer } from '../plugins/SlotRenderer'

// ---------------------------------------------------------------------------
// Shared primitives
// ---------------------------------------------------------------------------

function AccordionSection({
  title,
  icon,
  children,
}: {
  title: string
  icon?: React.ReactNode
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border-b border-[--color-border] last:border-0">
      <button
        type="button"
        className="flex items-center justify-between w-full px-5 py-4 font-medium text-sm
                   text-[--color-text-primary] bg-[--color-bg-tertiary] hover:bg-[--color-sidebar-hover]
                   transition-colors gap-3"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="flex items-center gap-2">
          {icon}
          {title}
        </span>
        <svg
          className="w-3 h-3 shrink-0 transition-transform duration-200"
          style={{ transform: open ? 'rotate(180deg)' : '' }}
          fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 10 6"
        >
          <path d="M1 1 5 5 9 1" />
        </svg>
      </button>
      {open && (
        <div className="px-5 py-4 bg-[--color-bg-primary] text-sm text-[--color-text-primary]">
          {children}
        </div>
      )}
    </div>
  )
}

function SaveButton({ pending }: { pending?: boolean }) {
  return (
    <button
      type="submit"
      disabled={pending}
      className="px-4 py-2 text-sm font-medium text-[--color-bg-primary] bg-[--color-accent]
                 rounded-lg hover:bg-[--color-accent-hover] disabled:opacity-50 transition-colors"
    >
      {pending ? 'Saving…' : 'Save'}
    </button>
  )
}

function SaveOk({ visible }: { visible: boolean }) {
  if (!visible) return null
  return <span className="text-xs text-[--color-success]">Saved</span>
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

function ThemeSection() {
  const { current, setTheme, allThemes } = useTheme()
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
    <div className="flex flex-wrap gap-2">
      {allThemes.map((t) => {
        const isActive = t.name === current
        const swatch = t.colors.accent
        return (
          <button
            key={t.name}
            type="button"
            onClick={() => handleSelect(t.name)}
            disabled={applying}
            className={[
              'flex items-center gap-2 px-3 py-2 rounded-lg text-sm border transition-colors',
              isActive
                ? 'border-[--color-accent] bg-[--color-accent] text-[--color-bg-primary] font-semibold'
                : 'border-[--color-border] text-[--color-text-primary] hover:border-[--color-accent]',
            ].join(' ')}
          >
            <span
              className="w-3 h-3 rounded-full flex-shrink-0"
              style={{ background: swatch }}
              aria-hidden="true"
            />
            {t.label}
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
        <input
          list="wl-contact-names"
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="handle, contact, or [Group] name"
          required
          className="flex-1 py-2 px-3 text-sm text-[--color-text-primary] bg-[--color-bg-tertiary]
                     border border-[--color-border] rounded-lg focus:outline-none focus:border-[--color-accent]"
        />
        <datalist id="wl-contact-names">
          {contactNames.map((n) => <option key={n} value={n} />)}
        </datalist>
        <button
          type="submit"
          className="px-4 py-2 text-sm font-medium text-[--color-bg-primary] bg-[--color-accent]
                     rounded-lg hover:bg-[--color-accent-hover] transition-colors"
        >
          Add
        </button>
      </form>
      <p className="text-xs text-[--color-text-muted]">
        Phone (<code className="bg-[--color-bg-tertiary] px-1 rounded">+15551234567</code>), email, a
        Contacts name, or a named group chat.
      </p>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={handleSync}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium
                     text-[--color-text-primary] bg-[--color-bg-primary] border border-[--color-border]
                     rounded-lg hover:bg-[--color-sidebar-hover] transition-colors"
        >
          ↻ Sync contacts
        </button>
        {syncMsg && <span className="text-xs text-[--color-success]">{syncMsg}</span>}
        <button
          type="button"
          onClick={() => setShowList((v) => !v)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium
                     text-[--color-text-primary] bg-[--color-bg-primary] border border-[--color-border]
                     rounded-lg hover:bg-[--color-sidebar-hover] transition-colors"
        >
          {showList ? 'Hide contacts' : `Show contacts${rows.length ? ` (${rows.length})` : ''}`}
        </button>
      </div>
      {showList && rows.length > 0 && (
        <ul className="space-y-1 max-h-48 overflow-y-auto">
          {rows.map((r) => (
            <li key={r.value} className="flex items-center justify-between text-xs py-1
                                         border-b border-[--color-border] last:border-0">
              <span className="text-[--color-text-primary] font-mono">{r.label || r.value}</span>
              <button
                type="button"
                onClick={() => handleRemove(r.value)}
                className="text-[--color-error] hover:underline ml-2"
              >
                Remove
              </button>
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
          <li key={h} className="px-2 py-1 bg-[--color-bg-tertiary] rounded text-[--color-text-primary]">
            {h}
          </li>
        ))}
      </ul>
      <p className="text-xs text-[--color-text-muted]">
        Edit <code className="bg-[--color-bg-tertiary] px-1 rounded">SELF_HANDLES</code> in{' '}
        <code className="bg-[--color-bg-tertiary] px-1 rounded">~/.chatwire/config.json</code> and
        reload the agent to change.
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// API key section
// ---------------------------------------------------------------------------

function ApiKeySection() {
  const { data, refetch } = useQuery<{ api_key_hint: string }>({
    queryKey: ['settings-api-key'],
    queryFn: () =>
      fetch('/api/ui/settings/api_key', { credentials: 'same-origin' }).then((r) => r.json()),
    staleTime: 30_000,
  })
  const [revealed, setRevealed] = useState<string | null>(null)

  async function generate() {
    const r = await fetch('/api/settings/api_key/generate', { method: 'POST', credentials: 'same-origin' })
    if (r.ok) {
      const d = await r.json()
      setRevealed(d.key)
      refetch()
    }
  }

  async function revoke() {
    if (!confirm('Revoke the API key? Any integrations using it will stop working.')) return
    const r = await fetch('/api/settings/api_key/revoke', { method: 'POST', credentials: 'same-origin' })
    if (r.ok) {
      setRevealed(null)
      refetch()
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-[--color-text-muted]">
        REST API for programmatic access. Authenticate with{' '}
        <code className="bg-[--color-bg-tertiary] px-1 rounded">X-API-Key: &lt;key&gt;</code> on
        all <code className="bg-[--color-bg-tertiary] px-1 rounded">/api/v1/</code> requests.
      </p>
      <div>
        <p className="text-xs text-[--color-text-muted] mb-1">Current API key</p>
        <p className="text-sm font-mono text-[--color-text-primary] mb-3">
          {data?.api_key_hint ?? 'Not set'}
        </p>
        {revealed && (
          <div className="mb-3">
            <p className="text-xs text-[--color-text-muted] mb-1">
              New key — copy now, it will not be shown again
            </p>
            <input
              readOnly
              value={revealed}
              onClick={(e) => (e.target as HTMLInputElement).select()}
              className="w-full py-2 px-3 text-sm font-mono text-[--color-text-primary]
                         bg-[--color-bg-tertiary] border border-[--color-border] rounded-lg cursor-text"
            />
          </div>
        )}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={generate}
            className="px-4 py-2 text-sm font-medium text-[--color-bg-primary] bg-[--color-accent]
                       rounded-lg hover:bg-[--color-accent-hover] transition-colors"
          >
            Generate
          </button>
          {data?.api_key_hint && data.api_key_hint !== 'Not set' && (
            <button
              type="button"
              onClick={revoke}
              className="px-4 py-2 text-sm font-medium text-[--color-error] border border-[--color-error]
                         rounded-lg hover:bg-[--color-bg-tertiary] transition-colors"
            >
              Revoke
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Notifications section
// ---------------------------------------------------------------------------

function NotificationsSection() {
  const { data } = useQuery<{
    notification_detail: string
    hiatus_enabled: boolean
    hiatus_duration_minutes: number
    reminder_enabled: boolean
    reminder_days: number
  }>({
    queryKey: ['settings-notifications'],
    queryFn: () =>
      fetch('/api/ui/settings/notifications', { credentials: 'same-origin' }).then((r) => r.json()),
    staleTime: 30_000,
  })

  const { mutation: detailMut, saved: detailSaved } = useSettingsMutation('/api/settings/notification_detail')
  const { mutation: hiatusMut, saved: hiatusSaved } = useSettingsMutation('/api/settings/hiatus_settings')
  const { mutation: reminderMut, saved: reminderSaved } = useSettingsMutation('/api/settings/reminder_settings')

  if (!data) return <p className="text-xs text-[--color-text-muted]">Loading…</p>

  return (
    <div className="space-y-5">
      {/* Detail level */}
      <form onSubmit={(e) => { e.preventDefault(); detailMut.mutate(new FormData(e.currentTarget)) }}>
        <label className="block text-xs font-semibold text-[--color-text-muted] uppercase tracking-wider mb-1">
          Notification detail
        </label>
        <select
          name="notification_detail"
          defaultValue={data.notification_detail}
          className="w-full py-2 px-3 text-sm text-[--color-text-primary] bg-[--color-bg-tertiary]
                     border border-[--color-border] rounded-lg focus:outline-none focus:border-[--color-accent]"
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

      {/* Hiatus mode */}
      <form onSubmit={(e) => { e.preventDefault(); hiatusMut.mutate(new FormData(e.currentTarget)) }}>
        <label className="block text-xs font-semibold text-[--color-text-muted] uppercase tracking-wider mb-1">
          Hiatus mode
        </label>
        <p className="text-xs text-[--color-text-muted] mb-2">
          Suppress notifications while you're actively chatting — no buzz if you just sent a message
          to that contact within the last N minutes.
        </p>
        <label className="flex items-center gap-2 cursor-pointer text-sm mb-2">
          <input
            type="checkbox"
            name="hiatus_enabled"
            value="true"
            defaultChecked={data.hiatus_enabled}
            className="w-4 h-4 rounded border-[--color-border]"
          />
          Enable hiatus mode
        </label>
        <div className="flex items-center gap-2">
          <label htmlFor="hiatus-mins" className="text-xs text-[--color-text-muted] whitespace-nowrap">
            Silence window (minutes):
          </label>
          <input
            type="number"
            id="hiatus-mins"
            name="hiatus_duration_minutes"
            defaultValue={data.hiatus_duration_minutes}
            min={1}
            max={1440}
            className="w-20 py-1.5 px-2 text-sm text-[--color-text-primary] bg-[--color-bg-primary]
                       border border-[--color-border] rounded-lg focus:outline-none focus:border-[--color-accent]"
          />
        </div>
        <div className="flex items-center gap-2 mt-2">
          <SaveButton pending={hiatusMut.isPending} />
          <SaveOk visible={hiatusSaved} />
        </div>
      </form>

      {/* Reminder timers */}
      <form onSubmit={(e) => { e.preventDefault(); reminderMut.mutate(new FormData(e.currentTarget)) }}>
        <label className="block text-xs font-semibold text-[--color-text-muted] uppercase tracking-wider mb-1">
          Reminder timers
        </label>
        <p className="text-xs text-[--color-text-muted] mb-2">
          Push a daily reminder when you haven't heard from someone in N days.
        </p>
        <label className="flex items-center gap-2 cursor-pointer text-sm mb-2">
          <input
            type="checkbox"
            name="reminder_enabled"
            value="true"
            defaultChecked={data.reminder_enabled}
            className="w-4 h-4 rounded border-[--color-border]"
          />
          Enable reminders
        </label>
        <div className="flex items-center gap-2">
          <label htmlFor="reminder-days" className="text-xs text-[--color-text-muted] whitespace-nowrap">
            Remind after (days):
          </label>
          <input
            type="number"
            id="reminder-days"
            name="reminder_days"
            defaultValue={data.reminder_days}
            min={1}
            max={365}
            className="w-20 py-1.5 px-2 text-sm text-[--color-text-primary] bg-[--color-bg-primary]
                       border border-[--color-border] rounded-lg focus:outline-none focus:border-[--color-accent]"
          />
        </div>
        <div className="flex items-center gap-2 mt-2">
          <SaveButton pending={reminderMut.isPending} />
          <SaveOk visible={reminderSaved} />
        </div>
      </form>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Anti-spam section
// ---------------------------------------------------------------------------

function AntiSpamSection() {
  const { data } = useQuery<{ spam_whitelist_text: string; ntfy_topic: string }>({
    queryKey: ['settings-antispam'],
    queryFn: () =>
      fetch('/api/ui/settings/antispam', { credentials: 'same-origin' }).then((r) => r.json()),
    staleTime: 30_000,
  })

  const { mutation: spamMut, saved: spamSaved } = useSettingsMutation('/api/settings/spam_whitelist')
  const { mutation: ntfyMut, saved: ntfySaved } = useSettingsMutation('/api/settings/ntfy_topic')

  if (!data) return <p className="text-xs text-[--color-text-muted]">Loading…</p>

  return (
    <div className="space-y-5">
      <form onSubmit={(e) => { e.preventDefault(); spamMut.mutate(new FormData(e.currentTarget)) }}>
        <label className="block text-xs font-semibold text-[--color-text-muted] uppercase tracking-wider mb-1">
          Broadcast-whitelist names
        </label>
        <p className="text-xs text-[--color-text-muted] mb-2">
          Contact names or words stripped from messages before broadcast hashing.
          One entry per line. Prevents false positives for personalised greetings.
        </p>
        <textarea
          name="spam_whitelist"
          rows={5}
          defaultValue={data.spam_whitelist_text}
          placeholder={"Alice\nBob\n+15551234567"}
          className="w-full py-2 px-3 text-sm text-[--color-text-primary] bg-[--color-bg-tertiary]
                     border border-[--color-border] rounded-lg focus:outline-none focus:border-[--color-accent]
                     font-mono resize-y"
        />
        <div className="flex items-center gap-2 mt-2">
          <SaveButton pending={spamMut.isPending} />
          <SaveOk visible={spamSaved} />
        </div>
      </form>

      <form onSubmit={(e) => { e.preventDefault(); ntfyMut.mutate(new FormData(e.currentTarget)) }}>
        <label className="block text-xs font-semibold text-[--color-text-muted] uppercase tracking-wider mb-1">
          ntfy topic for spam alerts
        </label>
        <p className="text-xs text-[--color-text-muted] mb-2">
          Your ntfy.sh topic. Leave blank to suppress notifications.
        </p>
        <input
          type="text"
          name="ntfy_topic"
          defaultValue={data.ntfy_topic}
          placeholder="my-topic-id"
          className="w-full py-2 px-3 text-sm text-[--color-text-primary] bg-[--color-bg-tertiary]
                     border border-[--color-border] rounded-lg focus:outline-none focus:border-[--color-accent]"
        />
        <div className="flex items-center gap-2 mt-2">
          <SaveButton pending={ntfyMut.isPending} />
          <SaveOk visible={ntfySaved} />
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

  if (!data) return <p className="text-xs text-[--color-text-muted]">Loading…</p>

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
        <label htmlFor="web-port" className="block text-xs font-semibold text-[--color-text-muted] uppercase tracking-wider mb-1">
          Port
        </label>
        <input
          type="number"
          id="web-port"
          defaultValue={data.web_port}
          min={1024}
          max={65535}
          onBlur={(e) => savePort(e.target.value)}
          className="w-32 py-2 px-3 text-sm text-[--color-text-primary] bg-[--color-bg-primary]
                     border border-[--color-border] rounded-lg focus:outline-none focus:border-[--color-accent]"
        />
        {portSaved && (
          <p className="mt-1 text-xs text-[--color-warning]">
            Port change saved — restart chatwire web for it to take effect.
          </p>
        )}
      </div>

      {/* Listen on */}
      <div>
        <label className="block text-xs font-semibold text-[--color-text-muted] uppercase tracking-wider mb-1">
          Listen on
        </label>
        <select
          defaultValue={['127.0.0.1', 'localhost', '0.0.0.0'].includes(data.web_bind) ? data.web_bind : 'custom'}
          onChange={(e) => { if (e.target.value !== 'custom') saveBind(e.target.value) }}
          className="py-2 px-3 text-sm text-[--color-text-primary] bg-[--color-bg-primary]
                     border border-[--color-border] rounded-lg focus:outline-none focus:border-[--color-accent]"
        >
          <option value="127.0.0.1">localhost only</option>
          <option value="0.0.0.0">all interfaces</option>
          <option value="custom">custom…</option>
        </select>
        {bindSaved && <span className="ml-2 text-xs text-[--color-success]">Saved</span>}
      </div>

      {/* Reverse proxy */}
      <div>
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            defaultChecked={data.web_proxy_headers}
            onChange={(e) => saveProxy(e.target.checked)}
            className="w-4 h-4 rounded border-[--color-border]"
          />
          <span className="text-sm font-medium text-[--color-text-primary]">
            Trust reverse proxy headers
          </span>
        </label>
        <p className="mt-1 text-xs text-[--color-text-muted] ml-7">
          When enabled, chatwire trusts{' '}
          <code className="bg-[--color-bg-tertiary] px-1 rounded">X-Forwarded-For</code> and{' '}
          <code className="bg-[--color-bg-tertiary] px-1 rounded">X-Forwarded-Proto</code> headers
          from an upstream proxy. Do not enable if exposed directly to the internet.
        </p>
        {proxySaved && <span className="text-xs text-[--color-success] ml-7">Saved</span>}
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
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null)
  const [pending, setPending] = useState(false)

  const authEnabled = data?.auth_enabled ?? false

  function flash(text: string, ok: boolean) {
    setMsg({ text, ok })
    setTimeout(() => setMsg(null), 3000)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (newPw !== confirmPw) {
      flash('Passwords do not match.', false)
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
        flash(d.detail ?? 'Error.', false)
      } else {
        flash(authEnabled ? 'Password changed.' : 'Password set.', true)
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
        flash(d.detail ?? 'Error.', false)
      } else {
        flash('Password removed. Auth is now disabled.', true)
        setCurrentPw('')
        qc.invalidateQueries({ queryKey: ['settings-password-status'] })
      }
    } finally {
      setPending(false)
    }
  }

  const fieldClass =
    'w-full py-2 px-3 text-sm text-[--color-text-primary] bg-[--color-bg-tertiary] ' +
    'border border-[--color-border] rounded-lg focus:outline-none focus:border-[--color-accent]'

  return (
    <div className="space-y-4">
      <p className="text-xs text-[--color-text-muted]">
        {authEnabled
          ? 'A password is currently set. Enter your current password to change or remove it.'
          : 'No password is set — anyone with local network access can use the UI.'}
      </p>
      <form onSubmit={handleSubmit} className="space-y-3">
        {authEnabled && (
          <div>
            <label htmlFor="pw-current" className="block text-xs font-semibold text-[--color-text-muted] uppercase tracking-wider mb-1">
              Current password
            </label>
            <input
              id="pw-current"
              type="password"
              value={currentPw}
              onChange={(e) => setCurrentPw(e.target.value)}
              autoComplete="current-password"
              className={fieldClass}
            />
          </div>
        )}
        <div>
          <label htmlFor="pw-new" className="block text-xs font-semibold text-[--color-text-muted] uppercase tracking-wider mb-1">
            New password
          </label>
          <input
            id="pw-new"
            type="password"
            value={newPw}
            onChange={(e) => setNewPw(e.target.value)}
            autoComplete="new-password"
            minLength={6}
            required
            className={fieldClass}
          />
        </div>
        <div>
          <label htmlFor="pw-confirm" className="block text-xs font-semibold text-[--color-text-muted] uppercase tracking-wider mb-1">
            Confirm new password
          </label>
          <input
            id="pw-confirm"
            type="password"
            value={confirmPw}
            onChange={(e) => setConfirmPw(e.target.value)}
            autoComplete="new-password"
            minLength={6}
            required
            className={fieldClass}
          />
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <button
            type="submit"
            disabled={pending}
            className="px-4 py-2 text-sm font-medium text-[--color-bg-primary] bg-[--color-accent]
                       rounded-lg hover:bg-[--color-accent-hover] disabled:opacity-50 transition-colors"
          >
            {pending ? 'Saving…' : authEnabled ? 'Change password' : 'Set password'}
          </button>
          {authEnabled && (
            <button
              type="button"
              disabled={pending}
              onClick={handleClear}
              className="px-4 py-2 text-sm font-medium text-[--color-error] border border-[--color-error]
                         rounded-lg hover:bg-[--color-bg-tertiary] disabled:opacity-50 transition-colors"
            >
              Remove password
            </button>
          )}
          {msg && (
            <span className={`text-xs ${msg.ok ? 'text-[--color-success]' : 'text-[--color-error]'}`}>
              {msg.text}
            </span>
          )}
        </div>
      </form>
    </div>
  )
}

// ---------------------------------------------------------------------------
// About / version section
// ---------------------------------------------------------------------------

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
        <p className="text-sm font-semibold text-[--color-text-primary]">
          chatwire <span className="font-normal text-[--color-text-muted]">v{version}</span>
          {hasUpdate && (
            <span className="ml-2 text-xs text-[--color-warning]">(v{latest} available)</span>
          )}
        </p>
        <p className="text-xs text-[--color-text-muted] mt-0.5">
          Made by{' '}
          <a href="https://github.com/allenbina" target="_blank" rel="noopener"
             className="text-[--color-accent] hover:underline">Allen Bina</a>
        </p>
      </div>
      <p className="text-xs text-[--color-text-muted]">
        Released under the{' '}
        <a href="https://github.com/allenbina/chatwire/blob/main/LICENSE" target="_blank" rel="noopener"
           className="text-[--color-accent] hover:underline">MIT License</a>.
        {' '}Source on{' '}
        <a href="https://github.com/allenbina/chatwire" target="_blank" rel="noopener"
           className="text-[--color-accent] hover:underline">GitHub</a>.
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main SettingsPage
// ---------------------------------------------------------------------------

export function SettingsPage() {
  const navigate = useNavigate()

  return (
    <Layout>
      <div className="flex-1 overflow-y-auto bg-[--color-bg-primary]">
        {/* Header */}
        <header className="flex items-center gap-2 px-4 py-3 border-b border-[--color-border]
                           bg-[--color-bg-tertiary] flex-shrink-0">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="p-2 rounded-lg text-[--color-text-muted] hover:bg-[--color-sidebar-hover]
                       md:hidden transition-colors"
            aria-label="back to conversations"
          >
            ‹
          </button>
          <h2 className="text-sm font-semibold text-[--color-text-primary]">Settings</h2>
        </header>

        <div className="p-4">
          <div className="border border-[--color-border] rounded-lg overflow-hidden max-w-2xl mx-auto">
            <AccordionSection title="Self handles" icon={<UserIcon />}>
              <SelfHandlesSection />
            </AccordionSection>

            <AccordionSection title="Whitelist" icon={<ListIcon />}>
              <WhitelistSection />
            </AccordionSection>

            <AccordionSection title="Appearance" icon={<SunIcon />}>
              <ThemeSection />
            </AccordionSection>

            <AccordionSection title="Anti-spam" icon={<ShieldIcon />}>
              <AntiSpamSection />
            </AccordionSection>

            <AccordionSection title="Notifications" icon={<BellIcon />}>
              <NotificationsSection />
            </AccordionSection>

            <AccordionSection title="Advanced" icon={<SettingsIcon />}>
              <AdvancedSection />
            </AccordionSection>

            <AccordionSection title="API" icon={<CodeIcon />}>
              <ApiKeySection />
            </AccordionSection>

            <AccordionSection title="Password" icon={<LockIcon />}>
              <PasswordSection />
            </AccordionSection>

            <AccordionSection title="About" icon={<InfoIcon />}>
              <AboutSection />
            </AccordionSection>

            {/* Plugin slot: extra sections injected by installed plugins */}
            <SlotRenderer slot="settings.page" />
          </div>

          {/* Footer */}
          <div className="mt-4 flex items-center justify-center gap-3 text-xs text-[--color-text-muted] max-w-2xl mx-auto">
            <a href="https://github.com/allenbina/chatwire/issues" target="_blank" rel="noopener"
               className="hover:text-[--color-text-primary]">Report a bug</a>
            <span>·</span>
            <a href="https://github.com/sponsors/allenbina" target="_blank" rel="noopener"
               className="hover:text-[--color-text-primary]">♥ Sponsor</a>
            <span>·</span>
            <a href="/logout" className="hover:text-[--color-text-primary]">Sign out</a>
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
    <svg className="w-4 h-4 text-[--color-text-muted]" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
    </svg>
  )
}
function ListIcon() {
  return (
    <svg className="w-4 h-4 text-[--color-text-muted]" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2M9 5h6m-3 7v4m-2-2h4"/>
    </svg>
  )
}
function SunIcon() {
  return (
    <svg className="w-4 h-4 text-[--color-text-muted]" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
      <line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
    </svg>
  )
}
function ShieldIcon() {
  return (
    <svg className="w-4 h-4 text-[--color-text-muted]" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  )
}
function BellIcon() {
  return (
    <svg className="w-4 h-4 text-[--color-text-muted]" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>
    </svg>
  )
}
function SettingsIcon() {
  return (
    <svg className="w-4 h-4 text-[--color-text-muted]" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/>
    </svg>
  )
}
function CodeIcon() {
  return (
    <svg className="w-4 h-4 text-[--color-text-muted]" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 9l3 3-3 3m5 0h3"/><rect x="3" y="3" width="18" height="18" rx="2"/>
    </svg>
  )
}
function InfoIcon() {
  return (
    <svg className="w-4 h-4 text-[--color-text-muted]" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
    </svg>
  )
}
function LockIcon() {
  return (
    <svg className="w-4 h-4 text-[--color-text-muted]" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
    </svg>
  )
}
