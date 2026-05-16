/**
 * Vitest unit tests for SlotRenderer — plugin slot rendering orchestrator.
 *
 * Covers:
 *   - returns null when the slot is empty (no DOM footprint)
 *   - renders core-tier components directly in the React tree
 *   - renders official-tier components directly in the React tree
 *   - defaults to core tier when tier is omitted
 *   - forwards extra SlotRenderer props to trusted components
 *   - merges registration props with SlotRenderer props
 *   - renders ui-tier components with a src URL via PluginFrame (sandboxed)
 *   - renders notify-tier components with a src URL via PluginFrame (sandboxed)
 *   - falls back to direct render for ui/notify without a src URL
 *   - PluginFrame receives correct pluginKey, src, slot, and slotProps
 *   - renders multiple registrations in registration order
 *   - error boundary catches a crashing component and shows "Plugin error: key"
 */
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { ComponentType } from 'react'
import { SlotRenderer } from './SlotRenderer'
import { clearSlots, registerSlot, type SlotProps } from './registry'

// ---------------------------------------------------------------------------
// Mock PluginFrame — avoid iframe/postMessage complexity in these tests.
// The mock renders a div whose data attributes expose the props received.
// ---------------------------------------------------------------------------

vi.mock('./PluginFrame', () => ({
  PluginFrame: ({
    pluginKey,
    src,
    slot,
    slotProps,
  }: {
    pluginKey: string
    src: string
    slot: string
    slotProps?: Record<string, unknown>
  }) => (
    <div
      data-testid="plugin-frame"
      data-plugin-key={pluginKey}
      data-src={src}
      data-slot={slot}
      data-slot-props={JSON.stringify(slotProps ?? {})}
    />
  ),
}))

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Create a named stub component that renders its received props as JSON. */
function makeComp(testId: string): ComponentType<SlotProps> {
  const Comp = (props: SlotProps) => (
    <div
      data-testid={testId}
      data-slot={props.slot}
      data-props={JSON.stringify(props)}
    />
  )
  Comp.displayName = testId
  return Comp as ComponentType<SlotProps>
}

/** A component that always throws during render — used for error-boundary tests. */
const CrashingComp = (_props: SlotProps): never => {
  throw new Error('intentional crash')
}
CrashingComp.displayName = 'CrashingComp'

// ---------------------------------------------------------------------------
// Setup: reset registry between tests
// ---------------------------------------------------------------------------

beforeEach(() => {
  clearSlots()
})

// ---------------------------------------------------------------------------
// Empty slot
// ---------------------------------------------------------------------------

