/**
 * Unified reaction + action popover panel.
 *
 * Replaces the old HoverActionBar with a Radix Popover that opens on
 * hover (desktop, 200ms) or long-press (mobile, 500ms).
 *
 * Layout:
 *  - Quick reactions row: large tappable emoji buttons
 *  - [+] button to expand the full emoji picker inline
 *  - Action rows: Copy, Reply, Edit (fromMe+ventura), Unsend (fromMe+ventura)
 */
import { useState, useRef, useCallback, useEffect, type ReactNode } from 'react'
import { toast } from 'sonner'
import * as PopoverPrimitive from '@radix-ui/react-popover'
import type { Message } from '../api'
import { sendTapback, unsendMessage, editMessage } from '../api'
import { EmojiPicker } from './emoji'

const QUICK_REACTIONS = ['\u2764\uFE0F', '\uD83D\uDC4D', '\uD83D\uDC4E', '\uD83D\uDE02', '\u203C\uFE0F', '\u2753'] as const

interface ReactionPanelProps {
  msg: Message
  fromMe: boolean
  ventura: boolean
  onReply: () => void
  /** Whether this is a pending/optimistic message (disables the panel). */
  pending?: boolean
  children: ReactNode
}

export function ReactionPanel({
  msg,
  fromMe,
  ventura,
  onReply,
  pending = false,
  children,
}: ReactionPanelProps) {
  const [open, setOpen] = useState(false)
  const [showPicker, setShowPicker] = useState(false)
  const [editMode, setEditMode] = useState(false)
  const [editText, setEditText] = useState(msg.text || '')

  // Hover timers (desktop)
  const hoverOpenTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const hoverCloseTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Long-press timer (mobile)
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Track recent touches — suppresses synthetic mouse events on mobile.
  // Mobile browsers fire mouseenter ~300ms after touchend; without this guard
  // the 200ms hover timer opens the panel on every plain tap.
  const recentTouchRef = useRef(false)
  const recentTouchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const cleanupRef = useRef<(() => void) | null>(null)

  const closePanel = useCallback(() => {
    setOpen(false)
    setShowPicker(false)
    setEditMode(false)
  }, [])

  // Close on outside tap or scroll
  useEffect(() => {
    if (!open) return
    // Small delay so the opening touch doesn't immediately dismiss
    const timer = setTimeout(() => {
      function handleOutsideTouch(e: TouchEvent | MouseEvent) {
        // If the tap is inside the popover content, let it through
        const target = e.target as HTMLElement
        if (target.closest?.('[data-reaction-panel-content]')) return
        closePanel()
      }
      function handleScroll() { closePanel() }
      document.addEventListener('touchstart', handleOutsideTouch, { passive: true })
      document.addEventListener('mousedown', handleOutsideTouch)
      window.addEventListener('scroll', handleScroll, { capture: true, passive: true })
      cleanupRef.current = () => {
        document.removeEventListener('touchstart', handleOutsideTouch)
        document.removeEventListener('mousedown', handleOutsideTouch)
        window.removeEventListener('scroll', handleScroll, { capture: true })
      }
    }, 100)
    return () => {
      clearTimeout(timer)
      cleanupRef.current?.()
      cleanupRef.current = null
    }
  }, [open, closePanel])

  // --- Desktop hover handlers (suppressed after touch) ---
  function handleMouseEnter() {
    if (pending || recentTouchRef.current) return
    if (hoverCloseTimer.current) {
      clearTimeout(hoverCloseTimer.current)
      hoverCloseTimer.current = null
    }
    hoverOpenTimer.current = setTimeout(() => setOpen(true), 200)
  }

  function handleMouseLeave() {
    if (recentTouchRef.current) return
    if (hoverOpenTimer.current) {
      clearTimeout(hoverOpenTimer.current)
      hoverOpenTimer.current = null
    }
    hoverCloseTimer.current = setTimeout(() => {
      // Don't close if user is in edit mode
      if (!editMode) closePanel()
    }, 300)
  }

  // --- Mobile long-press handlers ---
  function handleTouchStart() {
    if (pending) return
    // Mark that a touch happened — suppress synthetic mouse events for 500ms
    recentTouchRef.current = true
    if (recentTouchTimer.current) clearTimeout(recentTouchTimer.current)
    recentTouchTimer.current = setTimeout(() => { recentTouchRef.current = false }, 500)
    longPressTimer.current = setTimeout(() => setOpen(true), 500)
  }

  function handleTouchEnd() {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current)
      longPressTimer.current = null
    }
  }

  // --- Actions ---
  async function handleTapback(emoji: string) {
    try {
      await sendTapback(msg.rowid, emoji)
    } catch {
      toast.error('Tapback failed — check macOS version and Messages.app access.')
    }
    closePanel()
  }

  function handleCopy() {
    if (!msg.text) { closePanel(); return }
    // Clipboard API requires secure context; fall back to execCommand
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(msg.text).then(
        () => toast.success('Copied'),
        () => fallbackCopy(msg.text),
      )
    } else {
      fallbackCopy(msg.text)
    }
    closePanel()
  }

  function fallbackCopy(text: string) {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    try {
      document.execCommand('copy')
      toast.success('Copied')
    } catch {
      toast.error('Copy failed')
    }
    document.body.removeChild(ta)
  }

  function handleReply() {
    onReply()
    closePanel()
  }

  async function handleUnsend() {
    if (!confirm('Unsend this message? It will be retracted for everyone.')) return
    try {
      await unsendMessage(msg.rowid)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Unsend failed')
    }
    closePanel()
  }

  async function handleEditSubmit() {
    const trimmed = editText.trim()
    if (!trimmed || trimmed === msg.text) {
      setEditMode(false)
      return
    }
    try {
      await editMessage(msg.rowid, trimmed)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Edit failed')
    }
    setEditMode(false)
    closePanel()
  }

  function handleEditClick() {
    setEditText(msg.text || '')
    setEditMode(true)
  }

  // Keep popover content alive on hover so the mouse can move from bubble to panel
  function handleContentMouseEnter() {
    if (hoverCloseTimer.current) {
      clearTimeout(hoverCloseTimer.current)
      hoverCloseTimer.current = null
    }
  }

  function handleContentMouseLeave() {
    hoverCloseTimer.current = setTimeout(() => {
      if (!editMode) closePanel()
    }, 300)
  }

  // On macOS < 13 (Ventura), tapback sending / edit / unsend are unavailable,
  // but Copy and Reply still work — so we keep the panel and just hide
  // the emoji row + edit/unsend actions (gated individually below).

  return (
    <PopoverPrimitive.Root open={open} onOpenChange={(v) => { if (!v) closePanel() }}>
      <PopoverPrimitive.Anchor asChild>
        <div
          onMouseEnter={handleMouseEnter}
          onMouseLeave={handleMouseLeave}
          onTouchStart={handleTouchStart}
          onTouchEnd={handleTouchEnd}
          onTouchMove={handleTouchEnd}
        >
          {children}
        </div>
      </PopoverPrimitive.Anchor>

      {open && (
        <PopoverPrimitive.Portal>
          <PopoverPrimitive.Content
            data-reaction-panel-content
            side="top"
            align={fromMe ? 'end' : 'start'}
            collisionPadding={16}
            sideOffset={4}
            onMouseEnter={handleContentMouseEnter}
            onMouseLeave={handleContentMouseLeave}
            onOpenAutoFocus={(e) => e.preventDefault()}
            className="z-50 rounded-xl border shadow-md overflow-hidden reaction-panel-enter"
            style={{
              backgroundColor: 'var(--reaction-panel-bg)',
              color: 'var(--reaction-panel-text)',
              borderColor: 'var(--reaction-panel-border)',
            }}
          >
            {editMode ? (
              /* --- Edit mode --- */
              <div className="p-2 flex gap-1 min-w-[260px]">
                <input
                  autoFocus
                  className="flex-1 rounded-lg border border-border bg-input px-2 py-1 text-foreground min-w-0"
                  style={{ fontSize: 'var(--font-size-message)' }}
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') { e.preventDefault(); handleEditSubmit() }
                    if (e.key === 'Escape') { setEditMode(false); closePanel() }
                  }}
                />
                <button
                  type="button"
                  onClick={handleEditSubmit}
                  className="px-2 py-1 rounded-lg bg-primary text-primary-foreground text-xs hover:opacity-90"
                >
                  Save
                </button>
                <button
                  type="button"
                  onClick={() => { setEditMode(false); closePanel() }}
                  className="px-2 py-1 rounded-lg bg-muted text-muted-foreground text-xs hover:text-foreground"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <>
                {ventura && showPicker ? (
                  /* --- Full emoji picker (replaces entire panel) --- */
                  <div>
                    <div className="flex items-center justify-between px-3 pt-2 pb-1">
                      <span className="text-xs text-muted-foreground font-medium">Pick a reaction</span>
                      <button
                        type="button"
                        onClick={() => setShowPicker(false)}
                        className="text-muted-foreground hover:text-foreground text-sm px-1"
                        aria-label="Back"
                      >
                        ✕
                      </button>
                    </div>
                    <EmojiPicker
                      onSelect={(emoji) => { handleTapback(emoji); setShowPicker(false) }}
                      width={350}
                      height={350}
                    />
                  </div>
                ) : (
                <>
                {/* --- Quick reactions row (macOS 13+ only) --- */}
                {ventura && (
                <div
                  className="grid gap-0.5 px-1.5 pt-2 pb-1"
                  style={{ gridTemplateColumns: 'repeat(8, 1fr)' }}
                >
                  {QUICK_REACTIONS.map((emoji) => (
                    <button
                      key={emoji}
                      type="button"
                      onClick={() => handleTapback(emoji)}
                      className="flex items-center justify-center rounded-lg hover:bg-accent transition-colors leading-none aspect-square"
                      style={{ fontSize: '1.75rem' }}
                      aria-label={`React with ${emoji}`}
                    >
                      {emoji}
                    </button>
                  ))}
                  {/* More reactions — opens full emoji picker */}
                  <button
                    type="button"
                    onClick={() => setShowPicker(true)}
                    className="flex items-center justify-center rounded-lg hover:bg-accent transition-colors leading-none aspect-square"
                    style={{ fontSize: '1.75rem' }}
                    aria-label="More reactions"
                  >
                    ☺
                  </button>
                  {/* Empty 8th cell for grid alignment */}
                </div>
                )}

                {/* --- Action rows --- */}
                <div className="flex flex-col py-1 min-w-[160px]" style={{ fontSize: 'var(--font-size-message)' }}>
                  {/* Copy */}
                  {msg.text && (
                    <button
                      type="button"
                      onClick={handleCopy}
                      className="flex items-center gap-2 px-3 py-1.5 hover:bg-accent transition-colors text-left"
                    >
                      <svg className="shrink-0" style={{ width: 'var(--icon-size-md)', height: 'var(--icon-size-md)' }} fill="none" stroke="currentColor" strokeWidth="var(--icon-stroke)" viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                      </svg>
                      Copy
                    </button>
                  )}

                  {/* Reply */}
                  <button
                    type="button"
                    onClick={handleReply}
                    className="flex items-center gap-2 px-3 py-1.5 hover:bg-accent transition-colors text-left"
                  >
                    <svg className="shrink-0" style={{ width: 'var(--icon-size-md)', height: 'var(--icon-size-md)' }} fill="none" stroke="currentColor" strokeWidth="var(--icon-stroke)" viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="9 17 4 12 9 7" /><path d="M20 18v-2a4 4 0 0 0-4-4H4" />
                    </svg>
                    Reply
                  </button>

                  {/* Edit — fromMe + ventura only */}
                  {fromMe && ventura && (
                    <button
                      type="button"
                      onClick={handleEditClick}
                      className="flex items-center gap-2 px-3 py-1.5 hover:bg-accent transition-colors text-left"
                    >
                      <svg className="shrink-0" style={{ width: 'var(--icon-size-md)', height: 'var(--icon-size-md)' }} fill="none" stroke="currentColor" strokeWidth="var(--icon-stroke)" viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                      </svg>
                      Edit
                    </button>
                  )}

                  {/* Unsend — fromMe + ventura only */}
                  {fromMe && ventura && (
                    <button
                      type="button"
                      onClick={handleUnsend}
                      className="flex items-center gap-2 px-3 py-1.5 text-destructive hover:bg-destructive/10 transition-colors text-left"
                    >
                      <svg className="shrink-0" style={{ width: 'var(--icon-size-md)', height: 'var(--icon-size-md)' }} fill="none" stroke="currentColor" strokeWidth="var(--icon-stroke)" viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                      </svg>
                      Unsend
                    </button>
                  )}
                </div>

                {/* --- Existing reactions summary (at bottom, grouped by type) --- */}
                {msg.tapbacks && msg.tapbacks.length > 0 && (
                  <>
                    <div className="border-t border-border/40 mx-2" />
                    <div className="px-3 py-1.5" style={{ fontSize: 'var(--font-size-message)' }}>
                      {msg.tapbacks.map((tb) => (
                        <div key={tb.type} className="py-1">
                          <div className="flex items-center gap-1.5 font-medium">
                            <span>{tb.type}</span>
                            <span>{tb.type === '\u2764\uFE0F' ? 'Loved' : tb.type === '\uD83D\uDC4D' ? 'Liked' : tb.type === '\uD83D\uDC4E' ? 'Disliked' : tb.type === '\uD83D\uDE02' ? 'Laughed' : tb.type === '\u203C\uFE0F' ? 'Emphasized' : tb.type === '\u2753' ? 'Questioned' : 'Reacted'}</span>
                          </div>
                          <div className="ml-6 text-muted-foreground">
                            {tb.senders.map((s, i) => (
                              <div key={i}>{s.name}</div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                )}
                </>
                )}
              </>
            )}
          </PopoverPrimitive.Content>
        </PopoverPrimitive.Portal>
      )}
    </PopoverPrimitive.Root>
  )
}
