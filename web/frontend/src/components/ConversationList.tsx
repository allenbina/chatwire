/**
 * Sidebar list of conversations, sorted by the backend (favorites first,
 * then recency). Clicking a row navigates to /app/chat/:handle and sets
 * the active handle in the zustand store.
 *
 * Data is fetched by react-query; refetched every 30 s in the background.
 * Both 1:1 (kind=handle) and group (kind=group) conversations are rendered.
 */
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { fetchConversations, convRouteKey, type Conversation } from '../api'
import { useChatStore } from '../store'

function avatarLabel(convo: Conversation): string {
  if (convo.kind === 'group') return '##'
  const name = convo.name || convo.handle
  return (name.trim()[0] ?? '?').toUpperCase()
}

function ConversationRow({ convo }: { convo: Conversation }) {
  const navigate = useNavigate()
  const { handle: activeHandle } = useParams()
  const setActiveHandle = useChatStore((s) => s.setActiveHandle)
  const setSidebarOpen = useChatStore((s) => s.setSidebarOpen)

  const routeKey = convRouteKey(convo)
  const isActive = activeHandle === encodeURIComponent(routeKey)
  const displayName = convo.name || (convo.kind === 'handle' ? convo.handle : '(group)')

  function handleClick() {
    setActiveHandle(routeKey)
    setSidebarOpen(false) // close drawer on mobile
    navigate(`/app/chat/${encodeURIComponent(routeKey)}`)
  }

  return (
    <button
      onClick={handleClick}
      className={[
        'w-full text-left flex items-center gap-3 px-3 py-2.5',
        'hover:bg-[--color-sidebar-hover] transition-colors',
        isActive ? 'bg-[--color-sidebar-active]' : '',
      ].join(' ')}
    >
      {/* Avatar — round for 1:1, rounded-lg for groups */}
      <div
        className={[
          'flex-shrink-0 w-9 h-9 flex items-center justify-center',
          'bg-[--color-bg-secondary] text-[--color-accent] font-semibold text-sm',
          convo.kind === 'group' ? 'rounded-lg' : 'rounded-full',
        ].join(' ')}
        aria-hidden="true"
      >
        {avatarLabel(convo)}
      </div>

      {/* Name + preview */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-1">
          <span
            className={[
              'text-sm font-medium truncate',
              convo.is_favorite ? 'text-[--color-warning]' : 'text-[--color-text-primary]',
            ].join(' ')}
          >
            {convo.is_favorite && <span className="mr-1 text-xs">&#9733;</span>}
            {convo.kind === 'group' && <span className="mr-1 text-xs opacity-60">[G]</span>}
            {displayName}
          </span>
          <span className="flex-shrink-0 text-xs text-[--color-text-muted]">{convo.last}</span>
        </div>
        <div className="flex items-center justify-between gap-1 mt-0.5">
          <p className="text-xs text-[--color-text-muted] truncate">{convo.preview || '\u00a0'}</p>
          {convo.n > 0 && (
            <span
              className="flex-shrink-0 min-w-[1.25rem] h-5 rounded-full bg-[--color-accent]
                         text-[--color-bg-primary] text-[10px] font-bold flex items-center justify-center px-1"
            >
              {convo.n > 99 ? '99+' : convo.n}
            </span>
          )}
        </div>
      </div>
    </button>
  )
}

export function ConversationList() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['conversations'],
    queryFn: fetchConversations,
    refetchInterval: 30_000,
    staleTime: 10_000,
  })

  if (isLoading) {
    return (
      <div className="p-4 text-sm text-[--color-text-muted] animate-pulse">
        Loading conversations&hellip;
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="p-4 text-sm text-[--color-error]">
        Failed to load conversations.
      </div>
    )
  }

  if (data.length === 0) {
    return (
      <div className="p-4 text-sm text-[--color-text-muted]">
        No conversations yet.
      </div>
    )
  }

  return (
    <nav aria-label="Conversations">
      {data.map((c) => (
        <ConversationRow key={c.handle} convo={c} />
      ))}
    </nav>
  )
}
