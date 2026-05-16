/**
 * WhatsApp-style emoji picker — no external libraries.
 *
 * Layout:
 *  - Category tab bar (emoji icons)
 *  - Search input
 *  - Scrollable emoji grid with sticky section headers
 *  - Recently-used section (localStorage-backed)
 */

import { useState, useRef, useCallback, useEffect, useMemo } from 'react'
import { CATEGORIES, EMOJI_SEARCH } from './emoji-data'

const RECENT_KEY = 'chatwire:recent-emojis'
const MAX_RECENT = 24
const COLS = 8

interface EmojiPickerProps {
  onSelect: (emoji: string) => void
  /** Width in px. Default 350. */
  width?: number
  /** Height in px. Default 380. */
  height?: number
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function loadRecent(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (Array.isArray(parsed)) return parsed.filter((e): e is string => typeof e === 'string').slice(0, MAX_RECENT)
  } catch { /* ignore corrupt data */ }
  return []
}

function saveRecent(emojis: string[]) {
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(emojis.slice(0, MAX_RECENT)))
  } catch { /* quota exceeded — ignore */ }
}

function addToRecent(emoji: string): string[] {
  const prev = loadRecent()
  const next = [emoji, ...prev.filter((e) => e !== emoji)].slice(0, MAX_RECENT)
  saveRecent(next)
  return next
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function EmojiPicker({ onSelect, width = 350, height = 380 }: EmojiPickerProps) {
  const [query, setQuery] = useState('')
  const [recent, setRecent] = useState(loadRecent)
  const scrollRef = useRef<HTMLDivElement>(null)
  const sectionRefs = useRef<Map<string, HTMLDivElement>>(new Map())

  // Sync recent from storage on mount (in case another tab changed it)
  useEffect(() => { setRecent(loadRecent()) }, [])

  // --- Search ---
  const searchResults = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return null
    const matched = new Set<string>()
    for (const [keyword, emojis] of EMOJI_SEARCH) {
      if (keyword.startsWith(q)) {
        for (const e of emojis) matched.add(e)
      }
    }
    return [...matched]
  }, [query])

  const isSearching = searchResults !== null

  // --- Select handler ---
  const handleSelect = useCallback((emoji: string) => {
    setRecent(addToRecent(emoji))
    onSelect(emoji)
  }, [onSelect])

  // --- Scroll to category ---
  const scrollToCategory = useCallback((id: string) => {
    const el = sectionRefs.current.get(id)
    if (el && scrollRef.current) {
      // Offset by a small amount so the header is visible
      const container = scrollRef.current
      const top = el.offsetTop - container.offsetTop
      container.scrollTo({ top, behavior: 'smooth' })
    }
  }, [])

  // Build the "all categories" list, prepending recent if applicable
  const showRecent = !isSearching && recent.length > 0
  const allCategories = useMemo(() => {
    if (!showRecent) return CATEGORIES
    return [
      { id: 'recent', icon: '🕐', label: 'Recently Used', emojis: recent },
      ...CATEGORIES,
    ]
  }, [showRecent, recent])

  const tabCategories = useMemo(() => {
    const tabs = CATEGORIES.map((c) => ({ id: c.id, icon: c.icon }))
    if (showRecent) tabs.unshift({ id: 'recent', icon: '🕐' })
    return tabs
  }, [showRecent])

  // --- Ref setter ---
  const setSectionRef = useCallback((id: string, el: HTMLDivElement | null) => {
    if (el) sectionRefs.current.set(id, el)
    else sectionRefs.current.delete(id)
  }, [])

  return (
    <div style={{ width, height }} className="flex flex-col">
      {/* ── Category tabs ── */}
      <div className="flex items-center gap-0.5 px-1.5 py-1 border-b border-border/40 overflow-x-auto shrink-0">
        {tabCategories.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => { setQuery(''); scrollToCategory(tab.id) }}
            className="flex items-center justify-center shrink-0 w-8 h-8 text-base rounded-lg hover:bg-accent transition-colors text-muted-foreground"
            aria-label={tab.id}
          >
            {tab.icon}
          </button>
        ))}
      </div>

      {/* ── Search input ── */}
      <div className="px-2 py-1.5 shrink-0">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search emojis..."
          className="w-full bg-input border border-border text-foreground placeholder:text-muted-foreground rounded-lg px-2.5 py-1.5 text-sm outline-none focus:ring-1 focus:ring-ring"
        />
      </div>

      {/* ── Scrollable grid area ── */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto overflow-x-hidden px-1.5 pb-1">
        {isSearching ? (
          /* ── Search results (flat) ── */
          searchResults.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6">No emojis found</p>
          ) : (
            <div
              className="grid gap-0.5"
              style={{ gridTemplateColumns: `repeat(${COLS}, 1fr)` }}
            >
              {searchResults.map((emoji) => (
                <EmojiButton key={emoji} emoji={emoji} onSelect={handleSelect} />
              ))}
            </div>
          )
        ) : (
          /* ── Categorized view ── */
          allCategories.map((cat) => (
            <div key={cat.id} ref={(el) => setSectionRef(cat.id, el)}>
              <div className="sticky top-0 z-10 text-xs font-semibold text-muted-foreground py-1 px-1 bg-[var(--reaction-panel-bg,transparent)]">
                {cat.label}
              </div>
              <div
                className="grid gap-0.5"
                style={{ gridTemplateColumns: `repeat(${COLS}, 1fr)` }}
              >
                {cat.emojis.map((emoji) => (
                  <EmojiButton key={emoji} emoji={emoji} onSelect={handleSelect} />
                ))}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Emoji button (extracted to keep the grid render lean)
// ---------------------------------------------------------------------------

function EmojiButton({ emoji, onSelect }: { emoji: string; onSelect: (e: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onSelect(emoji)}
      className="flex items-center justify-center rounded-lg hover:bg-accent transition-colors leading-none aspect-square"
      style={{ fontSize: '1.75rem' }}
    >
      {emoji}
    </button>
  )
}
