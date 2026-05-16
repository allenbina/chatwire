/**
 * Scrollable message feed for the active conversation.
 *
 * Uses `flex-direction: column-reverse` on the scroll container so the
 * browser natively anchors the viewport to the bottom (newest messages).
 * No JavaScript scroll management is needed for the default case — the
 * browser handles image loads, content expansion, and initial positioning.
 *
 * - Fetches messages via react-query (polling every 5 s as a fallback;
 *   real-time updates come from the SSE hook in ChatPage).
 * - Appends optimistic messages from the zustand store.
 * - Shows a "scroll to bottom" button when the user has scrolled up.
 * - "Load older" button at the top when the backend signals has_more.
 * - For group chats, shows the sender name above incoming bubbles.
 */
import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchMessages, fetchOlderMessages, markSeen, type Message } from '../api'
import { useChatStore } from '../store'
import { MessageBubble } from './MessageBubble'

interface MessageListProps {
  handle: string
  isGroup?: boolean
  lastSeenRowid?: number
  ventura?: boolean
  onReply?: (msg: Message) => void
}

// Stable empty array — avoids returning a new [] on every render when there
// are no optimistic messages, which would cause an infinite render loop via
// useSyncExternalStore's getSnapshot cache check.
const EMPTY_OPTIMISTIC: never[] = []

/**
 * Collapse iMessage→SMS fallback pairs into a single SMS bubble.
 *
 * When iMessage fails and Messages.app retries via SMS, the database stores
 * two consecutive rows: a failed iMessage (status="failed") immediately
 * followed by the SMS send with identical text. We hide the failed row and
 * annotate the SMS row with fell_back_to_sms=true so the bubble can show a
 * small note.
 */
function collapseSmsFallback(messages: Message[]): Message[] {
  const result: Message[] = []
  let i = 0
  while (i < messages.length) {
    const curr = messages[i]
    const next = messages[i + 1]
    if (
      curr.from_me &&
      curr.status === 'failed' &&
      next?.from_me &&
      next.service === 'SMS' &&
      curr.text === next.text
    ) {
      // Suppress the failed iMessage bubble; show only the SMS bubble with a note.
      result.push({ ...next, fell_back_to_sms: true })
      i += 2
    } else {
      result.push(curr)
      i++
    }
  }
  return result
}

