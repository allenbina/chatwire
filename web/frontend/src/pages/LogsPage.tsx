/**
 * Structured log viewer — Phase 19 Chunk 5.
 *
 * Streams new log lines via SSE from /api/ui/logs/stream and loads
 * history from /api/ui/logs.  Supports source + level filters, text
 * search, pause/resume, export, and auto-scroll.
 *
 * Route: /logs  (lazy-loaded from App.tsx)
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { ChevronLeft } from 'lucide-react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Layout } from '../components/Layout'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type LogLevel = 'info' | 'warn' | 'error'

interface LogEntry {
  ts: string
  source: string
  level: LogLevel
  msg: string
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const LEVEL_COLOR: Record<LogLevel, string> = {
  info: 'text-foreground',
  warn: 'text-yellow-400',
  error: 'text-red-400',
}

const LEVEL_BADGE: Record<LogLevel, string> = {
  info: 'bg-muted text-muted-foreground',
  warn: 'bg-yellow-500/10 text-yellow-400',
  error: 'bg-red-500/10 text-red-400',
}

const LEVELS: LogLevel[] = ['info', 'warn', 'error']
const HISTORY_LIMIT = 500

// ---------------------------------------------------------------------------
// Source selector option
// ---------------------------------------------------------------------------

function useLogSources(entries: LogEntry[]): string[] {
  const sources = new Set<string>()
  for (const e of entries) {
    if (e.source) sources.add(e.source)
  }
  return ['all', ...Array.from(sources).sort()]
}

// ---------------------------------------------------------------------------
// Filter predicate
// ---------------------------------------------------------------------------

const LEVEL_ORDER: Record<string, number> = { info: 0, warn: 1, error: 2 }

function matchesFilter(
  entry: LogEntry,
  source: string,
  minLevel: string,
  search: string,
): boolean {
  if (source && source !== 'all' && entry.source !== source) return false
  if (minLevel && minLevel !== 'all') {
    if ((LEVEL_ORDER[entry.level] ?? 0) < (LEVEL_ORDER[minLevel] ?? 0)) return false
  }
  if (search) {
    const q = search.toLowerCase()
    if (
      !entry.msg.toLowerCase().includes(q) &&
      !entry.source.toLowerCase().includes(q)
    ) return false
  }
  return true
}

// ---------------------------------------------------------------------------
// LogsPage
// ---------------------------------------------------------------------------

export function LogsPage() {
  const [allEntries, setAllEntries] = useState<LogEntry[]>([])
  const [source, setSource] = useState('all')
  const [minLevel, setMinLevel] = useState('all')
  const [search, setSearch] = useState('')
  const [paused, setPaused] = useState(false)
  const [connected, setConnected] = useState(false)

  const pausedRef = useRef(paused)
  pausedRef.current = paused

  const parentRef = useRef<HTMLDivElement>(null)
  const atBottomRef = useRef(true)

  // -------------------------------------------------------------------------
  // Load history on mount
  // -------------------------------------------------------------------------

  useEffect(() => {
    const params = new URLSearchParams({ limit: String(HISTORY_LIMIT) })
    fetch(`/api/ui/logs?${params}`, { credentials: 'same-origin' })
      .then((r) => r.json())
      .then((d) => {
        if (Array.isArray(d.entries)) {
          setAllEntries(d.entries)
        }
      })
      .catch(() => {/* silently ignore on startup */})
  }, [])

  // -------------------------------------------------------------------------
  // SSE stream for live entries
  // -------------------------------------------------------------------------

  useEffect(() => {
    const es = new EventSource('/api/ui/logs/stream', { withCredentials: true })

    es.onopen = () => setConnected(true)
    es.onerror = () => setConnected(false)

    es.onmessage = (ev) => {
      if (pausedRef.current) return
      try {
        const entry: LogEntry = JSON.parse(ev.data)
        setAllEntries((prev) => {
          // Keep at most 2000 entries in memory
          const next = prev.length >= 2000 ? prev.slice(-1999) : prev
          return [...next, entry]
        })
      } catch {
        // ignore malformed SSE data
      }
    }

    return () => {
      es.close()
      setConnected(false)
    }
  }, []) // single SSE connection for the page lifetime

  // -------------------------------------------------------------------------
  // Filtered view
  // -------------------------------------------------------------------------

  const filtered = allEntries.filter((e) => matchesFilter(e, source, minLevel, search))
  const sources = useLogSources(allEntries)

  // -------------------------------------------------------------------------
  // Virtualiser
  // -------------------------------------------------------------------------

  const virtualizer = useVirtualizer({
    count: filtered.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 36,
    overscan: 20,
  })

  // -------------------------------------------------------------------------
  // Auto-scroll to bottom when new entries arrive (unless paused/scrolled up)
  // -------------------------------------------------------------------------

  const prevCountRef = useRef(filtered.length)
  useEffect(() => {
    if (!paused && atBottomRef.current && filtered.length > prevCountRef.current) {
      virtualizer.scrollToIndex(filtered.length - 1, { align: 'end' })
    }
    prevCountRef.current = filtered.length
  }, [filtered.length, paused, virtualizer])

  // Track whether user is at the bottom
  const handleScroll = useCallback(() => {
    const el = parentRef.current
    if (!el) return
    const threshold = 60
    atBottomRef.current = el.scrollTop + el.clientHeight >= el.scrollHeight - threshold
  }, [])

  // -------------------------------------------------------------------------
  // Export
  // -------------------------------------------------------------------------

  const handleExport = useCallback(() => {
    const text = filtered
      .map((e) => `[${e.ts}] [${e.level.toUpperCase()}] [${e.source}] ${e.msg}`)
      .join('\n')
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `chatwire-logs-${new Date().toISOString().slice(0, 10)}.log`
    a.click()
    URL.revokeObjectURL(url)
  }, [filtered])

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <Layout>
      <div className="flex flex-col h-full">
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border bg-background flex-shrink-0">
          <Link
            to="/"
            className="md:hidden p-2 -ml-3 -my-1 text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Back to conversations"
          >
            <ChevronLeft className="w-6 h-6" />
          </Link>
          <h1 className="text-sm font-semibold text-foreground flex-1">Logs</h1>
          <span
            className={cn(
              'text-[10px] font-mono px-1.5 py-0.5 rounded',
              connected ? 'bg-green-500/10 text-green-400' : 'bg-muted text-muted-foreground',
            )}
            title={connected ? 'Live stream connected' : 'Disconnected'}
          >
            {connected ? '● live' : allEntries.length > 0 ? '○ history' : '○ connecting…'}
          </span>
        </div>

        {/* Filter bar */}
        <div className="flex flex-wrap items-center gap-2 px-4 py-2 border-b border-border bg-background flex-shrink-0">
          {/* Source selector */}
          <select
            value={source}
            onChange={(e) => setSource(e.target.value)}
            className="text-xs px-2 py-1 border border-border rounded bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
          >
            {sources.map((s) => (
              <option key={s} value={s}>{s === 'all' ? 'All sources' : s}</option>
            ))}
          </select>

          {/* Level selector */}
          <select
            value={minLevel}
            onChange={(e) => setMinLevel(e.target.value)}
            className="text-xs px-2 py-1 border border-border rounded bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
          >
            <option value="all">All levels</option>
            {LEVELS.map((l) => (
              <option key={l} value={l}>{l}</option>
            ))}
          </select>

          {/* Text search */}
          <Input
            type="search"
            placeholder="Search…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="text-xs h-7 w-40"
          />

          <div className="flex items-center gap-1 ml-auto">
            <Button
              size="sm"
              variant="outline"
              className="text-xs h-7"
              onClick={() => setPaused((p) => !p)}
            >
              {paused ? '▶ Resume' : '⏸ Pause'}
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="text-xs h-7"
              onClick={handleExport}
              disabled={filtered.length === 0}
            >
              Export
            </Button>
          </div>
        </div>

        {/* Paused notice */}
        {paused && (
          <div className="bg-yellow-500/10 text-yellow-400 text-[11px] px-4 py-1 text-center flex-shrink-0">
            Stream paused — new entries are buffered. Press Resume to continue.
          </div>
        )}

        {/* Log list (virtualised) */}
        <div
          ref={parentRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto overscroll-contain font-mono text-xs"
        >
          {filtered.length === 0 ? (
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
              {allEntries.length === 0 ? 'No log entries yet.' : 'No entries match the current filter.'}
            </div>
          ) : (
            <div
              style={{ height: `${virtualizer.getTotalSize()}px`, position: 'relative' }}
            >
              {virtualizer.getVirtualItems().map((item) => {
                const entry = filtered[item.index]
                return (
                  <div
                    key={item.key}
                    data-index={item.index}
                    ref={virtualizer.measureElement}
                    style={{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      width: '100%',
                      transform: `translateY(${item.start}px)`,
                    }}
                    className={cn(
                      'flex items-start gap-2 px-4 py-1 border-b border-border/30 hover:bg-muted/30',
                      LEVEL_COLOR[entry.level],
                    )}
                  >
                    {/* Timestamp */}
                    <span className="text-muted-foreground flex-shrink-0 w-[76px] text-[10px] pt-0.5">
                      {entry.ts.slice(11, 19)}
                    </span>

                    {/* Level badge */}
                    <span
                      className={cn(
                        'flex-shrink-0 w-11 text-center text-[10px] px-1 py-0.5 rounded',
                        LEVEL_BADGE[entry.level],
                      )}
                    >
                      {entry.level}
                    </span>

                    {/* Source */}
                    <span className="flex-shrink-0 w-20 truncate text-muted-foreground text-[10px] pt-0.5">
                      {entry.source}
                    </span>

                    {/* Message */}
                    <span className="flex-1 break-words whitespace-pre-wrap min-w-0">
                      {entry.msg}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Footer: entry count */}
        <div className="px-4 py-1 border-t border-border bg-background flex-shrink-0 text-[10px] text-muted-foreground font-mono">
          {filtered.length.toLocaleString()} {filtered.length !== allEntries.length ? `of ${allEntries.length.toLocaleString()} ` : ''}entries
        </div>
      </div>
    </Layout>
  )
}
