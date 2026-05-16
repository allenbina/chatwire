/**
 * Two-pane shell: fixed sidebar on the left, scrollable main area on
 * the right. On mobile (< 768px), uses stack-based full-screen navigation:
 * conversations list is the home screen, sub-pages render full-screen with
 * a back button in their header. See docs/MOBILE_NAV_SPEC.md.
 *
 * Accessibility:
 *  - Skip-nav link at top (visible on focus via .sr-only:focus)
 *  - Sidebar is <nav aria-label="Conversations"> (inside ConversationList)
 *  - Main content area is <main aria-label="Chat">
 */
import { ReactNode, useState, useEffect, useRef } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { LogOut, Settings, Puzzle, Palette, ScrollText, Sun, Moon, CheckCheck, PauseCircle, Bell, TriangleAlert } from 'lucide-react'
import { useTheme } from '../hooks/useTheme'
import { usePinnedSettings } from '../hooks/usePinnedSettings'
import { useSwipeBack } from '../hooks/useSwipeBack'
import { SlidingHighlight } from './SlidingHighlight'
import { ConversationList } from './ConversationList'
import { SlotRenderer } from '../plugins/SlotRenderer'
import { useOnline } from '../hooks/useOnline'
import { UpdateBanner } from './UpdateBanner'
import { fetchConversations, markAllSeen, getFuseStatus } from '../api'

interface LayoutProps {
  children: ReactNode
}

