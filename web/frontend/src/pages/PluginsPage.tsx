/**
 * Plugin management page — Phase 19 Chunk 2.
 *
 * Installed section: accordion list with tier badges, health dots,
 * inline settings form generated from SETTINGS_SCHEMA, and enable/disable.
 * Marketplace section: Chunk 3.
 *
 * Route: /plugins  (lazy-loaded from App.tsx)
 */
import { useState, useEffect, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { Layout } from '../components/Layout'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type PluginStatus = 'healthy' | 'degraded' | 'failing'
type PluginTier = 'core' | 'official' | 'ui'

interface PluginHealth {
  last_run: string | null
  last_success: string | null
  last_error: string | null
  errors_24h: number
  total_runs: number
  status: PluginStatus
}

interface SchemaProperty {
  type?: string
  title?: string
  description?: string
  default?: unknown
  enum?: string[]
  format?: string
  'x-ui-type'?: string
  'x-ui-placeholder'?: string
  minimum?: number
  maximum?: number
}

interface JsonSchema {
  type?: string
  properties?: Record<string, SchemaProperty>
  required?: string[]
}

interface Plugin {
  name: string
  display_name: string
  description: string
  icon: string | null
  tier: PluginTier
  version: string | null
  min_sdk: string | null
  max_sdk: string | null
  tags: string[]
  settings_schema: JsonSchema | Record<string, never>
  enabled: boolean
  health: PluginHealth
  needs_config: boolean
  dist_name: string | null
  sdk_compat: boolean
  sdk_warning: string | null
}

interface PluginUpdate {
  name: string
  dist_name: string
  current_version: string
  latest_version: string
}

interface RegistryPlugin {
  name: string
  pypi: string
  description: string
  author: string
  signed: boolean
  homepage: string
  icon: string | null
  tags?: string[]
  deprecated?: boolean
}

// ---------------------------------------------------------------------------
// Tier metadata
// ---------------------------------------------------------------------------

const TIER_META: Record<PluginTier, { label: string; badge: string; info: string }> = {
  core: {
    label: 'core',
    badge: 'bg-muted text-muted-foreground',
    info: 'Built-in system component',
  },
  official: {
    label: 'official',
    badge: 'bg-blue-500/10 text-blue-400',
    info: 'Reviewed & signed — message forwarding',
  },
  ui: {
    label: 'ui',
    badge: 'bg-green-500/10 text-green-400',
    info: 'No data access — CSS, themes, and UI widgets only',
  },
}

const TIER_ICON: Record<PluginTier, string> = {
  core: '⚙️',
  official: '🔵',
  ui: '🟢',
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function TierBadge({ tier }: { tier: PluginTier }) {
  const m = TIER_META[tier] ?? TIER_META.core
  return (
    <span
      className={cn('inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded font-mono', m.badge)}
      title={m.info}
    >
      <span aria-hidden="true">{TIER_ICON[tier] ?? '⚙️'}</span>
      {m.label}
    </span>
  )
}

function HealthDot({ status }: { status: PluginStatus }) {
  const color =
    status === 'healthy' ? 'bg-green-500' :
    status === 'degraded' ? 'bg-yellow-500' :
    'bg-red-500'
  const label =
    status === 'healthy' ? 'Healthy' :
    status === 'degraded' ? 'Degraded' :
    'Failing'
  return (
    <span
      className={cn('inline-block w-2 h-2 rounded-full flex-shrink-0', color)}
      title={label}
      aria-label={label}
    />
  )
}

function PluginIcon({ icon, name }: { icon: string | null; name: string }) {
  if (icon) {
    // If it's an emoji or short string, render as text
    if (icon.length <= 4) {
      return <span className="text-xl" aria-hidden="true">{icon}</span>
    }
    // Otherwise it might be a lucide icon name — show first letter fallback
  }
  return (
    <span
      className="inline-flex items-center justify-center w-8 h-8 rounded-lg bg-muted text-muted-foreground text-sm font-semibold flex-shrink-0"
      aria-hidden="true"
    >
      {name.charAt(0).toUpperCase()}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Consent dialog
// ---------------------------------------------------------------------------

function ConsentDialog({
  plugin,
  onConfirm,
  onCancel,
}: {
  plugin: Plugin
  onConfirm: () => void
  onCancel: () => void
}) {
  if (plugin.tier === 'official') {
    return (
      <Dialog open onOpenChange={(open) => { if (!open) onCancel() }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Enable {plugin.display_name}?</DialogTitle>
            <DialogDescription>
              This plugin can read your message content and send messages on
              your behalf. It has been reviewed and signed by the chatwire team.
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
  // ui or core tier: no consent needed
  onConfirm()
  return null
}

// ---------------------------------------------------------------------------
// JSON Schema form renderer
// ---------------------------------------------------------------------------

function SchemaForm({
  schema,
  config,
  onChange,
}: {
  schema: JsonSchema
  config: Record<string, unknown>
  onChange: (key: string, value: unknown) => void
}) {
  const props = schema.properties ?? {}
  const required = schema.required ?? []
  const entries = Object.entries(props)

  if (entries.length === 0) {
    return <p className="text-xs text-muted-foreground">No configurable settings.</p>
  }

  return (
    <div className="space-y-3">
      {entries.map(([key, def]) => {
        const isRequired = required.includes(key)
        const label = def.title ?? key
        const hint = def.description
        const uiType = def['x-ui-type']
        const placeholder = def['x-ui-placeholder'] ?? ''
        const value = config[key]

        return (
          <div key={key} className="space-y-1">
            <label className="text-xs font-medium text-foreground flex items-center gap-1">
              {label}
              {isRequired && <span className="text-destructive" aria-label="required">*</span>}
            </label>
            {hint && <p className="text-[11px] text-muted-foreground break-words">{hint}</p>}

            {def.type === 'boolean' ? (
              <button
                type="button"
                role="switch"
                aria-checked={!!value}
                aria-label={`Toggle ${label}`}
                onClick={() => onChange(key, !value)}
                className={cn(
                  'flex-shrink-0 w-8 h-4 rounded-full transition-colors',
                  value ? 'bg-primary' : 'bg-border',
                )}
              >
                <span
                  className={cn(
                    'block w-3 h-3 rounded-full bg-white transition-transform mx-0.5',
                    value ? 'translate-x-4' : 'translate-x-0',
                  )}
                />
              </button>
            ) : def.enum ? (
              <select
                value={String(value ?? def.default ?? '')}
                onChange={(e) => onChange(key, e.target.value)}
                className="w-full text-xs px-2 py-1.5 border border-border rounded bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              >
                {def.enum.map((opt) => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
            ) : uiType === 'textarea' ? (
              <Textarea
                value={String(value ?? '')}
                onChange={(e) => onChange(key, e.target.value)}
                placeholder={placeholder}
                className="text-xs resize-y min-h-[80px]"
                rows={4}
              />
            ) : def.type === 'number' || def.type === 'integer' ? (
              <Input
                type="number"
                value={String(value ?? def.default ?? '')}
                min={def.minimum}
                max={def.maximum}
                onChange={(e) => onChange(key, e.target.valueAsNumber)}
                className="text-xs"
              />
            ) : (
              <Input
                type={
                  uiType === 'password' || def.format === 'password'
                    ? 'password'
                    : 'text'
                }
                value={String(value ?? '')}
                onChange={(e) => onChange(key, e.target.value)}
                placeholder={placeholder}
                className="text-xs"
              />
            )}
          </div>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Per-plugin accordion row
// ---------------------------------------------------------------------------

function PluginRow({
  plugin,
  update,
  onToggle,
  onRemove,
  onUpdate,
}: {
  plugin: Plugin
  update?: PluginUpdate
  onToggle: (p: Plugin, enabled: boolean) => void
  onRemove: (p: Plugin) => void
  onUpdate: (p: Plugin, u: PluginUpdate) => void
}) {
  const queryClient = useQueryClient()

  // Load plugin config when row is expanded
  const { data: configData, isLoading: configLoading } = useQuery<{ config: Record<string, unknown> }>({
    queryKey: ['plugin-config', plugin.name],
    queryFn: () =>
      fetch(`/api/ui/plugins/${plugin.name}/config`, { credentials: 'same-origin' })
        .then((r) => r.json()),
    staleTime: 30_000,
  })

  const [localConfig, setLocalConfig] = useState<Record<string, unknown> | null>(null)
  const effectiveConfig = localConfig ?? configData?.config ?? {}

  const handleFieldChange = useCallback((key: string, value: unknown) => {
    setLocalConfig((prev) => ({ ...(prev ?? configData?.config ?? {}), [key]: value }))
  }, [configData?.config])

  const saveMutation = useMutation({
    mutationFn: (config: Record<string, unknown>) =>
      fetch(`/api/ui/plugins/${plugin.name}/config`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config }),
      }).then((r) => {
        if (!r.ok) throw new Error(`${r.status}`)
        return r.json()
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['plugin-config', plugin.name] })
      queryClient.invalidateQueries({ queryKey: ['plugins'] })
      setLocalConfig(null)
      toast.success(`${plugin.display_name} settings saved.`)
    },
    onError: () => toast.error('Failed to save plugin settings.'),
  })

  const hasSchema =
    typeof plugin.settings_schema === 'object' &&
    plugin.settings_schema !== null &&
    'properties' in plugin.settings_schema &&
    Object.keys((plugin.settings_schema as JsonSchema).properties ?? {}).length > 0

  const health = plugin.health

  return (
    <AccordionItem value={plugin.name} className="border-b border-border last:border-0">
      <AccordionTrigger className="py-3 hover:no-underline [&>svg]:ml-2">
        <div className="flex items-center gap-3 flex-1 min-w-0 text-left">
          {/* Icon */}
          <PluginIcon icon={plugin.icon} name={plugin.name} />

          {/* Info */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-medium text-foreground">{plugin.display_name}</span>
              <TierBadge tier={plugin.tier} />
              {plugin.version && (
                <span className="text-[10px] text-muted-foreground">v{plugin.version}</span>
              )}
              {plugin.needs_config && (
                <span className="text-[10px] text-yellow-500" title="Setup required">⚠️</span>
              )}
              {!plugin.sdk_compat && plugin.sdk_warning && (
                <span
                  className="text-[10px] text-orange-500 font-mono"
                  title={plugin.sdk_warning}
                >
                  ⚠ SDK
                </span>
              )}
              {update && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    onUpdate(plugin, update)
                  }}
                  className="inline-flex items-center gap-0.5 text-[10px] text-blue-400 hover:text-blue-300 font-mono bg-blue-500/10 px-1.5 py-0.5 rounded transition-colors"
                  title={`Update to v${update.latest_version}`}
                >
                  ↑ v{update.latest_version}
                </button>
              )}
            </div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <HealthDot status={health.status} />
              <span className="text-[11px] text-muted-foreground truncate">
                {health.status === 'healthy' ? (
                  health.total_runs > 0 ? '✓ Running' : 'Not yet run'
                ) : health.status === 'degraded' ? (
                  `⚠ ${health.errors_24h} error${health.errors_24h !== 1 ? 's' : ''} today`
                ) : (
                  `✗ Failing${health.last_error ? `: ${health.last_error.slice(0, 40)}` : ''}`
                )}
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground mt-0.5 truncate">{plugin.description}</p>
          </div>

          {/* Enable/disable toggle */}
          {plugin.tier !== 'core' && (
            <button
              type="button"
              role="switch"
              aria-checked={plugin.enabled}
              aria-label={`${plugin.enabled ? 'Disable' : 'Enable'} ${plugin.display_name}`}
              onClick={(e) => {
                e.stopPropagation()
                onToggle(plugin, !plugin.enabled)
              }}
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
          )}
        </div>
      </AccordionTrigger>

      <AccordionContent className="pb-4">
        <div className="pl-11 space-y-4">
          {/* Health details */}
          {health.total_runs > 0 && (
            <div className="text-[11px] text-muted-foreground space-y-0.5">
              <p>Total runs: {health.total_runs.toLocaleString()}</p>
              {health.last_run && <p>Last run: {new Date(health.last_run).toLocaleString()}</p>}
              {health.last_error && (
                <p className="text-yellow-500">Last error: {health.last_error}</p>
              )}
            </div>
          )}

          {/* Settings form */}
          {hasSchema && (
            <div className="space-y-3">
              <h4 className="text-xs font-semibold text-foreground">Settings</h4>
              {configLoading ? (
                <p className="text-xs text-muted-foreground animate-pulse">Loading…</p>
              ) : (
                <>
                  <SchemaForm
                    schema={plugin.settings_schema as JsonSchema}
                    config={effectiveConfig}
                    onChange={handleFieldChange}
                  />
                  <Button
                    size="sm"
                    disabled={saveMutation.isPending || localConfig === null}
                    onClick={() => saveMutation.mutate(effectiveConfig)}
                  >
                    {saveMutation.isPending ? 'Saving…' : 'Save'}
                  </Button>
                </>
              )}
            </div>
          )}

          {!hasSchema && (
            <p className="text-xs text-muted-foreground italic">
              No configurable settings for this plugin.
            </p>
          )}

          {/* Remove button — only for pip-installed plugins */}
          {plugin.dist_name && (
            <div className="pt-2 border-t border-border">
              <Button
                size="sm"
                variant="outline"
                className="text-destructive border-destructive hover:bg-muted text-xs"
                onClick={() => onRemove(plugin)}
              >
                Remove plugin
              </Button>
            </div>
          )}
        </div>
      </AccordionContent>
    </AccordionItem>
  )
}

// ---------------------------------------------------------------------------
// Install progress overlay
// ---------------------------------------------------------------------------

function InstallOverlay({
  packageName,
  upgradeMode = false,
  onClose,
}: {
  packageName: string
  upgradeMode?: boolean
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  type Step = { label: string; done: boolean; error?: string }
  const [steps, setSteps] = useState<Step[]>([
    { label: 'Downloading package…', done: false },
    { label: 'Verifying signature…', done: false },
    { label: 'Registering plugin…', done: false },
  ])
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  // Run install on mount (or when packageName changes)
  useEffect(() => {
    fetch('/api/ui/plugins/install', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ package_name: packageName, upgrade: upgradeMode }),
    })
      .then(async (r) => {
        const data = await r.json()
        if (!r.ok) throw new Error(data.detail ?? `${r.status}`)
        setSteps([
          { label: 'Package downloaded', done: true },
          { label: data.signed ? 'Signature verified ✓' : 'Unsigned (community plugin)', done: true },
          { label: 'Plugin registered', done: true },
        ])
        setDone(true)
        queryClient.invalidateQueries({ queryKey: ['plugins'] })
        queryClient.invalidateQueries({ queryKey: ['plugin-updates'] })
        // Theme plugins register CSS via a separate entry-point group — notify
        // the theme hook to re-fetch plugin-themes so the picker updates immediately.
        window.dispatchEvent(new CustomEvent('chatwire-plugin-themes-changed'))
      })
      .catch((e) => {
        setError(e.message ?? 'Install failed')
        setSteps((prev) => prev.map((s) => (s.done ? s : { ...s, error: 'failed' })))
      })
  }, [packageName]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Dialog open onOpenChange={() => (done || error) && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{upgradeMode ? 'Updating' : 'Installing'} {packageName}</DialogTitle>
          <DialogDescription>Please wait while the plugin is {upgradeMode ? 'updated' : 'installed'}.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2 px-6 py-2">
          {steps.map((step, i) => (
            <div key={i} className="flex items-center gap-2 text-sm">
              <span className={step.done ? 'text-green-500' : step.error ? 'text-destructive' : 'text-muted-foreground'}>
                {step.done ? '✓' : step.error ? '✗' : '○'}
              </span>
              <span className={step.done ? 'text-foreground' : 'text-muted-foreground'}>{step.label}</span>
            </div>
          ))}
          {error && <p className="text-xs text-destructive mt-2">{error}</p>}
        </div>
        <DialogFooter>
          {(done || error) && (
            <Button size="sm" onClick={onClose}>{done ? 'Done' : 'Close'}</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Remove confirm dialog
// ---------------------------------------------------------------------------

function RemoveDialog({
  plugin,
  onConfirm,
  onCancel,
}: {
  plugin: Plugin
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <Dialog open onOpenChange={(open) => { if (!open) onCancel() }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Remove {plugin.display_name}?</DialogTitle>
          <DialogDescription>
            This will uninstall the plugin package and delete its settings and
            health data. This action cannot be undone.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" size="sm" onClick={onCancel}>Cancel</Button>
          <Button
            size="sm"
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            onClick={onConfirm}
          >
            Remove
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}


// ---------------------------------------------------------------------------
// Marketplace section
// ---------------------------------------------------------------------------

const ALL_TAGS = ['action', 'theme', 'color', 'ui', 'bridge', 'official']

function MarketplaceSection({ installedNames }: { installedNames: Set<string> }) {
  const [search, setSearch] = useState('')
  const [activeTag, setActiveTag] = useState<string | null>(null)
  const [installing, setInstalling] = useState<string | null>(null)

  const { data, isLoading, isError } = useQuery<{ plugins: RegistryPlugin[] }>({
    queryKey: ['plugins-marketplace'],
    queryFn: () =>
      fetch('/api/ui/plugins/marketplace', { credentials: 'same-origin' }).then((r) => r.json()),
    staleTime: 10 * 60_000,
  })

  const registry = data?.plugins ?? []

  const filtered = registry.filter((p) => {
    // Exclude deprecated plugins and already-installed plugins.
    if (p.deprecated) return false
    if (installedNames.has(p.pypi) || installedNames.has(p.name)) return false
    const matchSearch =
      !search ||
      p.name.toLowerCase().includes(search.toLowerCase()) ||
      p.description.toLowerCase().includes(search.toLowerCase())
    const matchTag = !activeTag || (p.tags ?? []).includes(activeTag)
    return matchSearch && matchTag
  })

  return (
    <section>
      <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
        Browse Marketplace
      </h2>

      {/* Search + tag filters */}
      <div className="space-y-2 mb-4">
        <Input
          type="search"
          placeholder="Search plugins…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="text-xs"
        />
        <div className="flex flex-wrap gap-1">
          <button
            onClick={() => setActiveTag(null)}
            className={cn(
              'text-[11px] px-2 py-0.5 rounded-full border transition-colors',
              activeTag === null
                ? 'bg-primary text-primary-foreground border-primary'
                : 'border-border text-muted-foreground hover:border-primary hover:text-primary',
            )}
          >
            All
          </button>
          {ALL_TAGS.map((tag) => (
            <button
              key={tag}
              onClick={() => setActiveTag(tag === activeTag ? null : tag)}
              className={cn(
                'text-[11px] px-2 py-0.5 rounded-full border transition-colors',
                activeTag === tag
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'border-border text-muted-foreground hover:border-primary hover:text-primary',
              )}
            >
              {tag}
            </button>
          ))}
        </div>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground animate-pulse">Loading marketplace…</p>}
      {isError && <p className="text-sm text-destructive">Failed to load marketplace.</p>}
      {!isLoading && !isError && filtered.length === 0 && (
        <p className="text-sm text-muted-foreground">No plugins found.</p>
      )}

      {!isLoading && !isError && filtered.length > 0 && (
        <div className="space-y-2">
          {filtered.map((pkg) => {
            const isInstalled = installedNames.has(pkg.pypi) || installedNames.has(pkg.name)
            return (
              <div
                key={pkg.pypi}
                className="flex items-start gap-3 py-2 border-b border-border last:border-0"
              >
                <span className="text-xl flex-shrink-0" aria-hidden="true">
                  {pkg.icon || '🔌'}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-foreground">{pkg.name}</span>
                    {!pkg.signed && (
                      <span className="text-[10px] text-yellow-500 font-mono">unsigned</span>
                    )}
                    {(pkg.tags ?? []).map((tag) => (
                      <span key={tag} className="text-[10px] text-muted-foreground font-mono bg-muted px-1 rounded">
                        {tag}
                      </span>
                    ))}
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5 break-words">{pkg.description}</p>
                  <p className="text-[10px] text-muted-foreground mt-0.5 break-words">by {pkg.author}</p>
                </div>
                <div className="flex-shrink-0">
                  {isInstalled ? (
                    <span className="text-xs text-green-500">Installed ✓</span>
                  ) : (
                    <Button
                      size="sm"
                      variant="outline"
                      className="text-xs"
                      onClick={() => setInstalling(pkg.pypi)}
                    >
                      Install
                    </Button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {installing && (
        <InstallOverlay
          packageName={installing}
          onClose={() => setInstalling(null)}
        />
      )}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function PluginsPage() {
  const queryClient = useQueryClient()
  const [consentFor, setConsentFor] = useState<Plugin | null>(null)
  const [pendingToggle, setPendingToggle] = useState<boolean | null>(null)
  const [removeFor, setRemoveFor] = useState<Plugin | null>(null)
  const [updateFor, setUpdateFor] = useState<{ plugin: Plugin; update: PluginUpdate } | null>(null)
  const [installedFilter, setInstalledFilter] = useState<'all' | 'theme'>('all')

  const { data, isLoading, isError } = useQuery<{ plugins: Plugin[] }>({
    queryKey: ['plugins'],
    queryFn: () =>
      fetch('/api/ui/plugins', { credentials: 'same-origin' }).then((r) => r.json()),
    staleTime: 30_000,
  })

  const { data: updatesData } = useQuery<{ updates: PluginUpdate[] }>({
    queryKey: ['plugin-updates'],
    queryFn: () =>
      fetch('/api/ui/plugins/updates', { credentials: 'same-origin' }).then((r) => r.json()),
    staleTime: 60 * 60_000, // 1 hour — server caches for 24h anyway
  })

  const updateMap = new Map<string, PluginUpdate>(
    (updatesData?.updates ?? []).map((u) => [u.name, u])
  )

  const plugins = data?.plugins ?? []
  const filteredPlugins =
    installedFilter === 'theme'
      ? plugins.filter((p) => p.tags.includes('theme'))
      : plugins
  const installedNames = new Set(plugins.flatMap((p) => [p.name, p.dist_name ?? ''].filter(Boolean)))

  const enableMutation = useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      fetch(`/api/ui/plugins/${name}/${enabled ? 'enable' : 'disable'}`, {
        method: 'POST',
        credentials: 'same-origin',
      }).then((r) => {
        if (!r.ok) throw new Error(`${r.status}`)
        return r.json()
      }),
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ['plugins'] })
      toast.success(`Plugin ${vars.enabled ? 'enabled' : 'disabled'}.`)
    },
    onError: () => toast.error('Failed to update plugin state.'),
  })

  const removeMutation = useMutation({
    mutationFn: ({ name, dist_name }: { name: string; dist_name: string }) =>
      fetch(`/api/ui/plugins/${name}?dist_name=${encodeURIComponent(dist_name)}`, {
        method: 'DELETE',
        credentials: 'same-origin',
      }).then((r) => {
        if (!r.ok) throw new Error(`${r.status}`)
        return r.json()
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['plugins'] })
      // If a theme plugin was removed, refresh the theme picker immediately.
      window.dispatchEvent(new CustomEvent('chatwire-plugin-themes-changed'))
      toast.success('Plugin removed.')
      setRemoveFor(null)
    },
    onError: () => {
      toast.error('Failed to remove plugin.')
      setRemoveFor(null)
    },
  })

  function handleToggle(plugin: Plugin, targetEnabled: boolean) {
    if (targetEnabled && plugin.tier === 'official') {
      setConsentFor(plugin)
      setPendingToggle(targetEnabled)
    } else {
      enableMutation.mutate({ name: plugin.name, enabled: targetEnabled })
    }
  }

  function handleRemove(plugin: Plugin) {
    setRemoveFor(plugin)
  }

  function handleUpdate(plugin: Plugin, update: PluginUpdate) {
    setUpdateFor({ plugin, update })
  }

  return (
    <Layout>
      <div className="flex flex-col h-full">
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border bg-background flex-shrink-0">
          <Link
            to="/"
            className="text-xs text-muted-foreground hover:text-foreground transition-colors md:hidden"
            aria-label="Back"
          >
            ← Back
          </Link>
          <h1 className="text-sm font-semibold text-foreground">Plugins</h1>
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-2xl mx-auto px-4 py-6 space-y-8">

            {/* Installed section */}
            <section>
              <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
                Installed
              </h2>

              {/* Filter tabs */}
              <div className="flex gap-1 mb-3" role="tablist" aria-label="Filter installed plugins">
                {(['all', 'theme'] as const).map((f) => (
                  <button
                    key={f}
                    role="tab"
                    aria-selected={installedFilter === f}
                    onClick={() => setInstalledFilter(f)}
                    className={cn(
                      'text-[11px] px-2 py-0.5 rounded-full border transition-colors',
                      installedFilter === f
                        ? 'bg-primary text-primary-foreground border-primary'
                        : 'border-border text-muted-foreground hover:border-primary hover:text-primary',
                    )}
                  >
                    {f === 'all' ? 'All' : 'Themes'}
                  </button>
                ))}
              </div>

              {isLoading && (
                <p className="text-sm text-muted-foreground animate-pulse">Loading plugins…</p>
              )}
              {isError && (
                <p className="text-sm text-destructive">Failed to load plugins.</p>
              )}
              {!isLoading && !isError && plugins.length === 0 && (
                <p className="text-sm text-muted-foreground">No plugins installed.</p>
              )}
              {!isLoading && !isError && plugins.length > 0 && filteredPlugins.length === 0 && (
                <p className="text-sm text-muted-foreground">No theme plugins installed.</p>
              )}

              {!isLoading && !isError && filteredPlugins.length > 0 && (
                <Accordion type="multiple" className="w-full">
                  {filteredPlugins.map((plugin) => (
                    <PluginRow
                      key={plugin.name}
                      plugin={plugin}
                      update={updateMap.get(plugin.name)}
                      onToggle={handleToggle}
                      onRemove={handleRemove}
                      onUpdate={handleUpdate}
                    />
                  ))}
                </Accordion>
              )}
            </section>


            {/* Marketplace section */}
            <MarketplaceSection installedNames={installedNames} />
          </div>
        </div>
      </div>

      {/* Consent dialog */}
      {consentFor && pendingToggle !== null && (
        <ConsentDialog
          plugin={consentFor}
          onConfirm={() => {
            enableMutation.mutate({ name: consentFor.name, enabled: pendingToggle })
            setConsentFor(null)
            setPendingToggle(null)
          }}
          onCancel={() => {
            setConsentFor(null)
            setPendingToggle(null)
          }}
        />
      )}

      {/* Remove confirm dialog */}
      {removeFor && (
        <RemoveDialog
          plugin={removeFor}
          onConfirm={() => {
            if (removeFor.dist_name) {
              removeMutation.mutate({ name: removeFor.name, dist_name: removeFor.dist_name })
            }
          }}
          onCancel={() => setRemoveFor(null)}
        />
      )}

      {/* Update overlay */}
      {updateFor && (
        <InstallOverlay
          packageName={updateFor.update.dist_name}
          upgradeMode
          onClose={() => setUpdateFor(null)}
        />
      )}
    </Layout>
  )
}
