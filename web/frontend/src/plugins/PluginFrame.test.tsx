/**
 * Vitest unit tests for PluginFrame — sandboxed iframe container.
 *
 * Covers:
 *   - renders an iframe element with sandbox="allow-scripts"
 *   - correct title and aria-label attributes
 *   - srcDoc embeds the plugin script src
 *   - onLoad sends slot-render message with slot + slotProps to iframe
 *   - onLoad sends theme-changed message to iframe
 *   - get-theme message from plugin triggers a theme-changed reply
 *   - register-css message injects a <style> into document.head
 *   - register-css style element carries data-plugin-key and data-plugin-css-key
 *   - register-css same key replaces existing style textContent (no new element)
 *   - register-css with non-string key is silently ignored
 *   - register-css with non-string css is silently ignored
 *   - unknown message type is silently ignored
 *   - message from a different source (not the plugin iframe) is ignored
 *   - message with no type field is ignored
 *   - injected <style> element is removed from the DOM on component unmount
 *   - window message listener is removed on unmount (no processing after)
 */
import { render, screen, fireEvent, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { PluginFrame } from './PluginFrame'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PLUGIN_KEY = 'test-plugin'
const SRC = '/plugins/test.js'
const SLOT = 'sidebar.panel' as const

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderFrame(
  overrides: Partial<React.ComponentProps<typeof PluginFrame>> = {},
) {
  return render(
    <PluginFrame
      pluginKey={PLUGIN_KEY}
      src={SRC}
      slot={SLOT}
      slotProps={{ extra: 42 }}
      {...overrides}
    />,
  )
}

/**
 * Return the rendered iframe element and a spy on its contentWindow.postMessage.
 * If jsdom gives us a real contentWindow, we spy on it directly.
 * If contentWindow is null, we inject a fake window via Object.defineProperty.
 */
function getIframeWithSpy() {
  const iframe = document.querySelector('iframe') as HTMLIFrameElement
  expect(iframe).not.toBeNull()

  let postMessageSpy: ReturnType<typeof vi.fn>
  const cw = iframe.contentWindow
  if (cw) {
    postMessageSpy = vi.spyOn(cw, 'postMessage') as ReturnType<typeof vi.fn>
  } else {
    const fakeWin = { postMessage: vi.fn() }
    Object.defineProperty(iframe, 'contentWindow', {
      get: () => fakeWin,
      configurable: true,
    })
    postMessageSpy = fakeWin.postMessage as ReturnType<typeof vi.fn>
  }

  return { iframe, postMessageSpy }
}

/**
 * Dispatch a MessageEvent to window, as if it came from the plugin iframe.
 * Uses the iframe's contentWindow as event.source so the component's
 * origin check passes.
 */
function dispatchFromIframe(iframe: HTMLIFrameElement, data: unknown) {
  act(() => {
    window.dispatchEvent(
      new MessageEvent('message', {
        source: iframe.contentWindow as MessageEventSource,
        data,
      }),
    )
  })
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  // Remove any leftover injected style elements from previous tests
  document
    .querySelectorAll(`style[data-plugin-key="${PLUGIN_KEY}"]`)
    .forEach((el) => el.remove())
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// Iframe attributes
// ---------------------------------------------------------------------------

describe('PluginFrame — iframe attributes', () => {
  it('renders an iframe element', () => {
    renderFrame()
    expect(document.querySelector('iframe')).not.toBeNull()
  })

  it('has sandbox="allow-scripts" (no allow-same-origin)', () => {
    renderFrame()
    const iframe = document.querySelector('iframe')!
    expect(iframe.getAttribute('sandbox')).toBe('allow-scripts')
  })

  it('title is "plugin:<pluginKey>"', () => {
    renderFrame()
    expect(screen.getByTitle(`plugin:${PLUGIN_KEY}`)).toBeTruthy()
  })

  it('aria-label is "Plugin: <pluginKey>"', () => {
    renderFrame()
    const iframe = document.querySelector('iframe')!
    expect(iframe.getAttribute('aria-label')).toBe(`Plugin: ${PLUGIN_KEY}`)
  })

  it('srcDoc contains the plugin script src', () => {
    renderFrame()
    const iframe = document.querySelector('iframe')!
    expect(iframe.getAttribute('srcdoc')).toContain(SRC)
  })
})

// ---------------------------------------------------------------------------
// onLoad — initial messages
// ---------------------------------------------------------------------------

describe('PluginFrame — onLoad messages', () => {
  it('sends slot-render with slot and slotProps on load', () => {
    renderFrame()
    const { iframe, postMessageSpy } = getIframeWithSpy()
    fireEvent.load(iframe)

    expect(postMessageSpy).toHaveBeenCalledWith(
      { type: 'slot-render', slot: SLOT, props: { extra: 42 } },
      '*',
    )
  })

  it('sends theme-changed on load', () => {
    renderFrame()
    const { iframe, postMessageSpy } = getIframeWithSpy()
    fireEvent.load(iframe)

    expect(postMessageSpy).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'theme-changed', theme: expect.any(Object) }),
      '*',
    )
  })

  it('slot-render uses default empty slotProps when none provided', () => {
    renderFrame({ slotProps: undefined })
    const { iframe, postMessageSpy } = getIframeWithSpy()
    fireEvent.load(iframe)

    expect(postMessageSpy).toHaveBeenCalledWith(
      { type: 'slot-render', slot: SLOT, props: {} },
      '*',
    )
  })
})