function SidebarContent() {
  const isOnline = useOnline()
  const { themeMode, setThemeMode } = useTheme()
  const qc = useQueryClient()

  const { data: authData } = useQuery<{ has_password: boolean }>({
    queryKey: ['auth-has-password'],
    queryFn: () =>
      fetch('/api/ui/auth/has-password', { credentials: 'same-origin' }).then((r) => r.json()),
    staleTime: 60_000,
  })
  const hasPassword = authData?.has_password ?? false

  // Share the cached conversations query (no extra network request)
  const { data: convos } = useQuery({
    queryKey: ['conversations'],
    queryFn: fetchConversations,
    staleTime: 10_000,
  })
  const hasUnseen = convos?.some((c) => c.unseen) ?? false

  // Hiatus status — fetched once at mount, refreshed on window focus.
  // staleTime:Infinity prevents background polling (hiatus rarely changes).
  const { isPinned } = usePinnedSettings()

  const { data: notifData } = useQuery<{
    hiatus_enabled: boolean
    hiatus_duration_minutes: number
    hiatus_started_at: number
    reminder_enabled: boolean
    reminder_days: number
    reminder_contacts: string[]
  }>({
    queryKey: ['hiatus-status'],
    queryFn: () =>
      fetch('/api/ui/settings/notifications', { credentials: 'same-origin' }).then((r) => r.json()),
    staleTime: Infinity,
    refetchOnWindowFocus: true,
  })
  const hiatusEnabled = notifData?.hiatus_enabled ?? false
  const hiatusDurationMinutes = notifData?.hiatus_duration_minutes ?? 30
  const hiatusStartedAt = notifData?.hiatus_started_at ?? 0
  const reminderEnabled = notifData?.reminder_enabled ?? false
  const reminderDays = notifData?.reminder_days ?? 7
  const reminderContacts = notifData?.reminder_contacts ?? []

  // Track current time so the "Xm left" label updates and the timer can auto-expire.
  const [now, setNow] = useState(() => Date.now())

  const endHiatusMutation = useMutation({
    mutationFn: () => {
      const fd = new FormData()
      fd.append('hiatus_enabled', 'false')
      fd.append('hiatus_duration_minutes', String(hiatusDurationMinutes))
      return fetch('/api/settings/hiatus_settings', {
        method: 'POST',
        credentials: 'same-origin',
        body: fd,
      }).then((r) => r.json())
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['hiatus-status'] })
    },
  })

  // Keep a ref to the mutate fn so the interval closure is always fresh.
  const endHiatusMutateRef = useRef(endHiatusMutation.mutate)
  endHiatusMutateRef.current = endHiatusMutation.mutate

  // Countdown ticker: updates `now` every 30 s while hiatus is active.
  // When the timer expires, fires the end-hiatus mutation automatically.
  useEffect(() => {
    if (!hiatusEnabled || hiatusStartedAt <= 0) return
    const endsAt = hiatusStartedAt * 1000 + hiatusDurationMinutes * 60_000

    const tick = () => {
      if (Date.now() >= endsAt) {
        endHiatusMutateRef.current()
      } else {
        setNow(Date.now())
      }
    }

    tick() // run once immediately so the label appears right away
    const id = setInterval(tick, 30_000)
    return () => clearInterval(id)
  }, [hiatusEnabled, hiatusStartedAt, hiatusDurationMinutes])

  // Compute remaining minutes for the banner label (0 means no timestamp available).
  const hiatusEndsAt = hiatusStartedAt > 0
    ? hiatusStartedAt * 1000 + hiatusDurationMinutes * 60_000
    : 0
  const minutesLeft = hiatusEndsAt > 0
    ? Math.max(1, Math.ceil((hiatusEndsAt - now) / 60_000))
    : 0

  // Pinned sidebar toggle — hiatus
  const toggleHiatusMutation = useMutation({
    mutationFn: (enable: boolean) => {
      const fd = new FormData()
      fd.append('hiatus_enabled', String(enable))
      fd.append('hiatus_duration_minutes', String(hiatusDurationMinutes))
      return fetch('/api/settings/hiatus_settings', {
        method: 'POST',
        credentials: 'same-origin',
        body: fd,
      }).then((r) => r.json())
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['hiatus-status'] })
      qc.invalidateQueries({ queryKey: ['settings-notifications'] })
    },
  })

  // Pinned sidebar toggle — reminder
  const toggleReminderMutation = useMutation({
    mutationFn: (enable: boolean) => {
      const fd = new FormData()
      fd.append('reminder_enabled', String(enable))
      fd.append('reminder_days', String(reminderDays))
      fd.append('reminder_contacts', JSON.stringify(reminderContacts))
      return fetch('/api/settings/reminder_settings', {
        method: 'POST',
        credentials: 'same-origin',
        body: fd,
      }).then((r) => r.json())
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['hiatus-status'] })
      qc.invalidateQueries({ queryKey: ['settings-notifications'] })
    },
  })

  const markAllMutation = useMutation({
    mutationFn: markAllSeen,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conversations'] })
      if ('clearAppBadge' in navigator) {
        ;(navigator as Navigator & { clearAppBadge: () => Promise<void> })
          .clearAppBadge()
          .catch(() => {})
      }
    },
  })

  return (
    <div className="flex flex-col h-full bg-sidebar-bg">
      {/* Conversation list — starts immediately, no header */}
      <div className="flex-1 overflow-y-auto overscroll-contain">
        <ConversationList />
        <SlotRenderer slot="sidebar.panel" />
      </div>
      {/* Hiatus banner — shown when hiatus mode is active */}
      {hiatusEnabled && (
        <div className="px-3 py-1.5 bg-warning/10 border-t border-warning/20 flex items-center gap-1.5">
          <PauseCircle className="text-warning flex-shrink-0" style={{ width: 'var(--icon-size-sm)', height: 'var(--icon-size-sm)' }} aria-hidden="true" />
          <span className="text-xs text-warning font-medium flex-1">
            Hiatus ON{minutesLeft > 0 ? ` · ${minutesLeft}m left` : ''}
          </span>
          <button
            onClick={() => endHiatusMutation.mutate()}
            disabled={endHiatusMutation.isPending}
            className="text-xs text-warning/70 hover:text-warning underline disabled:opacity-50"
            aria-label="End hiatus mode"
          >
            End
          </button>
        </div>
      )}
      {/* Offline banner */}
      {!isOnline && (
        <div className="px-3 py-1.5 bg-destructive/10 border-t border-destructive/20 flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-destructive flex-shrink-0" aria-hidden="true" />
          <span className="text-xs text-destructive font-medium">Offline</span>
        </div>
      )}
      {/* Sidebar footer */}
      <div className="px-4 py-3 bg-card">
        <SlidingHighlight direction="horizontal" highlightClass="bg-accent rounded-lg" className="flex items-center justify-center gap-2">
          <Link
            to="/settings"
            data-slide-item
            className="p-2 rounded-lg text-muted-foreground hover:text-primary transition-colors"
            title="Settings"
            aria-label="Settings"
          >
            <Settings className="w-5 h-5" style={{ width: 'var(--icon-size-lg)', height: 'var(--icon-size-lg)' }} />
          </Link>
          <Link
            to="/plugins"
            data-slide-item
            className="p-2 rounded-lg text-muted-foreground hover:text-primary transition-colors"
            title="Plugins"
            aria-label="Plugins"
          >
            <Puzzle className="w-5 h-5" style={{ width: 'var(--icon-size-lg)', height: 'var(--icon-size-lg)' }} />
          </Link>
          <Link
            to="/settings#appearance"
            data-slide-item
            className="p-2 rounded-lg text-muted-foreground hover:text-primary transition-colors"
            title="Appearance"
            aria-label="Appearance"
          >
            <Palette className="w-5 h-5" style={{ width: 'var(--icon-size-lg)', height: 'var(--icon-size-lg)' }} />
          </Link>
          <Link
            to="/logs"
            data-slide-item
            className="p-2 rounded-lg text-muted-foreground hover:text-primary transition-colors"
            title="Logs"
            aria-label="Logs"
          >
            <ScrollText className="w-5 h-5" style={{ width: 'var(--icon-size-lg)', height: 'var(--icon-size-lg)' }} />
          </Link>
          {/* Pinned setting toggles — only rendered when that key is pinned */}
          {isPinned('hiatus_enabled') && (
            <button
              type="button"
              data-slide-item
              onClick={() => toggleHiatusMutation.mutate(!hiatusEnabled)}
              disabled={toggleHiatusMutation.isPending}
              className={`p-2 rounded-lg transition-colors ${
                hiatusEnabled
                  ? 'text-warning hover:text-warning/70'
                  : 'text-muted-foreground hover:text-primary'
              }`}
              title={hiatusEnabled ? 'Hiatus ON — click to disable' : 'Hiatus OFF — click to enable'}
              aria-label={hiatusEnabled ? 'Disable hiatus mode' : 'Enable hiatus mode'}
              aria-pressed={hiatusEnabled}
            >
              <PauseCircle className="w-4 h-4" style={{ width: 'var(--icon-size-md)', height: 'var(--icon-size-md)' }} />
            </button>
          )}
          {isPinned('reminder_enabled') && (
            <button
              type="button"
              data-slide-item
              onClick={() => toggleReminderMutation.mutate(!reminderEnabled)}
              disabled={toggleReminderMutation.isPending}
              className={`p-2 rounded-lg transition-colors ${
                reminderEnabled
                  ? 'text-success hover:text-success/70'
                  : 'text-muted-foreground hover:text-primary'
              }`}
              title={reminderEnabled ? 'Reminder ON — click to disable' : 'Reminder OFF — click to enable'}
              aria-label={reminderEnabled ? 'Disable reminders' : 'Enable reminders'}
              aria-pressed={reminderEnabled}
            >
              <Bell className="w-4 h-4" style={{ width: 'var(--icon-size-md)', height: 'var(--icon-size-md)' }} />
            </button>
          )}
          {hasUnseen && (
            <button
              type="button"
              data-slide-item
              onClick={() => markAllMutation.mutate()}
              disabled={markAllMutation.isPending}
              className="p-2 rounded-lg text-muted-foreground hover:text-primary transition-colors"
              title="Mark all read"
              aria-label="Mark all read"
            >
              <CheckCheck className="w-4 h-4" style={{ width: 'var(--icon-size-md)', height: 'var(--icon-size-md)' }} />
            </button>
          )}
          {themeMode === 'auto' && (
            <button
              type="button"
              data-slide-item
              onClick={() => {
                // Quick toggle: if OS is dark, force light; if OS is light, force dark
                const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches
                setThemeMode(isDark ? 'light' : 'dark')
              }}
              className="p-2 rounded-lg text-muted-foreground hover:text-primary transition-colors"
              title="Toggle day/night"
              aria-label="Toggle day/night"
            >
              {window.matchMedia('(prefers-color-scheme: dark)').matches
                ? <Sun className="w-4 h-4" style={{ width: 'var(--icon-size-md)', height: 'var(--icon-size-md)' }} />
                : <Moon className="w-4 h-4" style={{ width: 'var(--icon-size-md)', height: 'var(--icon-size-md)' }} />}
            </button>
          )}
          {/* Sun/Moon toggle only visible when Day/Night is enabled */}
          {hasPassword && (
            <a
              href="/logout"
              data-slide-item
              className="p-2 rounded-lg text-muted-foreground hover:text-destructive transition-colors"
              title="Sign out"
              aria-label="Sign out"
            >
              <LogOut className="w-3.5 h-3.5" style={{ width: 'var(--icon-size-sm)', height: 'var(--icon-size-sm)' }} />
            </a>
          )}
        </SlidingHighlight>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Persistent lockout banner — shown at the top of every Layout page when
// the anti-spam fuse is at step 4+ (LockoutOverlay only covers the chat view;
// this banner ensures Settings / Plugins / Logs pages also communicate the
// locked state).
// ---------------------------------------------------------------------------

function LockoutTopBanner() {
  const { data: fuseStatus } = useQuery({
    queryKey: ['fuse-status'],
    queryFn: getFuseStatus,
    staleTime: 0,
    refetchInterval: 30_000,
  })

  if (!fuseStatus?.locked || fuseStatus.step < 4) return null

  const isPermanent = fuseStatus.step >= 6

  return (
    <div
      role="alert"
      aria-live="polite"
      className="flex items-center gap-2 px-4 py-1.5 text-xs font-medium
                 bg-destructive/10 border-b border-destructive/20 text-destructive"
      data-testid="lockout-top-banner"
    >
      <TriangleAlert className="flex-shrink-0" style={{ width: 'var(--icon-size-sm)', height: 'var(--icon-size-sm)' }} aria-hidden="true" />
      <span className="flex-1">
        {isPermanent
          ? 'Outbound messaging permanently locked — enter unlock code in Settings to restore.'
          : 'Outbound messaging locked — cooling down. Check Settings for details.'}
      </span>
      <Link
        to="/settings"
        className="underline hover:no-underline flex-shrink-0"
      >
        Settings
      </Link>
    </div>
  )
}

export function Layout({ children }: LayoutProps) {
  const location = useLocation()
  const isHome = location.pathname === '/'

  // Swipe-from-left-edge navigates back to '/' on mobile sub-pages
  useSwipeBack(!isHome)

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-background text-foreground">
      {/* Skip-nav link */}
      <a
        href="#messages"
        className="sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50
                   focus:px-4 focus:py-2 focus:rounded-lg
                   focus:bg-primary focus:text-primary-foreground
                   focus:text-sm focus:font-medium"
      >
        Skip to messages
      </a>

      {/* Persistent banners — visible from any page */}
      <LockoutTopBanner />
      <UpdateBanner />

      {/* ── App shell: sidebar + main (fills remaining height) ── */}
      <div className="flex flex-1 min-h-0 overflow-hidden">

      {/* ── Desktop sidebar (always visible on md+) ── */}
      <aside
        className="hidden md:flex flex-col flex-shrink-0 w-[var(--sidebar-width)] h-full
                        bg-sidebar-bg border-r-[var(--border-width)] border-border"
        style={{ backgroundImage: 'var(--sidebar-bg-image)' }}>
        <SidebarContent />
      </aside>

      {/* ── Mobile: full-screen conversations list when at / ── */}
      {isHome && (
        <div
          className="md:hidden flex flex-col flex-1 min-w-0 h-full overflow-hidden bg-sidebar-bg"
          style={{ backgroundImage: 'var(--sidebar-bg-image)' }}
        >
          <SidebarContent />
        </div>
      )}

      {/* ── Main content area (desktop always, mobile only on sub-pages) ── */}
      <main
        aria-label="Chat"
        className={`flex-1 flex flex-col min-w-0 h-full overflow-hidden ${isHome ? 'hidden md:flex' : ''}`}
      >
        {children}
      </main>
      </div>{/* end app shell */}
    </div>
  )
}
