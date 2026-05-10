/**
 * PluginFrame — sandboxed iframe container for third-party (ui/notify) plugins.
 *
 * Security model:
 * - `sandbox="allow-scripts"` only — NO allow-same-origin.
 *   The iframe has an opaque (null) origin, so it cannot access:
 *   parent DOM, localStorage, cookies, or make credentialed fetch requests.
 * - All communication is via window.postMessage only.
 *
 * postMessage protocol
 * --------------------
 * Parent → Plugin:
 *   { type: 'theme-changed', theme: Record<string, string> }
 *     Sent on load and whenever the host theme changes.
 *   { type: 'slot-render', slot: string, props: Record<string, unknown> }
 *     Sent on load so the plugin knows which slot it occupies.
 *
 * Plugin → Parent:
 *   { type: 'get-theme' }
 *     Plugin requests the current theme variables. Parent replies with theme-changed.
 *   { type: 'register-css', key: string, css: string }
 *     Plugin injects/replaces a named <style> block in the parent document.
 *
 * Unknown message types are silently ignored — no errors thrown.
 */
import { useCallback, useEffect, useRef } from 'react'

// ---------------------------------------------------------------------------
// Message type contracts
// ---------------------------------------------------------------------------

type ParentToPlugin =
  | { type: 'theme-changed'; theme: Record<string, string> }
  | { type: 'slot-render'; slot: string; props: Record<string, unknown> }

// Plugin → Parent messages we handle
interface RegisterCssMsg {
  type: 'register-css'
  key: string
  css: string
}
interface GetThemeMsg {
  type: 'get-theme'
}
type PluginToParent = RegisterCssMsg | GetThemeMsg | { type: string }

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface PluginFrameProps {
  /** Unique key identifying this plugin (used to scope injected styles). */
  pluginKey: string
  /** URL of the plugin JS bundle to load inside the sandbox. */
  src: string
  /** Slot name forwarded to the plugin via slot-render. */
  slot: string
  /** Additional slot props forwarded to the plugin (no PII). */
  slotProps?: Record<string, unknown>
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Collect all CSS custom properties from :root that look like theme vars. */
function collectThemeVars(): Record<string, string> {
  if (typeof document === 'undefined') return {}
  const style = getComputedStyle(document.documentElement)
  const vars: Record<string, string> = {}
  // Iterate inline custom properties set on documentElement (theme switcher
  // writes them directly onto documentElement.style).
  for (const prop of Array.from(document.documentElement.style)) {
    if (prop.startsWith('--')) {
      vars[prop] = style.getPropertyValue(prop).trim()
    }
  }
  return vars
}

/** Build the srcdoc HTML that bootstraps the plugin inside the iframe. */
function buildSrcdoc(scriptSrc: string): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>body { margin: 0; }</style>
</head>
<body>
  <script src="${scriptSrc}"></script>
</body>
</html>`
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PluginFrame({ pluginKey, src, slot, slotProps = {} }: PluginFrameProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null)
  // Track the <style> element we injected for this plugin's CSS.
  const injectedStyleRef = useRef<HTMLStyleElement | null>(null)

  /** Send a typed message to the iframe. */
  const send = useCallback((msg: ParentToPlugin) => {
    iframeRef.current?.contentWindow?.postMessage(msg, '*')
  }, [])

  // Handle messages from the plugin iframe.
  useEffect(() => {
    function onMessage(event: MessageEvent) {
      // Only process messages from our iframe — compare contentWindow reference.
      if (!iframeRef.current || event.source !== iframeRef.current.contentWindow) return

      const msg = event.data as PluginToParent
      if (!msg || typeof msg.type !== 'string') return

      if (msg.type === 'get-theme') {
        send({ type: 'theme-changed', theme: collectThemeVars() })
        return
      }

      if (msg.type === 'register-css') {
        const { key, css } = msg as RegisterCssMsg
        if (typeof key !== 'string' || typeof css !== 'string') return
        // Inject / replace a <style> element scoped to this plugin.
        let style = injectedStyleRef.current
        if (!style) {
          style = document.createElement('style')
          style.dataset.pluginKey = pluginKey
          style.dataset.pluginCssKey = key
          document.head.appendChild(style)
          injectedStyleRef.current = style
        }
        style.textContent = css
        return
      }

      // Unknown type — silently ignore.
    }

    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [pluginKey, send])

  // Remove injected <style> when the component unmounts.
  useEffect(() => {
    return () => {
      injectedStyleRef.current?.remove()
      injectedStyleRef.current = null
    }
  }, [])

  // When the iframe finishes loading, send initial messages.
  const handleLoad = useCallback(() => {
    send({ type: 'slot-render', slot, props: slotProps })
    send({ type: 'theme-changed', theme: collectThemeVars() })
  }, [send, slot, slotProps])

  return (
    <iframe
      ref={iframeRef}
      title={`plugin:${pluginKey}`}
      // allow-scripts: plugin JS can execute.
      // NO allow-same-origin: iframe has null origin — cannot touch parent DOM,
      // localStorage, cookies, or make credentialed requests.
      sandbox="allow-scripts"
      srcDoc={buildSrcdoc(src)}
      onLoad={handleLoad}
      style={{ border: 'none', width: '100%', height: '0' }}
      aria-label={`Plugin: ${pluginKey}`}
    />
  )
}
