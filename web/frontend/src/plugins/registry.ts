/**
 * Chatwire plugin slot registry.
 *
 * Slots are named extension points in the React UI where plugins can inject
 * additional React components. Four named slots are pre-defined:
 *
 *   message.toolbar   — rendered after the timestamp in each MessageBubble
 *   sidebar.panel     — rendered below the conversation list in the sidebar
 *   settings.page     — rendered as an extra accordion section in SettingsPage
 *   compose.extension — rendered above the textarea in ComposeBox
 *
 * Plugin bundles (loaded via <script> tags) call the global API:
 *
 *   window.chatwire.registerSlot('sidebar.panel', MyWidget, { title: 'Stats' })
 *
 * The React app calls getSlots(slotName) to retrieve all registered components
 * and renders them via <SlotRenderer slot="sidebar.panel" />.
 *
 * This module also exposes the registry on window.chatwire so plugin scripts
 * loaded after the app boots can call it immediately.
 */
import type { ComponentType } from 'react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type SlotName =
  | 'message.toolbar'
  | 'sidebar.panel'
  | 'settings.page'
  | 'compose.extension'

/**
 * Security tier for plugin registrations.
 *
 * - `core`     — Built-in system component. Renders directly in the React tree.
 * - `official` — Reviewed + signed by project maintainer. Renders directly.
 * - `notify`   — Third-party notification plugin. Rendered inside a sandboxed iframe.
 * - `ui`       — Third-party UI/theme plugin. Rendered inside a sandboxed iframe.
 */
export type PluginTier = 'core' | 'official' | 'notify' | 'ui'

export interface SlotRegistration {
  /** A unique key for this registration (defaults to component.displayName). */
  key: string
  /** The React component to render in the slot (used for core/official tiers). */
  component: ComponentType<SlotProps>
  /** Arbitrary props passed through to the component at render time. */
  props?: Record<string, unknown>
  /**
   * Security tier. Determines the rendering path:
   * - `core` / `official` → render directly in the host React tree (trusted).
   * - `notify` / `ui`     → render via PluginFrame (sandboxed iframe, no DOM access).
   *
   * Defaults to `'core'` for backward compatibility.
   */
  tier: PluginTier
  /**
   * For sandboxed (notify/ui) plugins: URL of the JS bundle to load inside
   * the iframe. When provided alongside tier='ui'|'notify', SlotRenderer
   * will use PluginFrame instead of rendering the component directly.
   */
  src?: string
}

/** Props that every slot component receives from <SlotRenderer>. */
export interface SlotProps {
  /** The slot this component is registered in. */
  slot: SlotName
  /** Any extra props the caller passed to <SlotRenderer>. */
  [key: string]: unknown
}

// ---------------------------------------------------------------------------
// Internal registry state
// ---------------------------------------------------------------------------

const _slots: Map<SlotName, SlotRegistration[]> = new Map()
let _keyCounter = 0

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Register a React component in a named slot.
 *
 * @param slot      - One of the four slot names.
 * @param component - React component (function or class).
 * @param options   - Optional `key` override and/or extra `props` to forward.
 *
 * @example
 * ```ts
 * import { registerSlot } from './plugins/registry'
 * registerSlot('sidebar.panel', StatsWidget, { title: 'Message Stats' })
 * ```
 */
export function registerSlot(
  slot: SlotName,
  component: ComponentType<SlotProps>,
  options: {
    key?: string
    props?: Record<string, unknown>
    /**
     * Security tier for this registration.
     * Defaults to `'core'`. Third-party plugins should set `'notify'` or `'ui'`.
     */
    tier?: PluginTier
    /**
     * URL of the JS bundle for sandboxed (notify/ui) plugins.
     * When set, SlotRenderer renders via PluginFrame instead of the component.
     */
    src?: string
  } = {},
): void {
  const key = options.key ?? component.displayName ?? component.name ?? `slot-${++_keyCounter}`
  const existing = _slots.get(slot) ?? []
  // Deduplicate by key — re-registering replaces the old entry.
  const filtered = existing.filter((r) => r.key !== key)
  _slots.set(slot, [
    ...filtered,
    { key, component, props: options.props, tier: options.tier ?? 'core', src: options.src },
  ])
}

/**
 * Retrieve all registrations for a slot, in registration order.
 *
 * Returns an empty array if nothing has been registered for the slot.
 */
export function getSlots(slot: SlotName): SlotRegistration[] {
  return _slots.get(slot) ?? []
}

/**
 * Remove all registrations for a slot (or all slots if called without args).
 * Primarily useful in tests.
 */
export function clearSlots(slot?: SlotName): void {
  if (slot === undefined) {
    _slots.clear()
  } else {
    _slots.delete(slot)
  }
}

// ---------------------------------------------------------------------------
// Global window.chatwire exposure
// ---------------------------------------------------------------------------

/**
 * The public API surface exposed on `window.chatwire`.
 * Plugin scripts loaded via <script> tags call this after the app boots.
 */
export const chatwire = {
  registerSlot,
  getSlots,
  /** SDK version — plugins can gate on this if they need specific features. */
  version: '0.1.0',
} as const

// Attach to window so external plugin bundles can reach it.
if (typeof window !== 'undefined') {
  ;(window as Window & { chatwire?: typeof chatwire }).chatwire = chatwire
}
