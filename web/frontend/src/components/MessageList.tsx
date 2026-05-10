/**
 * Scrollable message feed for the active conversation.
 *
 * - Fetches messages via react-query (polling every 5 s as a fallback;
 *   real-time updates come from the SSE hook in ChatPage).
 * - Appends optimistic messages from the zustand store.
 * - Auto-scrolls to the bottom on new messages.
 * - Shows a "scroll to bottom" button when the user has scrolled up.
 * - "Load older" button at the top when the backend signals has_more.
 * - For group chats, shows the sender name above incoming bubbles.
 *
 * Performance: the message list is virtualised with @tanstack/react-virtual
 * so only ~30 DOM nodes are rendered regardless of conversation length.
 */
import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useVirtualizer } from '@tanstack/react-virtual'
import { fetchMessages, fetchOlderMessages, markSeen, type Message } from '../api'
import { useChatStore } from '../store'
import { MessageBubble } from './MessageBubble'

interface MessageListProps {
  handle: string
  isGroup?: boolean
  lastSeenRowid?: number
}

// Stable empty array — avoids returning a new [] on every render when there
// are no optimistic messages, which would cause an infinite render loop via
// useSyncExternalStore's getSnapshot cache check.
const EMPTY_OPTIMISTIC: never[] = []

export function MessageList({ handle, isGroup = false, lastSeenRowid = 0 }: MessageListProps) {
  const queryClient = useQueryClient()
  const optimistic = useChatStore((s) => s.optimistic[handle] ?? EMPTY_OPTIMISTIC)
  const scrollRef = useRef<HTMLDivElement>(null)
  const atBottomRef = useRef(true)
  const [showScrollBtn, setShowScrollBtn] = useState(false)
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

  // Reset older pages when the conversation changes
  useEffect(() => {
    setOlderMsgs([])
    setHasMore(false)
  }, [handle])

  const recentMessages: Message[] = data?.messages ?? []
  const allMessages = [...olderMsgs, ...recentMessages, ...optimistic]

  // ---------------------------------------------------------------------------
  // Unread pill — "N new messages ↓"
  // ---------------------------------------------------------------------------

  // New messages = those with rowid above the snapshot taken at mount.
  const newMessageCount = useMemo(
    () => allMessages.filter((m) => m.rowid > initialSeenRowidRef.current && !m.from_me).length,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [allMessages.length],
  )
  const firstNewIndex = useMemo(
    () => allMessages.findIndex((m) => m.rowid > initialSeenRowidRef.current && !m.from_me),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [allMessages.length],
  )

  // Show pill once when messages first load and there are unseen ones and user isn't at bottom.
  const pillShownRef = useRef(false)
  useEffect(() => {
    if (!pillShownRef.current && newMessageCount > 0 && allMessages.length > 0) {
      pillShownRef.current = true
      setShowPill(true)
      pillTimerRef.current = setTimeout(() => {
        setShowPill(false)
        markSeen(handle, allMessages[allMessages.length - 1]?.rowid ?? 0)
      }, 3000)
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
    if (firstNewIndex >= 0) {
      virtualizer.scrollToIndex(firstNewIndex, { align: 'start' })
    } else {
      scrollToBottom()
    }
    markSeen(handle, allMessages[allMessages.length - 1]?.rowid ?? 0)
  }

  // ---------------------------------------------------------------------------
  // Virtualiser — renders only the visible slice of allMessages
  // ---------------------------------------------------------------------------
  const virtualizer = useVirtualizer({
    count: allMessages.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 64, // rough average row height (px)
    overscan: 10, // extra rows to pre-render above/below viewport
  })

  // Scroll to bottom on new messages (only when already at bottom)
  useEffect(() => {
    if (atBottomRef.current && allMessages.length > 0) {
      virtualizer.scrollToIndex(allMessages.length - 1, { align: 'end' })
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allMessages.length])

  const handleScroll = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    atBottomRef.current = nearBottom
    setShowScrollBtn(!nearBottom)
  }, [])

  function scrollToBottom() {
    virtualizer.scrollToIndex(allMessages.length - 1, { align: 'end' })
    atBottomRef.current = true
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

  const virtualItems = virtualizer.getVirtualItems()

  return (
    <div className="relative flex-1 min-h-0">
      <div
        id="messages"
        ref={scrollRef}
        onScroll={handleScroll}
        role="log"
        aria-live="polite"
        aria-label="Conversation messages"
        className="absolute inset-0 overflow-y-auto"
      >
        {/* Load-older button */}
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

        {allMessages.length === 0 && (
          <p className="text-center text-sm text-muted-foreground mt-8 px-4">
            No messages yet.
          </p>
        )}

        {/* Virtual list container — height matches total row heights */}
        <div
          style={{ height: `${virtualizer.getTotalSize()}px`, position: 'relative' }}
        >
          {virtualItems.map((vItem) => {
            const msg = allMessages[vItem.index]
            return (
              <div
                key={msg.rowid}
                data-index={vItem.index}
                ref={virtualizer.measureElement}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  transform: `translateY(${vItem.start}px)`,
                }}
                className="px-4 py-1"
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
                />
              </div>
            )
          })}
        </div>
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