export function MessageList({ handle, isGroup = false, lastSeenRowid = 0, ventura = false, onReply }: MessageListProps) {
  const queryClient = useQueryClient()
  const optimistic = useChatStore((s) => s.optimistic[handle] ?? EMPTY_OPTIMISTIC)
  const scrollRef = useRef<HTMLDivElement>(null)
  const [showScrollBtn, setShowScrollBtn] = useState(false)
  // Ref so handleScroll can read the latest messages without stale closure
  const allMsgsRef = useRef<Message[]>([])
  const [olderMsgs, setOlderMsgs] = useState<Message[]>([])
  const [loadingOlder, setLoadingOlder] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  // Pill: captures last-seen rowid at mount so new SSE messages don't inflate count
  const initialSeenRowidRef = useRef(lastSeenRowid)
  const [showPill, setShowPill] = useState(false)
  const pillTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['messages', handle],
    queryFn: () => fetchMessages(handle, isGroup, 0, 150),
    // Refetch every 5 s as a heartbeat; SSE delivers real-time updates.
    refetchInterval: 5_000,
    staleTime: 2_000,
  })

  // Sync has_more from the latest fetch result
  useEffect(() => {
    if (data) setHasMore(data.has_more)
  }, [data])

  // Reset state when the conversation changes
  useEffect(() => {
    setOlderMsgs([])
    setHasMore(false)
    setShowScrollBtn(false)
  }, [handle])

  const recentMessages: Message[] = data?.messages ?? []
  const allMessages = collapseSmsFallback([...olderMsgs, ...recentMessages, ...optimistic])
  // Keep ref in sync so scroll handler can access latest messages without stale closures
  allMsgsRef.current = allMessages

  // Self-chat detection: every message is from_me (notes to yourself).
  // Only treat as self-chat when there's at least one message to avoid
  // false positives on first render.
  const isSelfChat = allMessages.length > 0 && allMessages.every((m) => m.from_me)

  // ---------------------------------------------------------------------------
  // Mark seen when messages load (column-reverse starts at bottom by default)
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (allMessages.length === 0) return
    const lastRowid = allMessages[allMessages.length - 1]?.rowid
    if (lastRowid) markSeen(handle, lastRowid)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handle, allMessages.length])

  // ---------------------------------------------------------------------------
  // Unread pill — "N new messages ↓"
  // ---------------------------------------------------------------------------

  // New messages = those with rowid above the snapshot taken at mount.
  const newMessageCount = useMemo(
    () => allMessages.filter((m) => m.rowid > initialSeenRowidRef.current && !m.from_me).length,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [allMessages.length],
  )
  const firstNewRowid = useMemo(
    () => allMessages.find((m) => m.rowid > initialSeenRowidRef.current && !m.from_me)?.rowid ?? null,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [allMessages.length],
  )

  // Show pill once when messages first load and there are unseen ones.
  const pillShownRef = useRef(false)
  useEffect(() => {
    if (!pillShownRef.current && newMessageCount > 0 && allMessages.length > 0) {
      pillShownRef.current = true
      setShowPill(true)
      // Auto-dismiss pill after 3s (markSeen happens on scroll, not here)
      pillTimerRef.current = setTimeout(() => setShowPill(false), 3000)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allMessages.length])

  // Capture lastSeenRowid snapshot on handle change
  useEffect(() => {
    initialSeenRowidRef.current = lastSeenRowid
    pillShownRef.current = false
    setShowPill(false)
    if (pillTimerRef.current) clearTimeout(pillTimerRef.current)
  }, [handle, lastSeenRowid])

  function dismissPill() {
    setShowPill(false)
    if (pillTimerRef.current) clearTimeout(pillTimerRef.current)
    if (firstNewRowid !== null) {
      const el = scrollRef.current?.querySelector(`[data-rowid="${firstNewRowid}"]`)
      el?.scrollIntoView?.({ block: 'start' })
    } else {
      scrollToBottom()
    }
  }

  // ---------------------------------------------------------------------------
  // Scroll detection — column-reverse: scrollTop ≈ 0 means at bottom
  // ---------------------------------------------------------------------------
  const handleScroll = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    // In column-reverse, scrollTop is 0 at the natural position (bottom/newest).
    // Scrolling up toward older messages makes scrollTop go negative (or stay
    // near 0 on some browsers). Use Math.abs for cross-browser safety.
    const nearBottom = Math.abs(el.scrollTop) < 80
    setShowScrollBtn(!nearBottom)
    // Mark seen when user is at the bottom
    if (nearBottom && allMsgsRef.current.length > 0) {
      const lastRowid = allMsgsRef.current[allMsgsRef.current.length - 1]?.rowid
      if (lastRowid) markSeen(handle, lastRowid)
    }
  }, [handle])

  function scrollToBottom() {
    const el = scrollRef.current
    if (el) el.scrollTop = 0
    setShowScrollBtn(false)
  }

  async function loadOlder() {
    const oldest = olderMsgs.length > 0 ? olderMsgs[0] : recentMessages[0]
    if (!oldest || loadingOlder) return
    setLoadingOlder(true)
    try {
      const result = await fetchOlderMessages(handle, isGroup, oldest.date, oldest.rowid, 50)
      setOlderMsgs((prev) => [...result.messages, ...prev])
      setHasMore(result.has_more)
      queryClient.invalidateQueries({ queryKey: ['messages', handle] })
    } catch {
      // silently ignore; user can retry
    } finally {
      setLoadingOlder(false)
    }
  }

  // Reversed messages for column-reverse rendering: newest first in DOM
  // (column-reverse places first child at the bottom of the viewport).
  const reversedMessages = useMemo(
    () => [...allMessages].reverse(),
    [allMessages],
  )

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm animate-pulse">
        Loading messages&hellip;
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex-1 flex items-center justify-center text-destructive text-sm">
        Failed to load messages.
      </div>
    )
  }

  return (
    <div className="relative flex-1 min-h-0">
      {/* column-reverse scroll container: browser natively anchors to bottom */}
      <div
        id="messages"
        ref={scrollRef}
        onScroll={handleScroll}
        role="log"
        aria-live="polite"
        aria-label="Conversation messages"
        className="absolute inset-0 overflow-y-auto overscroll-contain flex flex-col-reverse"
      >
        {/* Messages rendered newest-first; column-reverse puts first child at bottom */}
        {reversedMessages.map((msg) => (
          <div
            key={msg.rowid}
            data-rowid={msg.rowid}
            className="px-4 flex flex-col"
            style={{
              paddingTop: 'var(--spacing-message)',
              paddingBottom: 'var(--spacing-message)',
            }}
          >
            {/* Sender label for incoming group messages */}
            {isGroup && !msg.from_me && msg.sender_name && (
              <p className="text-[10px] text-muted-foreground mb-0.5 ml-1">
                {msg.sender_name}
              </p>
            )}
            <MessageBubble
              msg={msg}
              pending={'pending' in msg && (msg as Message & { pending?: boolean }).pending === true}
              selfChatAlt={isSelfChat && msg.rowid % 2 !== 0}
              isGroup={isGroup}
              onScrollToRowid={(rowid) => {
                const el = scrollRef.current?.querySelector(
                  `[data-rowid="${rowid}"]`,
                )
                el?.scrollIntoView?.({ block: 'center', behavior: 'smooth' })
              }}
              ventura={ventura}
              onReply={onReply}
            />
          </div>
        ))}

        {/* Empty state */}
        {allMessages.length === 0 && (
          <p className="text-center text-sm text-muted-foreground mt-8 px-4">
            No messages yet.
          </p>
        )}

        {/* Load-older button — last child in DOM = top of viewport in column-reverse */}
        {hasMore && (
          <div className="flex justify-center my-2 px-4">
            <button
              onClick={loadOlder}
              disabled={loadingOlder}
              className="text-xs text-primary border border-primary rounded-full
                         px-4 py-1 hover:bg-card disabled:opacity-50
                         disabled:cursor-not-allowed transition-colors"
            >
              {loadingOlder ? 'Loading\u2026' : 'Load older messages'}
            </button>
          </div>
        )}
      </div>

      {/* New-messages pill */}
      {showPill && newMessageCount > 0 && (
        <button
          onClick={dismissPill}
          className="absolute top-3 left-1/2 -translate-x-1/2 z-10
                     flex items-center gap-1.5 px-3 py-1.5 rounded-full shadow-md text-xs font-medium
                     bg-primary text-primary-foreground
                     hover:opacity-90 transition-opacity"
          aria-label={`${newMessageCount} new messages, scroll to first`}
        >
          {newMessageCount === 1 ? '1 new message' : `${newMessageCount} new messages`} ↓
        </button>
      )}

      {/* Scroll-to-bottom button */}
      {showScrollBtn && (
        <button
          onClick={scrollToBottom}
          className="absolute bottom-4 right-4 w-9 h-9 rounded-full shadow-lg
                     bg-primary text-primary-foreground text-lg flex items-center justify-center
                     hover:bg-primary/90 transition-colors"
          aria-label="Scroll to bottom"
        >
          &#8595;
        </button>
      )}
    </div>
  )
}
