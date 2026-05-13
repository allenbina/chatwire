/**
 * Vitest unit tests for DSL mode in AutomationsSection.
 *
 * Tests the exported helper functions:
 *   - _formToApiRule: structured → API rule shape
 *   - _apiRuleToForm: API rule → form state
 *
 * Covers:
 *   - DSL mode produces { trigger: { type: 'dsl', expr } } with no conditions
 *   - DSL mode with stop_on_match
 *   - Structured mode (unchanged behaviour)
 *   - _apiRuleToForm detects dsl trigger type → dslMode: true, dslExpr populated
 *   - _apiRuleToForm with regular trigger → dslMode: false
 *   - Actions are passed through correctly in both modes
 */
import { describe, it, expect } from 'vitest'
import { _formToApiRule, _apiRuleToForm } from './SettingsPage'

// ---------------------------------------------------------------------------
// _formToApiRule — DSL mode
// ---------------------------------------------------------------------------

const _EMPTY_ACTION = {
  type: 'reply' as const,
  text: '',
  url: '',
  method: 'POST',
  headers: '',
  level: 'info',
  message: '',
}

const _BASE_FORM = {
  name: 'test',
  dslMode: false,
  dslExpr: '',
  triggerType: 'text_contains' as const,
  pattern: 'hello',
  fromHandles: '',
  notFromHandles: '',
  toHandles: '',
  notToHandles: '',
  inGroup: 'any' as const,
  groupGuid: '',
  actions: [{ ..._EMPTY_ACTION }],
  stopOnMatch: false,
}

describe('_formToApiRule — DSL mode', () => {
  it('produces trigger.type=dsl when dslMode is true', () => {
    const form = { ..._BASE_FORM, dslMode: true, dslExpr: 'contains:hello' }
    const rule = _formToApiRule(form)
    expect((rule.trigger as Record<string, unknown>).type).toBe('dsl')
  })

  it('includes expr from dslExpr field', () => {
    const form = { ..._BASE_FORM, dslMode: true, dslExpr: 'from:+15551234567 AND contains:urgent' }
    const rule = _formToApiRule(form)
    expect((rule.trigger as Record<string, unknown>).expr).toBe('from:+15551234567 AND contains:urgent')
  })

  it('does not include conditions when dslMode is true', () => {
    const form = {
      ..._BASE_FORM,
      dslMode: true,
      dslExpr: 'always',
      fromHandles: '+1555',
      inGroup: 'group_only' as const,
    }
    const rule = _formToApiRule(form)
    expect(rule.conditions).toBeUndefined()
  })

  it('does not include pattern in trigger when dslMode is true', () => {
    const form = { ..._BASE_FORM, dslMode: true, dslExpr: 'always', pattern: 'leftover' }
    const rule = _formToApiRule(form)
    expect((rule.trigger as Record<string, unknown>).pattern).toBeUndefined()
  })

  it('includes stop_on_match when set in DSL mode', () => {
    const form = { ..._BASE_FORM, dslMode: true, dslExpr: 'always', stopOnMatch: true }
    const rule = _formToApiRule(form)
    expect(rule.stop_on_match).toBe(true)
  })

  it('does not include stop_on_match when false in DSL mode', () => {
    const form = { ..._BASE_FORM, dslMode: true, dslExpr: 'always', stopOnMatch: false }
    const rule = _formToApiRule(form)
    expect(rule.stop_on_match).toBeUndefined()
  })

  it('passes through actions correctly in DSL mode', () => {
    const action = { ..._EMPTY_ACTION, type: 'log' as const, message: 'fired', level: 'warning' }
    const form = { ..._BASE_FORM, dslMode: true, dslExpr: 'always', actions: [action] }
    const rule = _formToApiRule(form)
    const actions = rule.actions as Record<string, unknown>[]
    expect(actions[0].type).toBe('log')
    expect(actions[0].message).toBe('fired')
    expect(actions[0].level).toBe('warning')
  })

  it('carries rule name into output in DSL mode', () => {
    const form = { ..._BASE_FORM, name: 'my-dsl-rule', dslMode: true, dslExpr: 'always' }
    const rule = _formToApiRule(form)
    expect(rule.name).toBe('my-dsl-rule')
  })
})

// ---------------------------------------------------------------------------
// _formToApiRule — structured mode (regression check)
// ---------------------------------------------------------------------------

