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
import { useParams, Navigate, useNavigate } from 'react-router-dom'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { useQueryClient, useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState, useCallback } from 'react'
import { Layout } from '../components/Layout'
import { MessageList } from '../components/MessageList'
import { ComposeBox } from '../components/ComposeBox'
import { ExportDropdown } from '../components/ExportDropdown'
import { UpdateBanner } from '../components/UpdateBanner'
import { ContactInfoSheet } from '../components/ContactInfoSheet'
import { LockoutOverlay } from '../components/LockoutOverlay'
import { useChatStore } from '../store'
import { useSSE, type SSEEvent } from '../hooks/useSSE'
import { fetchConversations, convRouteKey, resolveConvoHandle, getFuseStatus, getMacosVersion, type Conversation, type Message } from '../api'
import { playReceivedSound, configureSounds, type SoundsConfig } from '../hooks/useSounds'

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
      <p className="text-muted-foreground text-sm">
        Select a conversation to start chatting.
      </p>
    </div>
  )
}

/**
 * Shown on the index route (`/`). Waits for the conversations list to load,
 * then immediately redirects to the most-recent conversation. Falls back to
 * EmptyState when the list is empty (new installs, no messages yet).
 */
function AutoRedirect() {
  const { data: conversations, isLoading } = useQuery({
    queryKey: ['conversations'],
    queryFn: fetchConversations,
    staleTime: 30_000,
  })

  if (isLoading || !conversations) return null
  if (conversations.length === 0) return <EmptyState />

  const first = conversations[0]
  return (
    <Navigate to={`/chat/${encodeURIComponent(convRouteKey(first))}`} replace />
  )
}

interface HeaderProps {
  handle: string
  isGroup: boolean
  conversations: Conversation[]
  onInfoClick: () => void
}

function ConversationHeader({ handle, isGroup, conversations, onInfoClick }: HeaderProps) {
  const displayName = displayNameForHandle(handle, conversations)
  const initials = isGroup ? '##' : (displayName.trim()[0] ?? '?').toUpperCase()

  // Popout URL for this conversation
  const popoutParam = isGroup
    ? `?chat=${encodeURIComponent(handle)}`
    : `?handle=${encodeURIComponent(handle)}`

  return (
    <div
      className="flex items-center gap-3 px-4 py-3 border-b-[var(--header-border)] border-border
                 shadow-[var(--header-shadow)] bg-background flex-shrink-0"
    >
      {/* Clickable avatar + name → opens contact info sheet */}
      <button
        onClick={onInfoClick}
        aria-label={`View info for ${displayName}`}
        className="flex items-center gap-3 min-w-0 flex-1 text-left
                   hover:opacity-80 transition-opacity focus-visible:outline-none
                   focus-visible:ring-2 focus-visible:ring-primary rounded"
      >
        <Avatar
          className={[
            'flex-shrink-0 h-9 w-9 bg-card',
            isGroup ? 'rounded-lg' : 'rounded-[var(--avatar-shape)]',
          ].join(' ')}
          aria-hidden="true"
        >
          {!isGroup && (
            <AvatarImage
              src={`/avatar?handle=${encodeURIComponent(handle)}`}
              alt={displayName}
            />
          )}
          <AvatarFallback
            className={[
              'bg-card text-primary font-semibold text-sm',
              isGroup ? 'rounded-lg' : 'rounded-[var(--avatar-shape)]',
            ].join(' ')}
          >
            {initials}
          </AvatarFallback>
        </Avatar>
        <div className="min-w-0">
          <p className="text-base font-semibold text-foreground truncate">
            {displayName}
          </p>
          {isGroup && (
            <p className="text-xs text-muted-foreground">Group conversation</p>
          )}
        </div>
      </button>

      {/* Popout button — opens a dedicated narrow window, not a tab */}
      <button
        onClick={() => window.open(`/popout${popoutParam}`, '_blank', 'width=480,height=720,noopener')}
        aria-label="Open in popout window"
        className="p-2 rounded-lg text-muted-foreground hover:bg-accent transition-colors"
        title="Popout window"
        type="button"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24"
             strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
          <polyline points="15 3 21 3 21 9"/>
          <line x1="10" y1="14" x2="21" y2="3"/>
        </svg>
      </button>

      {/* Export dropdown */}
      <ExportDropdown handle={handle} isGroup={isGroup} />
    </div>
  )
}

/**
 * Renders the active conversation. `slugParam` is the decoded URL param —
 * it may be a human-readable slug (e.g. "sarah-chen") or a raw handle.
 * The real handle is resolved via the conversations list before any API call.
 */
