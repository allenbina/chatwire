/**
 * SlotRenderer — renders all components registered for a named slot.
 *
 * Each registration is wrapped in a per-component error boundary so a
 * crashing plugin cannot take down the host UI. A minimal fallback is
 * shown instead of the broken component.
 *
 * Usage:
 *   <SlotRenderer slot="sidebar.panel" />
 *   <SlotRenderer slot="message.toolbar" msgId={msg.rowid} />
 *
 * Any extra props are forwarded to every component in the slot.
 */
import { Component, type ErrorInfo, type ReactNode } from 'react'
import { getSlots, type SlotName, type SlotProps } from './registry'

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
          className="text-[10px] text-[--color-error] px-2 py-1 bg-[--color-bg-tertiary] rounded"
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
 * Extra props (beyond `slot`) are forwarded to each plugin component.
 * Returns null if nothing is registered for the slot (no DOM footprint).
 */
export function SlotRenderer({ slot, ...rest }: SlotRendererProps): React.ReactElement | null {
  const registrations = getSlots(slot)
  if (registrations.length === 0) return null

  const forwardedProps: SlotProps = { slot, ...rest }

  return (
    <>
      {registrations.map(({ key, component: Comp, props: regProps }) => {
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
