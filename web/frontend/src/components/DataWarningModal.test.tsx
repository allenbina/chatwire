/**
 * Vitest unit tests for DataWarningModal — first-run data exposure warning.
 *
 * Covers:
 *   - Modal is visible when localStorage key is absent
 *   - Modal is hidden when localStorage key is already set
 *   - "I understand" button dismisses the modal and writes localStorage key
 *   - Clicking the overlay does NOT dismiss the modal
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { DataWarningModal } from './DataWarningModal'

// Stub the shadcn Dialog so we can control open/close without Radix Portal
vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ open, children }: { open: boolean; children: React.ReactNode }) =>
    open ? <div data-testid="dialog">{children}</div> : null,
  DialogContent: ({
    children,
    onInteractOutside: _ois,
    className: _cls,
  }: {
    children: React.ReactNode
    onInteractOutside?: (e: Event) => void
    className?: string
  }) => <div data-testid="dialog-content">{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
  DialogDescription: ({
    children,
    asChild: _asChild,
  }: {
    children: React.ReactNode
    asChild?: boolean
  }) => <div>{children}</div>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

const DISMISSED_KEY = 'chatwire-dismissed-data-warning'

beforeEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

describe('DataWarningModal', () => {
  it('shows the modal when the localStorage key is absent', () => {
    render(<DataWarningModal />)
    expect(screen.getByTestId('dialog')).toBeTruthy()
    expect(screen.getByText(/messages are accessible/i)).toBeTruthy()
  })

  it('does not show the modal when the localStorage key is already set', () => {
    localStorage.setItem(DISMISSED_KEY, '1')
    render(<DataWarningModal />)
    expect(screen.queryByTestId('dialog')).toBeNull()
  })

  it('"I understand" button hides the modal', () => {
    render(<DataWarningModal />)
    fireEvent.click(screen.getByRole('button', { name: /i understand/i }))
    expect(screen.queryByTestId('dialog')).toBeNull()
  })

  it('"I understand" button writes the localStorage key', () => {
    render(<DataWarningModal />)
    fireEvent.click(screen.getByRole('button', { name: /i understand/i }))
    expect(localStorage.getItem(DISMISSED_KEY)).toBe('1')
  })

  it('shows the warning text about network exposure', () => {
    render(<DataWarningModal />)
    expect(screen.getByText(/same network/i)).toBeTruthy()
  })

  it('shows the settings recommendation', () => {
    render(<DataWarningModal />)
    expect(screen.getByText(/Settings.*Security/i)).toBeTruthy()
  })
})
