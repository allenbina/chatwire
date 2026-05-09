/**
 * Main chat view: Layout shell + contact header + MessageList + ComposeBox.
 *
 * Handles the active conversation identified by the :handle URL param.
 * Subscribes to the /events SSE stream and invalidates the messages
 * query whenever a new message arrives for the active conversation.
 *
 * Group chats are identified by GUIDs containing ';' (e.g. iMessage;+;chat…).
 * The isGroup flag is derived from the decoded handle and passed down to
 * MessageList and ComposeBox so they route API calls correctly.
 */
import { useParams } from 'react-router-dom'
import { useQueryClient, useQuery } from '@tanstack/react-query'
import { useEffect } from 'react'
import { Layout } from '../components/Layout'
import { MessageList } from '../components/MessageList'
import { ComposeBox } from '../components/ComposeBox'
import { ExportDropdown } from '../components/ExportDropdown'
import { UpdateBanner } from '../components/UpdateBanner'
import { useChatStore } from '../store'
import { useSSE, type SSEEvent } from '../hooks/useSSE'
import { fetchConversations, type Conversation } from '../api'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isGroupHandle(handle: string): boolean {
  // Group GUIDs look like "iMessage;+;chatXXX" — they always contain ';'
  return handle.includes(';')
}

function displayNameForHandle(handle: string, conversations: Conversation[]): string {
  const c = conversations.find((c) =>
    c.kind === 'group' ? c.guid === handle : c.handle === handle,
  )
  return c?.name ?? handle
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function EmptyState() {
  return (
    <div className="flex-1 flex items-center justify-center">
      <p className="text-[--color-text-muted] text-sm">
        Select a conversation to start chatting.
      </p>
    </div>
  )
}

interface HeaderProps {
  handle: string
  isGroup: boolean
  conversations: Conversation[]
}

function ConversationHeader({ handle, isGroup, conversations }: HeaderProps) {
  const displayName = displayNameForHandle(handle, conversations)
  const initials = isGroup ? '##' : (displayName.trim()[0] ?? '?').toUpperCase()

  // Popout URL for this conversation
  const popoutParam = isGroup
    ? `?chat=${encodeURIComponent(handle)}`
    : `?handle=${encodeURIComponent(handle)}`

  return (
    <div
      className="flex items-center gap-3 px-4 py-3 border-b border-[--color-border]
                 bg-[--color-bg-primary] flex-shrink-0"
    >
      <div
        className={[
          'flex-shrink-0 w-9 h-9 flex items-center justify-center',
          'bg-[--color-bg-secondary] text-[--color-accent] font-semibold text-sm',
          isGroup ? 'rounded-lg' : 'rounded-full',
        ].join(' ')}
        aria-hidden="true"
      >
        {initials}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-[--color-text-primary] truncate">
          {displayName}
        </p>
        {isGroup && (
          <p className="text-[10px] text-[--color-text-muted]">Group conversation</p>
        )}
      </div>

      {/* Popout button */}
      <a
        href={`/app/popout${popoutParam}`}
        target="_blank"
        rel="noopener"
        aria-label="Open in popout window"
        className="p-2 rounded-lg text-[--color-text-muted] hover:bg-[--color-sidebar-hover] transition-colors"
        title="Popout window"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24"
             strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
          <polyline points="15 3 21 3 21 9"/>
          <line x1="10" y1="14" x2="21" y2="3"/>
        </svg>
      </a>

      {/* Export dropdown */}
      <ExportDropdown handle={handle} isGroup={isGroup} />
    </div>
  )
}

function ActiveConversation({ handle }: { handle: string }) {
  const qc = useQueryClient()
  const clearOptimistic = useChatStore((s) => s.clearOptimistic)
  const isGroup = isGroupHandle(handle)

  const { data: conversations = [] } = useQuery({
    queryKey: ['conversations'],
    queryFn: fetchConversations,
    staleTime: 30_000,
  })

  useSSE({
    onEvent: (event: SSEEvent) => {
      if (event.handle && decodeURIComponent(event.handle) === handle) {
        qc.invalidateQueries({ queryKey: ['messages', handle] })
        if (event.rowid != null) {
          clearOptimistic(handle, event.rowid)
        }
      }
      qc.invalidateQueries({ queryKey: ['conversations'] })
    },
  })

  // Move focus to compose box when conversation changes (Chunk 5 a11y)
  useEffect(() => {
    const el = document.querySelector<HTMLTextAreaElement>('textarea[aria-label="Type a message"]')
    if (el) el.focus()
  }, [handle])

  return (
    <>
      <ConversationHeader
        handle={handle}
        isGroup={isGroup}
        conversations={conversations}
      />
      <MessageList handle={handle} isGroup={isGroup} />
      <ComposeBox handle={handle} isGroup={isGroup} />
    </>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function ChatPage() {
  const { handle: encodedHandle } = useParams<{ handle: string }>()
  const setActiveHandle = useChatStore((s) => s.setActiveHandle)

  const handle = encodedHandle ? decodeURIComponent(encodedHandle) : null

  useEffect(() => {
    setActiveHandle(handle)
    return () => setActiveHandle(null)
  }, [handle, setActiveHandle])

  return (
    <Layout>
      <UpdateBanner />
      {handle ? (
        <ActiveConversation handle={handle} />
      ) : (
        <EmptyState />
      )}
    </Layout>
  )
}
