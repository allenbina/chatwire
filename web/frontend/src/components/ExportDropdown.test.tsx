/**
 * Vitest unit tests for ExportDropdown — conversation export menu.
 *
 * Covers:
 *   - Button renders with correct aria attributes (haspopup, expanded=false)
 *   - Menu is not shown on initial render
 *   - Clicking the button opens the menu (aria-expanded=true)
 *   - Clicking the button again closes the menu
 *   - Shows all four export links when open
 *   - 1:1 chat: links use handle= query param
 *   - Group chat: links use chat= query param
 *   - Handles are URL-encoded in query params
 *   - All export links have the download attribute
 *   - JSON/TXT/CSV links include &format= in the href
 *   - Photos link points to /api/export/photos
 *   - Clicking a menu item closes the menu
 *   - Clicking outside the dropdown closes the menu
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { ExportDropdown } from './ExportDropdown'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderDropdown(handle = 'alice@example.com', isGroup = false) {
  return render(<ExportDropdown handle={handle} isGroup={isGroup} />)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ExportDropdown', () => {
  beforeEach(() => {
    // Ensure a fresh document body for outside-click tests
  })

  afterEach(() => {
    // nothing to clean up
  })

  it('renders the export button', () => {
    renderDropdown()
    const btn = screen.getByRole('button', { name: /export conversation/i })
    expect(btn).toBeTruthy()
  })

  it('button has aria-haspopup="menu"', () => {
    renderDropdown()
    const btn = screen.getByRole('button', { name: /export conversation/i })
    expect(btn.getAttribute('aria-haspopup')).toBe('menu')
  })

  it('button is initially aria-expanded=false', () => {
    renderDropdown()
    const btn = screen.getByRole('button', { name: /export conversation/i })
    expect(btn.getAttribute('aria-expanded')).toBe('false')
  })

  it('menu is not visible on initial render', () => {
    renderDropdown()
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('clicking the button opens the menu', () => {
    renderDropdown()
    fireEvent.click(screen.getByRole('button', { name: /export conversation/i }))
    expect(screen.getByRole('menu')).toBeTruthy()
  })

  it('button is aria-expanded=true when menu is open', () => {
    renderDropdown()
    fireEvent.click(screen.getByRole('button', { name: /export conversation/i }))
    const btn = screen.getByRole('button', { name: /export conversation/i })
    expect(btn.getAttribute('aria-expanded')).toBe('true')
  })

  it('clicking the button a second time closes the menu', () => {
    renderDropdown()
    const btn = screen.getByRole('button', { name: /export conversation/i })
    fireEvent.click(btn)
    fireEvent.click(btn)
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('shows all four export menu items when open', () => {
    renderDropdown()
    fireEvent.click(screen.getByRole('button', { name: /export conversation/i }))
    expect(screen.getByText('Export as JSON')).toBeTruthy()
    expect(screen.getByText('Export as TXT')).toBeTruthy()
    expect(screen.getByText('Export as CSV')).toBeTruthy()
    expect(screen.getByText('Download photos (ZIP)')).toBeTruthy()
  })

  // ---- 1:1 chat URL params ----

  it('1:1 chat: links use handle= query param', () => {
    renderDropdown('alice@icloud.com', false)
    fireEvent.click(screen.getByRole('button', { name: /export conversation/i }))
    const jsonLink = screen.getByText('Export as JSON').closest('a')
    expect(jsonLink?.href).toContain('handle=alice%40icloud.com')
  })

  it('1:1 chat: JSON link has format=json', () => {
    renderDropdown('bob@example.com', false)
    fireEvent.click(screen.getByRole('button', { name: /export conversation/i }))
    const link = screen.getByText('Export as JSON').closest('a')
    expect(link?.href).toContain('format=json')
  })

  it('1:1 chat: TXT link has format=txt', () => {
    renderDropdown('bob@example.com', false)
    fireEvent.click(screen.getByRole('button', { name: /export conversation/i }))
    const link = screen.getByText('Export as TXT').closest('a')
    expect(link?.href).toContain('format=txt')
  })

  it('1:1 chat: CSV link has format=csv', () => {
    renderDropdown('bob@example.com', false)
    fireEvent.click(screen.getByRole('button', { name: /export conversation/i }))
    const link = screen.getByText('Export as CSV').closest('a')
    expect(link?.href).toContain('format=csv')
  })

  it('1:1 chat: photos link points to /api/export/photos', () => {
    renderDropdown('bob@example.com', false)
    fireEvent.click(screen.getByRole('button', { name: /export conversation/i }))
    const link = screen.getByText('Download photos (ZIP)').closest('a')
    expect(link?.href).toContain('/api/export/photos')
  })

  it('1:1 chat: photos link does not include chat= param', () => {
    renderDropdown('bob@example.com', false)
    fireEvent.click(screen.getByRole('button', { name: /export conversation/i }))
    const link = screen.getByText('Download photos (ZIP)').closest('a')
    expect(link?.href).not.toContain('chat=')
  })

  // ---- Group chat URL params ----

  it('group chat: links use chat= query param', () => {
    renderDropdown('My Group', true)
    fireEvent.click(screen.getByRole('button', { name: /export conversation/i }))
    const jsonLink = screen.getByText('Export as JSON').closest('a')
    expect(jsonLink?.href).toContain('chat=My%20Group')
  })

  it('group chat: links do not include handle= param', () => {
    renderDropdown('My Group', true)
    fireEvent.click(screen.getByRole('button', { name: /export conversation/i }))
    const jsonLink = screen.getByText('Export as JSON').closest('a')
    expect(jsonLink?.href).not.toContain('handle=')
  })

  it('group chat: photos link uses chat= param', () => {
    renderDropdown('My Group', true)
    fireEvent.click(screen.getByRole('button', { name: /export conversation/i }))
    const link = screen.getByText('Download photos (ZIP)').closest('a')
    expect(link?.href).toContain('chat=My%20Group')
  })

  // ---- Download attribute ----

  it('all menu links have the download attribute', () => {
    renderDropdown()
    fireEvent.click(screen.getByRole('button', { name: /export conversation/i }))
    const items = screen.getAllByRole('menuitem')
    expect(items).toHaveLength(4)
    for (const item of items) {
      expect(item.hasAttribute('download')).toBe(true)
    }
  })

  // ---- Close behaviour ----

  it('clicking a menu item closes the menu', () => {
    renderDropdown()
    fireEvent.click(screen.getByRole('button', { name: /export conversation/i }))
    fireEvent.click(screen.getByText('Export as JSON'))
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('mousedown outside the dropdown closes the menu', () => {
    renderDropdown()
    fireEvent.click(screen.getByRole('button', { name: /export conversation/i }))
    expect(screen.getByRole('menu')).toBeTruthy()

    // Simulate clicking outside by dispatching mousedown on the document body
    fireEvent.mouseDown(document.body)
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('mousedown inside the dropdown does not close the menu', () => {
    renderDropdown()
    fireEvent.click(screen.getByRole('button', { name: /export conversation/i }))
    const menu = screen.getByRole('menu')
    fireEvent.mouseDown(menu)
    expect(screen.getByRole('menu')).toBeTruthy()
  })
})
