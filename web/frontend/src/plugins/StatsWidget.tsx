/**
 * StatsWidget — sidebar panel plugin component.
 *
 * Registered in the 'sidebar.panel' slot by main.tsx when the stats
 * integration is enabled. Fetches a compact stats summary from
 * GET /api/ui/stats and renders sent/received totals + top 3 contacts.
 *
 * Falls back gracefully when the integration is disabled or the API
 * returns an error.
 */
import { useQuery } from '@tanstack/react-query'

interface StatsData {
  enabled: boolean
  date_range?: string
  sent_total?: number
  received_total?: number
  top_contacts?: Array<{ name: string; handle: string; count: number }>
}

async function fetchStats(): Promise<StatsData> {
  const r = await fetch('/api/ui/stats', { credentials: 'same-origin' })
  if (!r.ok) throw new Error(`Stats API error ${r.status}`)
  return r.json()
}

export function StatsWidget() {
  const { data, isLoading, isError } = useQuery<StatsData>({
    queryKey: ['stats-widget'],
    queryFn: fetchStats,
    staleTime: 5 * 60_000,   // refresh every 5 min
    retry: 1,
  })

  // Don't render anything if stats are disabled or unavailable
  if (isLoading || isError || !data?.enabled) return null

  const sent = data.sent_total ?? 0
  const received = data.received_total ?? 0
  const total = sent + received
  const sentPct = total > 0 ? Math.round((sent / total) * 100) : 0
  const top3 = (data.top_contacts ?? []).slice(0, 3)
  const rangeLabel: Record<string, string> = {
    '30d': 'Last 30 days',
    '90d': 'Last 90 days',
    '365d': 'Last year',
    'all': 'All time',
  }

  return (
    <div
      className="border-t border-[--color-border] px-3 py-3 text-xs text-[--color-text-muted]"
      role="complementary"
      aria-label="Message statistics"
    >
      {/* Header row */}
      <div className="flex items-center justify-between mb-2">
        <span className="font-semibold text-[--color-text-secondary] uppercase tracking-wider text-[10px]">
          Stats
        </span>
        <a
          href="/plugins/stats/report"
          target="_blank"
          rel="noopener noreferrer"
          className="text-[--color-info] hover:text-[--color-accent] transition-colors"
          aria-label="Open full stats report"
        >
          ↗
        </a>
      </div>

      {/* Sent / received bar */}
      <p className="text-[10px] text-[--color-text-muted] mb-1">
        {rangeLabel[data.date_range ?? '30d'] ?? data.date_range} · {total.toLocaleString()} msgs
      </p>
      {total > 0 && (
        <div className="flex h-1.5 rounded-full overflow-hidden bg-[--color-bg-tertiary] mb-2">
          <div
            className="bg-[--color-accent] h-full transition-all"
            style={{ width: `${sentPct}%` }}
            aria-label={`${sentPct}% sent`}
          />
        </div>
      )}
      <div className="flex justify-between text-[10px] mb-3">
        <span>↑ {sent.toLocaleString()} sent</span>
        <span>↓ {received.toLocaleString()} received</span>
      </div>

      {/* Top contacts */}
      {top3.length > 0 && (
        <div className="space-y-1">
          {top3.map((c) => (
            <div key={c.handle} className="flex items-center justify-between gap-1">
              <span className="truncate max-w-[120px]" title={c.handle}>
                {c.name}
              </span>
              <span className="shrink-0 font-mono text-[--color-text-primary]">
                {c.count.toLocaleString()}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
