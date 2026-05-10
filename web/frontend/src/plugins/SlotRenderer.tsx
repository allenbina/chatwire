/**
 * SlotRenderer — renders all components registered for a named slot.
 *
 * Rendering paths
 * ---------------
 * - `core` / `official` tier → rendered directly in the host React tree (trusted).
 * - `notify` / `ui` tier with a `src` URL → rendered via <PluginFrame> (sandboxed
 *   iframe, no parent DOM access, no cookies, no localStorage).
 * - `notify` / `ui` tier without `src` → falls back to direct render (legacy path
 *   for built-in components that haven't migrated to the iframe model yet).
 *
 * Each registration is wrapped in a per-component error boundary so a crashing
 * plugin cannot take down the host UI.
 *
 * Usage:
 *   <SlotRenderer slot="sidebar.panel" />
 *   <SlotRenderer slot="message.toolbar" msgId={msg.rowid} />
 *
 * Any extra props are forwarded to every trusted component in the slot.
 */
import { Component, type ErrorInfo, type ReactNode } from 'react'
import { getSlots, type SlotName, type SlotProps } from './registry'
import { PluginFrame } from './PluginFrame'

// ---------------------------------------------------------------------------
// Per-plugin error boundary
// ---------------------------------------------------------------------------

interface BoundaryState {
  hasError: boolean
  error: Error | null
}

interface BoundaryProps {
  pluginKey: string
  children: ReactNode
}

class PluginErrorBoundary extends Component<BoundaryProps, BoundaryState> {
  constructor(props: BoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): BoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Log to console — production installs can hook this up to Sentry etc.
    console.error(`[chatwire plugin "${this.props.pluginKey}" crashed]`, error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          role="alert"
          className="text-[10px] text-destructive px-2 py-1 bg-muted rounded"
          title={this.state.error?.message}
        >
          Plugin error: {this.props.pluginKey}
        </div>
      )
    }
    return this.props.children
  }
}

// ---------------------------------------------------------------------------
// SlotRenderer
// ---------------------------------------------------------------------------

interface SlotRendererProps extends Record<string, unknown> {
  slot: SlotName
}

/**
 * Renders all components registered for `slot`.
 * Extra props (beyond `slot`) are forwarded to every trusted plugin component.
 * Sandboxed (ui/notify) plugins with a `src` receive props via postMessage.
 * Returns null if nothing is registered for the slot (no DOM footprint).
 */
export function SlotRenderer({ slot, ...rest }: SlotRendererProps): React.ReactElement | null {
  const registrations = getSlots(slot)
  if (registrations.length === 0) return null

  const forwardedProps: SlotProps = { slot, ...rest }

  return (
    <>
      {registrations.map(({ key, component: Comp, props: regProps, tier, src }) => {
        const isTrusted = !tier || tier === 'core' || tier === 'official'

        // Sandboxed path: ui/notify plugins with an explicit JS bundle URL.
        if (!isTrusted && src) {
          return (
            <PluginErrorBoundary key={key} pluginKey={key}>
              <PluginFrame
                pluginKey={key}
                src={src}
                slot={slot}
                slotProps={{ ...regProps, ...rest }}
              />
            </PluginErrorBoundary>
          )
        }

        // Trusted path (core/official) or legacy ui/notify without src.
        // Renders directly in the host React tree.
        const mergedProps: SlotProps = { ...regProps, ...forwardedProps }
        return (
          <PluginErrorBoundary key={key} pluginKey={key}>
            <Comp {...mergedProps} />
          </PluginErrorBoundary>
        )
      })}
    </>
  )
}
