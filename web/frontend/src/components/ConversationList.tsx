/**
 * Sidebar list of conversations, sorted by the backend (favorites first,
 * then recency). Clicking a row navigates to /app/chat/:handle and sets
 * the active handle in the zustand store.
 *
 * Data is fetched by react-query; refetched every 30 s in the background.
 * Both 1:1 (kind=handle) and group (kind=group) conversations are rendered.
 *
 * Accessibility:
 *  - <nav aria-label="Conversations"> wrapper
 *  - <ul role="list"> / <li role="listitem"> for semantic list structure
 *  - aria-current="page" on the active conversation row
 */
import { useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { fetchConversations, markSeen, markAllSeen, convRouteKey, type Conversation } from '../api'
import { useChatStore } from '../store'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { cn } from '@/lib/utils'
import { SlidingHighlight } from './SlidingHighlight'

function avatarLabel(convo: Conversation): string {
  if (convo.kind === 'group') return '##'
  const name = convo.name || convo.handle
  return (name.trim()[0] ?? '?').toUpperCase()
}

function ConversationRow({ convo }: { convo: Conversation }) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { handle: activeHandle } = useParams()
  const setActiveHandle = useChatStore((s) => s.setActiveHandle)
  const setSidebarOpen = useChatStore((s) => s.setSidebarOpen)

  const routeKey = convRouteKey(convo)
  const isActive = activeHandle === routeKey
  const displayName = convo.name || (convo.kind === 'handle' ? convo.handle : '(group)')
  const rawHandle = convo.kind === 'handle' ? convo.handle : convo.guid

  function handleClick() {
    setActiveHandle(rawHandle)
    setSidebarOpen(false)
    navigate(`/chat/${encodeURIComponent(routeKey)}`)
    // Mark as seen immediately — fire-and-forget, then refresh the list
    if (convo.last_rowid) {
      markSeen(rawHandle, convo.last_rowid).then(() => {
        qc.invalidateQueries({ queryKey: ['conversations'] })
      })
    }
  }

  return (
    <li role="listitem" data-slide-item className="border-b-[var(--sidebar-divider)] border-border">
      <button
        onClick={handleClick}
        aria-current={isActive ? 'page' : undefined}
        className={cn(
          'w-full text-left flex items-center gap-3 px-4',
          'transition-colors',
          isActive && 'bg-accent',
        )}
        style={{
          paddingTop: 'var(--spacing-sidebar)',
          paddingBottom: 'var(--spacing-sidebar)',
          borderRadius: 'var(--sidebar-active-radius)',
        }}
      >
        {/* Avatar — groups use rounded-lg; 1:1 uses --avatar-shape variable */}
        <Avatar
          className={cn(
            'flex-shrink-0 bg-card',
            'h-[var(--avatar-size)] w-[var(--avatar-size)]',
            convo.kind === 'group' ? 'rounded-lg' : 'rounded-[var(--avatar-shape)]',
          )}
          aria-hidden="true"
        >
          {convo.kind === 'handle' && (
            <AvatarImage
              src={`/avatar?handle=${encodeURIComponent(convo.handle)}`}
              alt={displayName}
            />
          )}
          <AvatarFallback
            className={cn(
              'bg-card text-primary font-semibold text-sm',
              convo.kind === 'group' ? 'rounded-lg' : 'rounded-[var(--avatar-shape)]',
            )}
          >
            {avatarLabel(convo)}
          </AvatarFallback>
        </Avatar>

        {/* Name + preview */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-1">
            <span
              className={cn(
                'text-base font-semibold truncate',
                convo.is_favorite
                  ? 'text-warning'
                  : 'text-foreground',
              )}
            >
              {convo.is_favorite && <span className="mr-1 text-xs">&#9733;</span>}
              {convo.kind === 'group' && (
                <span className="mr-1 text-xs opacity-60">[G]</span>
              )}
              {displayName}
            </span>
            <span className="flex-shrink-0 text-xs text-muted-foreground">
              {convo.last}
            </span>
          </div>
          <div className="flex items-center justify-between gap-1 mt-0.5">
            <p className="text-muted-foreground truncate flex items-center gap-1" style={{ fontSize: 'var(--font-size-sidebar)' }}>
              {convo.has_media && !convo.preview ? (
                <>
                  <svg className="w-3.5 h-3.5 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth={2}
                       viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                    <circle cx="8.5" cy="8.5" r="1.5"/>
                    <polyline points="21 15 16 10 5 21"/>
                  </svg>
                  <span>Photo</span>
                </>
              ) : (
                convo.preview || '\u00a0'
              )}
            </p>
            {/* Unseen dot — based on Chatwire's own read state, not iMessage is_read */}
            {convo.unseen && (
              <span
                className="flex-shrink-0 w-2.5 h-2.5 rounded-full bg-primary"
                aria-label="New messages"
              />
            )}
          </div>
        </div>
      </button>
    </li>
  )
}

export function ConversationList() {
  const qc = useQueryClient()
  const { data, isLoading, isError } = useQuery({
    queryKey: ['conversations'],
    queryFn: fetchConversations,
    refetchInterval: 30_000,
    staleTime: 10_000,
  })

  const markAllMutation = useMutation({
    mutationFn: markAllSeen,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conversations'] })
      // Clear the app badge on supported browsers (PWA / mobile)
      if ('clearAppBadge' in navigator) {
        ;(navigator as Navigator & { clearAppBadge: () => Promise<void> })
          .clearAppBadge()
          .catch(() => {})
      }
    },
  })

  // Shift+Escape — mark all read from anywhere in the app
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.shiftKey && e.key === 'Escape' && !markAllMutation.isPending) {
        markAllMutation.mutate()
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [markAllMutation])

  if (isLoading) {
    return (
      <div className="p-4 text-sm text-muted-foreground animate-pulse">
        Loading conversations&hellip;
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="p-4 text-sm text-destructive">
        Failed to load conversations.
      </div>
    )
  }

  if (data.length === 0) {
    return (
      <div className="p-4 text-sm text-muted-foreground">
        No conversations yet.
      </div>
    )
  }

  return (
    <nav aria-label="Conversations">
      <SlidingHighlight highlightClass="bg-accent rounded-[var(--sidebar-active-radius)]">
        <ul role="list" className="py-1">
          {data.map((c) => (
            <ConversationRow key={convRouteKey(c)} convo={c} />
          ))}
        </ul>
      </SlidingHighlight>
    </nav>
  )
}