describe('SlotRenderer — empty slot', () => {
  it('returns null when nothing is registered for the slot', () => {
    const { container } = render(<SlotRenderer slot="sidebar.panel" />)
    expect(container.firstChild).toBeNull()
  })

  it('returns null for a different slot even when another slot has registrations', () => {
    registerSlot('message.toolbar', makeComp('toolbar-widget'))
    const { container } = render(<SlotRenderer slot="sidebar.panel" />)
    expect(container.firstChild).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Trusted path — core / official / default tier
// ---------------------------------------------------------------------------

describe('SlotRenderer — trusted direct render', () => {
  it('renders a core-tier component directly', () => {
    registerSlot('sidebar.panel', makeComp('core-widget'), { tier: 'core' })
    render(<SlotRenderer slot="sidebar.panel" />)
    expect(screen.getByTestId('core-widget')).toBeTruthy()
  })

  it('renders an official-tier component directly', () => {
    registerSlot('sidebar.panel', makeComp('official-widget'), { tier: 'official' })
    render(<SlotRenderer slot="sidebar.panel" />)
    expect(screen.getByTestId('official-widget')).toBeTruthy()
  })

  it('defaults to core tier when tier is omitted and renders directly', () => {
    registerSlot('sidebar.panel', makeComp('default-widget'))
    render(<SlotRenderer slot="sidebar.panel" />)
    expect(screen.getByTestId('default-widget')).toBeTruthy()
    expect(screen.queryByTestId('plugin-frame')).toBeNull()
  })

  it('forwards extra SlotRenderer props to trusted components', () => {
    registerSlot('sidebar.panel', makeComp('prop-widget'), { tier: 'core' })
    render(<SlotRenderer slot="sidebar.panel" extraProp="hello" numProp={7} />)
    const el = screen.getByTestId('prop-widget')
    const props = JSON.parse(el.getAttribute('data-props') ?? '{}')
    expect(props.extraProp).toBe('hello')
    expect(props.numProp).toBe(7)
    expect(props.slot).toBe('sidebar.panel')
  })

  it('merges registration props with SlotRenderer props (renderer wins on collision)', () => {
    registerSlot('sidebar.panel', makeComp('merged-widget'), {
      tier: 'core',
      props: { fromReg: true, shared: 'reg' },
    })
    render(<SlotRenderer slot="sidebar.panel" fromSlot={42} shared="renderer" />)
    const el = screen.getByTestId('merged-widget')
    const props = JSON.parse(el.getAttribute('data-props') ?? '{}')
    expect(props.fromReg).toBe(true)
    expect(props.fromSlot).toBe(42)
    // SlotRenderer props spread last → override registration props
    expect(props.shared).toBe('renderer')
  })
})

// ---------------------------------------------------------------------------
// Sandboxed path — ui / notify tier with src
// ---------------------------------------------------------------------------

describe('SlotRenderer — sandboxed PluginFrame render', () => {
  it('renders ui-tier component with src via PluginFrame', () => {
    registerSlot('sidebar.panel', makeComp('ui-widget'), {
      tier: 'ui',
      src: 'https://example.com/plugin.js',
      key: 'my-ui-plugin',
    })
    render(<SlotRenderer slot="sidebar.panel" />)
    const frame = screen.getByTestId('plugin-frame')
    expect(frame.getAttribute('data-plugin-key')).toBe('my-ui-plugin')
    expect(frame.getAttribute('data-src')).toBe('https://example.com/plugin.js')
    expect(frame.getAttribute('data-slot')).toBe('sidebar.panel')
    // Trusted component should NOT appear
    expect(screen.queryByTestId('ui-widget')).toBeNull()
  })

  it('renders notify-tier component with src via PluginFrame', () => {
    registerSlot('message.toolbar', makeComp('notify-widget'), {
      tier: 'notify',
      src: '/plugins/notify.js',
      key: 'my-notify',
    })
    render(<SlotRenderer slot="message.toolbar" />)
    const frame = screen.getByTestId('plugin-frame')
    expect(frame.getAttribute('data-plugin-key')).toBe('my-notify')
    expect(frame.getAttribute('data-src')).toBe('/plugins/notify.js')
  })

  it('falls back to direct render for ui tier without a src', () => {
    registerSlot('sidebar.panel', makeComp('ui-no-src'), { tier: 'ui' })
    render(<SlotRenderer slot="sidebar.panel" />)
    expect(screen.getByTestId('ui-no-src')).toBeTruthy()
    expect(screen.queryByTestId('plugin-frame')).toBeNull()
  })

  it('falls back to direct render for notify tier without a src', () => {
    registerSlot('sidebar.panel', makeComp('notify-no-src'), { tier: 'notify' })
    render(<SlotRenderer slot="sidebar.panel" />)
    expect(screen.getByTestId('notify-no-src')).toBeTruthy()
    expect(screen.queryByTestId('plugin-frame')).toBeNull()
  })

  it('PluginFrame receives merged registration props and renderer props as slotProps', () => {
    registerSlot('sidebar.panel', makeComp('sp-widget'), {
      tier: 'ui',
      src: '/plugin.js',
      key: 'sp-test',
      props: { fromReg: 'yes' },
    })
    render(<SlotRenderer slot="sidebar.panel" msgId={99} />)
    const frame = screen.getByTestId('plugin-frame')
    const slotProps = JSON.parse(frame.getAttribute('data-slot-props') ?? '{}')
    expect(slotProps.fromReg).toBe('yes')
    expect(slotProps.msgId).toBe(99)
  })
})

// ---------------------------------------------------------------------------
// Multiple registrations
// ---------------------------------------------------------------------------

describe('SlotRenderer — multiple registrations', () => {
  it('renders all components in registration order', () => {
    registerSlot('sidebar.panel', makeComp('widget-a'))
    registerSlot('sidebar.panel', makeComp('widget-b'))
    registerSlot('sidebar.panel', makeComp('widget-c'))
    const { container } = render(<SlotRenderer slot="sidebar.panel" />)
    const items = container.querySelectorAll('[data-testid]')
    expect(items).toHaveLength(3)
    expect(items[0].getAttribute('data-testid')).toBe('widget-a')
    expect(items[1].getAttribute('data-testid')).toBe('widget-b')
    expect(items[2].getAttribute('data-testid')).toBe('widget-c')
  })

  it('mixes trusted and sandboxed registrations', () => {
    registerSlot('sidebar.panel', makeComp('trusted-one'))
    registerSlot('sidebar.panel', makeComp('sandboxed'), {
      tier: 'ui',
      src: '/p.js',
      key: 'sand-key',
    })
    render(<SlotRenderer slot="sidebar.panel" />)
    expect(screen.getByTestId('trusted-one')).toBeTruthy()
    expect(screen.getByTestId('plugin-frame')).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// Error boundary
// ---------------------------------------------------------------------------

describe('SlotRenderer — error boundary', () => {
  it('shows plugin error message when a trusted component throws', () => {
    registerSlot('sidebar.panel', CrashingComp as ComponentType<SlotProps>, {
      key: 'crash-key',
    })
    // Suppress React's error boundary console.error output
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(<SlotRenderer slot="sidebar.panel" />)
    errSpy.mockRestore()

    const alert = screen.getByRole('alert')
    expect(alert).toBeTruthy()
    expect(alert.textContent).toContain('crash-key')
  })

  it('a crashing plugin does not prevent other registrations from rendering', () => {
    registerSlot('sidebar.panel', CrashingComp as ComponentType<SlotProps>, {
      key: 'crash-key',
    })
    registerSlot('sidebar.panel', makeComp('healthy-widget'))

    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(<SlotRenderer slot="sidebar.panel" />)
    errSpy.mockRestore()

    expect(screen.getByRole('alert')).toBeTruthy()
    expect(screen.getByTestId('healthy-widget')).toBeTruthy()
  })
})
