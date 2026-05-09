/**
 * Tests for the plugin slot registry.
 *
 * We import clearSlots to reset state between tests so registrations from
 * one test don't bleed into the next.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import type { ComponentType } from 'react'
import {
  registerSlot,
  getSlots,
  clearSlots,
  chatwire,
  type SlotName,
  type SlotProps,
} from './registry'

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function makeComponent(name: string): ComponentType<SlotProps> {
  const comp = () => null
  comp.displayName = name
  return comp as unknown as ComponentType<SlotProps>
}

// ---------------------------------------------------------------------------
// Setup: isolate each test
// ---------------------------------------------------------------------------

beforeEach(() => {
  clearSlots()
})

// ---------------------------------------------------------------------------
// getSlots — empty
// ---------------------------------------------------------------------------

describe('getSlots', () => {
  it('returns an empty array when no components are registered', () => {
    expect(getSlots('sidebar.panel')).toEqual([])
    expect(getSlots('message.toolbar')).toEqual([])
    expect(getSlots('settings.page')).toEqual([])
    expect(getSlots('compose.extension')).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// registerSlot — basic
// ---------------------------------------------------------------------------

describe('registerSlot', () => {
  it('registers a component and getSlots returns it', () => {
    const Comp = makeComponent('TestWidget')
    registerSlot('sidebar.panel', Comp)

    const registrations = getSlots('sidebar.panel')
    expect(registrations).toHaveLength(1)
    expect(registrations[0].component).toBe(Comp)
    expect(registrations[0].key).toBe('TestWidget')
  })

  it('uses component.name as key when displayName is absent', () => {
    function NamedComp(_props: SlotProps) { return null }
    registerSlot('sidebar.panel', NamedComp as ComponentType<SlotProps>)

    const regs = getSlots('sidebar.panel')
    expect(regs[0].key).toBe('NamedComp')
  })

  it('uses provided key option over displayName', () => {
    const Comp = makeComponent('InternalName')
    registerSlot('sidebar.panel', Comp, { key: 'my-custom-key' })

    const regs = getSlots('sidebar.panel')
    expect(regs[0].key).toBe('my-custom-key')
  })

  it('stores extra props passed in options', () => {
    const Comp = makeComponent('PropComp')
    registerSlot('sidebar.panel', Comp, { props: { title: 'hello', count: 42 } })

    const regs = getSlots('sidebar.panel')
    expect(regs[0].props).toEqual({ title: 'hello', count: 42 })
  })

  it('registrations are independent per slot', () => {
    const A = makeComponent('A')
    const B = makeComponent('B')
    registerSlot('sidebar.panel', A)
    registerSlot('message.toolbar', B)

    expect(getSlots('sidebar.panel')).toHaveLength(1)
    expect(getSlots('message.toolbar')).toHaveLength(1)
    expect(getSlots('settings.page')).toHaveLength(0)
  })

  it('multiple registrations in the same slot accumulate in order', () => {
    const A = makeComponent('A')
    const B = makeComponent('B')
    const C = makeComponent('C')
    registerSlot('sidebar.panel', A)
    registerSlot('sidebar.panel', B)
    registerSlot('sidebar.panel', C)

    const regs = getSlots('sidebar.panel')
    expect(regs).toHaveLength(3)
    expect(regs.map((r) => r.key)).toEqual(['A', 'B', 'C'])
  })

  it('re-registering the same key replaces the old entry', () => {
    const First = makeComponent('MyWidget')
    const Second = makeComponent('MyWidget')
    registerSlot('sidebar.panel', First)
    registerSlot('sidebar.panel', Second)

    const regs = getSlots('sidebar.panel')
    expect(regs).toHaveLength(1)
    expect(regs[0].component).toBe(Second)
  })

  it('all four slot names are valid', () => {
    const slots: SlotName[] = [
      'message.toolbar',
      'sidebar.panel',
      'settings.page',
      'compose.extension',
    ]
    for (const slot of slots) {
      const Comp = makeComponent(`Comp_${slot}`)
      registerSlot(slot, Comp)
      expect(getSlots(slot)).toHaveLength(1)
    }
  })
})

// ---------------------------------------------------------------------------
// clearSlots
// ---------------------------------------------------------------------------

describe('clearSlots', () => {
  it('clears a specific slot without affecting others', () => {
    const A = makeComponent('A')
    const B = makeComponent('B')
    registerSlot('sidebar.panel', A)
    registerSlot('message.toolbar', B)

    clearSlots('sidebar.panel')

    expect(getSlots('sidebar.panel')).toHaveLength(0)
    expect(getSlots('message.toolbar')).toHaveLength(1)
  })

  it('clears all slots when called with no arguments', () => {
    registerSlot('sidebar.panel', makeComponent('A'))
    registerSlot('message.toolbar', makeComponent('B'))
    registerSlot('settings.page', makeComponent('C'))

    clearSlots()

    expect(getSlots('sidebar.panel')).toHaveLength(0)
    expect(getSlots('message.toolbar')).toHaveLength(0)
    expect(getSlots('settings.page')).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// window.chatwire exposure
// ---------------------------------------------------------------------------

describe('chatwire global API', () => {
  it('exposes registerSlot and getSlots', () => {
    expect(typeof chatwire.registerSlot).toBe('function')
    expect(typeof chatwire.getSlots).toBe('function')
  })

  it('chatwire.registerSlot delegates to the same registry', () => {
    const Comp = makeComponent('GlobalWidget')
    chatwire.registerSlot('sidebar.panel', Comp)
    expect(getSlots('sidebar.panel')[0].component).toBe(Comp)
  })

  it('chatwire.getSlots returns current registrations', () => {
    const Comp = makeComponent('GW2')
    registerSlot('settings.page', Comp)
    expect(chatwire.getSlots('settings.page')[0].component).toBe(Comp)
  })

  it('has a version string', () => {
    expect(typeof chatwire.version).toBe('string')
    expect(chatwire.version.length).toBeGreaterThan(0)
  })
})