describe('_formToApiRule — structured mode', () => {
  it('produces text_contains trigger with pattern', () => {
    const form = { ..._BASE_FORM, triggerType: 'text_contains' as const, pattern: 'hi' }
    const rule = _formToApiRule(form)
    const trigger = rule.trigger as Record<string, unknown>
    expect(trigger.type).toBe('text_contains')
    expect(trigger.pattern).toBe('hi')
  })

  it('does not include conditions key when no conditions set', () => {
    const rule = _formToApiRule(_BASE_FORM)
    expect(rule.conditions).toBeUndefined()
  })

  it('includes from_handles in conditions', () => {
    const form = { ..._BASE_FORM, fromHandles: '+1, +2' }
    const rule = _formToApiRule(form)
    expect((rule.conditions as Record<string, unknown>).from_handles).toEqual(['+1', '+2'])
  })

  it('includes in_group=true for group_only', () => {
    const form = { ..._BASE_FORM, inGroup: 'group_only' as const }
    const rule = _formToApiRule(form)
    expect((rule.conditions as Record<string, unknown>).in_group).toBe(true)
  })

  it('includes in_group=false for one_to_one', () => {
    const form = { ..._BASE_FORM, inGroup: 'one_to_one' as const }
    const rule = _formToApiRule(form)
    expect((rule.conditions as Record<string, unknown>).in_group).toBe(false)
  })

  it('always trigger omits pattern', () => {
    const form = { ..._BASE_FORM, triggerType: 'always' as const, pattern: '' }
    const rule = _formToApiRule(form)
    expect((rule.trigger as Record<string, unknown>).pattern).toBeUndefined()
  })
})

// ---------------------------------------------------------------------------
// _apiRuleToForm — DSL trigger detection
// ---------------------------------------------------------------------------

describe('_apiRuleToForm — DSL trigger', () => {
  it('sets dslMode=true when trigger.type is dsl', () => {
    const rule = {
      name: 'r',
      trigger: { type: 'dsl', expr: 'always' },
      actions: [],
    }
    const form = _apiRuleToForm(rule)
    expect(form.dslMode).toBe(true)
  })

  it('populates dslExpr from trigger.expr', () => {
    const rule = {
      name: 'r',
      trigger: { type: 'dsl', expr: '(from:+1 OR from:+2) AND contains:urgent' },
      actions: [],
    }
    const form = _apiRuleToForm(rule)
    expect(form.dslExpr).toBe('(from:+1 OR from:+2) AND contains:urgent')
  })

  it('sets dslMode=false for structured triggers', () => {
    const rule = {
      name: 'r',
      trigger: { type: 'text_contains', pattern: 'hi' },
      actions: [],
    }
    const form = _apiRuleToForm(rule)
    expect(form.dslMode).toBe(false)
  })

  it('sets dslExpr="" for structured triggers', () => {
    const rule = {
      name: 'r',
      trigger: { type: 'text_contains', pattern: 'hi' },
      actions: [],
    }
    const form = _apiRuleToForm(rule)
    expect(form.dslExpr).toBe('')
  })

  it('reads stop_on_match from DSL rule', () => {
    const rule = {
      name: 'r',
      trigger: { type: 'dsl', expr: 'always' },
      actions: [],
      stop_on_match: true,
    }
    const form = _apiRuleToForm(rule)
    expect(form.stopOnMatch).toBe(true)
  })

  it('parses actions from DSL rule', () => {
    const rule = {
      name: 'r',
      trigger: { type: 'dsl', expr: 'always' },
      actions: [{ type: 'reply', text: 'hello' }],
    }
    const form = _apiRuleToForm(rule)
    expect(form.actions[0].type).toBe('reply')
    expect(form.actions[0].text).toBe('hello')
  })

  it('uses default action when actions array is empty in DSL rule', () => {
    const rule = { name: 'r', trigger: { type: 'dsl', expr: 'always' }, actions: [] }
    const form = _apiRuleToForm(rule)
    expect(form.actions).toHaveLength(1)
    expect(form.actions[0].type).toBe('reply')
  })

  it('DSL form has empty fromHandles (conditions not in form)', () => {
    const rule = { name: 'r', trigger: { type: 'dsl', expr: 'always' }, actions: [] }
    const form = _apiRuleToForm(rule)
    expect(form.fromHandles).toBe('')
    expect(form.notFromHandles).toBe('')
  })
})
