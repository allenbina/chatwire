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
      <div className="min-w-0">
        <p className="text-sm font-semibold text-[--color-text-primary] truncate">
          {displayName}
        </p>
        {isGroup && (
          <p className="text-[10px] text-[--color-text-muted]">Group conversation</p>
        )}
      </div>
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
      {handle ? (
        <ActiveConversation handle={handle} />
      ) : (
        <EmptyState />
      )}
    </Layout>
  )
}