// ---------------------------------------------------------------------------
// Incoming messages — get-theme
// ---------------------------------------------------------------------------

describe('PluginFrame — get-theme handling', () => {
  it('replies with theme-changed when plugin sends get-theme', () => {
    renderFrame()
    const { iframe, postMessageSpy } = getIframeWithSpy()

    dispatchFromIframe(iframe, { type: 'get-theme' })

    expect(postMessageSpy).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'theme-changed', theme: expect.any(Object) }),
      '*',
    )
  })
})

// ---------------------------------------------------------------------------
// Incoming messages — register-css
// ---------------------------------------------------------------------------

describe('PluginFrame — register-css handling', () => {
  it('injects a <style> element into document.head', () => {
    renderFrame()
    const { iframe } = getIframeWithSpy()

    dispatchFromIframe(iframe, {
      type: 'register-css',
      key: 'my-styles',
      css: 'body { color: red; }',
    })

    const style = document.querySelector(`style[data-plugin-key="${PLUGIN_KEY}"]`)
    expect(style).not.toBeNull()
    expect(style!.textContent).toBe('body { color: red; }')
  })

  it('style element has data-plugin-key and data-plugin-css-key attributes', () => {
    renderFrame()
    const { iframe } = getIframeWithSpy()

    dispatchFromIframe(iframe, {
      type: 'register-css',
      key: 'my-css-key',
      css: '.foo { display: none; }',
    })

    const style = document.querySelector(`style[data-plugin-key="${PLUGIN_KEY}"]`) as HTMLStyleElement
    expect(style).not.toBeNull()
    expect(style.dataset.pluginKey).toBe(PLUGIN_KEY)
    expect(style.dataset.pluginCssKey).toBe('my-css-key')
  })

  it('replaces textContent when the same key is sent again (no new element)', () => {
    renderFrame()
    const { iframe } = getIframeWithSpy()

    dispatchFromIframe(iframe, {
      type: 'register-css',
      key: 'theme-css',
      css: '.a { color: blue; }',
    })
    dispatchFromIframe(iframe, {
      type: 'register-css',
      key: 'theme-css',
      css: '.a { color: green; }',
    })

    const styles = document.querySelectorAll(`style[data-plugin-key="${PLUGIN_KEY}"]`)
    expect(styles).toHaveLength(1)
    expect((styles[0] as HTMLStyleElement).textContent).toBe('.a { color: green; }')
  })

  it('ignores register-css when key is not a string', () => {
    renderFrame()
    const { iframe } = getIframeWithSpy()

    dispatchFromIframe(iframe, { type: 'register-css', key: 123, css: 'body {}' })

    expect(document.querySelector(`style[data-plugin-key="${PLUGIN_KEY}"]`)).toBeNull()
  })

  it('ignores register-css when css is not a string', () => {
    renderFrame()
    const { iframe } = getIframeWithSpy()

    dispatchFromIframe(iframe, { type: 'register-css', key: 'ok', css: null })

    expect(document.querySelector(`style[data-plugin-key="${PLUGIN_KEY}"]`)).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Message filtering
// ---------------------------------------------------------------------------

describe('PluginFrame — message filtering', () => {
  it('ignores messages from a different source', () => {
    renderFrame()
    const { iframe, postMessageSpy } = getIframeWithSpy()
    // Fire the initial load so we have a baseline call count
    fireEvent.load(iframe)
    const callsBefore = postMessageSpy.mock.calls.length

    // Dispatch get-theme from a different source (window itself, not iframe)
    act(() => {
      window.dispatchEvent(
        new MessageEvent('message', {
          source: window as MessageEventSource,
          data: { type: 'get-theme' },
        }),
      )
    })

    // postMessage should NOT have been called again
    expect(postMessageSpy.mock.calls.length).toBe(callsBefore)
  })

  it('ignores messages with no type field', () => {
    renderFrame()
    const { iframe } = getIframeWithSpy()

    // Should not throw
    dispatchFromIframe(iframe, { notType: 'foo' })
    dispatchFromIframe(iframe, null)

    expect(document.querySelector(`style[data-plugin-key="${PLUGIN_KEY}"]`)).toBeNull()
  })

  it('ignores unknown message types silently', () => {
    renderFrame()
    const { iframe, postMessageSpy } = getIframeWithSpy()
    fireEvent.load(iframe)
    const callsBefore = postMessageSpy.mock.calls.length

    // Should not throw and should not trigger any reply
    dispatchFromIframe(iframe, { type: 'some-unknown-type', payload: 42 })

    expect(postMessageSpy.mock.calls.length).toBe(callsBefore)
    expect(document.querySelector(`style[data-plugin-key="${PLUGIN_KEY}"]`)).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Unmount cleanup
// ---------------------------------------------------------------------------

describe('PluginFrame — unmount cleanup', () => {
  it('removes the injected <style> element from the DOM on unmount', () => {
    const { unmount } = renderFrame()
    const { iframe } = getIframeWithSpy()

    dispatchFromIframe(iframe, {
      type: 'register-css',
      key: 'cleanup-test',
      css: 'body { background: pink; }',
    })

    expect(document.querySelector(`style[data-plugin-key="${PLUGIN_KEY}"]`)).not.toBeNull()

    unmount()

    expect(document.querySelector(`style[data-plugin-key="${PLUGIN_KEY}"]`)).toBeNull()
  })

  it('stops processing messages after unmount', () => {
    const { unmount, rerender } = renderFrame()
    const { iframe, postMessageSpy } = getIframeWithSpy()
    fireEvent.load(iframe)

    unmount()
    // Re-render a fresh component so the DOM is not empty (just to keep test stable)
    // We capture call count right after unmount
    const callsAfterUnmount = postMessageSpy.mock.calls.length

    // Any further messages should be ignored (listener was removed)
    act(() => {
      window.dispatchEvent(
        new MessageEvent('message', {
          source: iframe.contentWindow as MessageEventSource,
          data: { type: 'get-theme' },
        }),
      )
    })

    expect(postMessageSpy.mock.calls.length).toBe(callsAfterUnmount)
    // Suppress unused variable warning
    void rerender
  })
})