function ActiveConversation({ slugParam }: { slugParam: string }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const clearOptimistic = useChatStore((s) => s.clearOptimistic)
  const setActiveHandle = useChatStore((s) => s.setActiveHandle)
  const [infoOpen, setInfoOpen] = useState(false)

  const { data: conversations = [] } = useQuery({
    queryKey: ['conversations'],
    queryFn: fetchConversations,
    staleTime: 30_000,
  })

  // Resolve slug → real handle. Returns null while conversations are still loading
  // to prevent fetching messages with an unresolved slug.
  const resolved = useMemo(
    () => resolveConvoHandle(slugParam, conversations),
    [slugParam, conversations],
  )
  // If the slug looks like a raw handle already (contains +, @, or ;), use it directly.
  // Otherwise wait for conversations to load so we can resolve the slug.
  const handle = resolved ?? (/[+@;]/.test(slugParam) ? slugParam : null)
  const isGroup = handle ? isGroupHandle(handle) : false

  /**
   * Called when "Remove from whitelist" succeeds. Closes the info sheet
   * and navigates to the next available conversation so the user is not
   * left on a dead route for the just-removed contact.
   */
  const handleRemoved = useCallback(() => {
    setInfoOpen(false)
    const next = conversations.find((c) =>
      c.kind === 'handle' ? c.handle !== handle : c.guid !== handle,
    )
    if (next) {
      navigate(`/chat/${encodeURIComponent(convRouteKey(next))}`, { replace: true })
    } else {
      navigate('/', { replace: true })
    }
  }, [conversations, handle, navigate])

  // Last-seen rowid for this conversation — used by the unread pill in MessageList.
  const lastSeenRowid = useMemo(() => {
    const convo = conversations.find((c) =>
      c.kind === 'handle' ? c.handle === handle : c.guid === handle,
    )
    return convo?.last_seen_rowid ?? 0
  }, [conversations, handle])

  // Keep Zustand in sync with the resolved real handle.
  useEffect(() => {
    setActiveHandle(handle)
    return () => setActiveHandle(null)
  }, [handle, setActiveHandle])

  useSSE({
    onEvent: (event: SSEEvent) => {
      if (event.handle && decodeURIComponent(event.handle) === handle) {
        qc.invalidateQueries({ queryKey: ['messages', handle] })
        if (event.rowid != null) {
          clearOptimistic(handle, event.rowid)
        }
      }
      // Play received sound for inbound messages (not our own sends)
      if (!event.from_me) {
        playReceivedSound()
      }
      qc.invalidateQueries({ queryKey: ['conversations'] })
    },
  })

  // Move focus to compose box when conversation changes (Chunk 5 a11y)
  useEffect(() => {
    const el = document.querySelector<HTMLTextAreaElement>('textarea[aria-label="Type a message"]')
    if (el) el.focus()
  }, [handle])

  // macOS version — fetched once; used to gate Edit/Unsend (Ventura 13+)
  const { data: macosVer } = useQuery({
    queryKey: ['macos-version'],
    queryFn: getMacosVersion,
    staleTime: Infinity,
    gcTime: Infinity,
  })
  const ventura = (macosVer?.major ?? 0) >= 13

  // Reply-to context — set from the hover action bar, cleared on send
  const [replyTo, setReplyTo] = useState<Message | null>(null)

  // Check fuse status for full lockout (steps 4+)
  const { data: fuseStatus } = useQuery({
    queryKey: ['fuse-status'],
    queryFn: getFuseStatus,
    staleTime: 0,
    refetchInterval: false,
  })
  const isLockedOut = !!(fuseStatus?.locked && fuseStatus.step >= 4)

  // Still resolving slug → show loading state
  if (!handle) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-muted-foreground text-sm animate-pulse">Loading...</p>
      </div>
    )
  }

  // Full lockout (step 4+): replace chat content with overlay
  if (isLockedOut && fuseStatus) {
    return <LockoutOverlay fuseStatus={fuseStatus} />
  }

  return (
    <>
      <ConversationHeader
        handle={handle}
        isGroup={isGroup}
        conversations={conversations}
        onInfoClick={() => setInfoOpen(true)}
      />
      <MessageList
        handle={handle}
        isGroup={isGroup}
        lastSeenRowid={lastSeenRowid}
        ventura={ventura}
        onReply={setReplyTo}
      />
      <ComposeBox
        handle={handle}
        isGroup={isGroup}
        replyToGuid={replyTo?.guid ?? ''}
        replyToText={replyTo?.text ?? ''}
        onClearReply={() => setReplyTo(null)}
      />
      <ContactInfoSheet
        open={infoOpen}
        onClose={() => setInfoOpen(false)}
        handle={handle}
        isGroup={isGroup}
        onRemoved={handleRemoved}
      />
    </>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function ChatPage() {
  const { handle: encodedHandle } = useParams<{ handle: string }>()

  // Load custom sound config once so useSounds respects user preferences.
  useEffect(() => {
    fetch('/api/ui/sounds/config', { credentials: 'same-origin' })
      .then((r) => (r.ok ? r.json() : null))
      .then((cfg: SoundsConfig | null) => { if (cfg) configureSounds(cfg) })
      .catch(() => {/* non-critical — falls back to defaults */})
  }, [])

  // URL param may be a slug (sarah-chen) or a raw handle (+14695551234).
  // Resolution to the real handle happens inside ActiveConversation once
  // the conversations list is available.
  const slugParam = encodedHandle ? decodeURIComponent(encodedHandle) : null

  return (
    <Layout>
      <UpdateBanner />
      {slugParam ? (
        <ActiveConversation slugParam={slugParam} />
      ) : (
        <AutoRedirect />
      )}
    </Layout>
  )
}
