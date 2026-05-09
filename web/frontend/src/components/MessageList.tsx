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
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchMessages, fetchOlderMessages, type Message } from '../api'
import { useChatStore } from '../store'
import { MessageBubble } from './MessageBubble'

interface MessageListProps {
  handle: string
  isGroup?: boolean
}

export function MessageList({ handle, isGroup = false }: MessageListProps) {
  const queryClient = useQueryClient()
  const optimistic = useChatStore((s) => s.optimistic[handle] ?? [])
  const scrollRef = useRef<HTMLDivElement>(null)
  const atBottomRef = useRef(true)
  const [showScrollBtn, setShowScrollBtn] = useState(false)
  const [olderMsgs, setOlderMsgs] = useState<Message[]>([])
  const [loadingOlder, setLoadingOlder] = useState(false)
  const [hasMore, setHasMore] = useState(false)

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

  // Scroll to bottom on new messages (only when already at bottom)
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    if (atBottomRef.current) {
      el.scrollTop = el.scrollHeight
    }
  }, [allMessages.length])

  const handleScroll = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    atBottomRef.current = nearBottom
    setShowScrollBtn(!nearBottom)
  }, [])

  function scrollToBottom() {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
    atBottomRef.current = true
    setShowScrollBtn(false)
  }

  async function loadOlder() {
    // Use the oldest message we currently display as the before-cursor
    const oldest = olderMsgs.length > 0 ? olderMsgs[0] : recentMessages[0]
    if (!oldest || loadingOlder) return
    setLoadingOlder(true)
    try {
      const result = await fetchOlderMessages(handle, isGroup, oldest.date, oldest.rowid, 50)
      setOlderMsgs((prev) => [...result.messages, ...prev])
      setHasMore(result.has_more)
      // Invalidate so the standard query stays fresh
      queryClient.invalidateQueries({ queryKey: ['messages', handle] })
    } catch {
      // silently ignore; user can retry
    } finally {
      setLoadingOlder(false)
    }
  }

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center text-[--color-text-muted] text-sm animate-pulse">
        Loading messages&hellip;
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex-1 flex items-center justify-center text-[--color-error] text-sm">
        Failed to load messages.
      </div>
    )
  }

  return (
    <div className="relative flex-1 min-h-0">
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="absolute inset-0 overflow-y-auto flex flex-col gap-2 px-4 py-4"
      >
        {/* Load-older button */}
        {hasMore && (
          <div className="flex justify-center mb-2">
            <button
              onClick={loadOlder}
              disabled={loadingOlder}
              className="text-xs text-[--color-accent] border border-[--color-accent] rounded-full
                         px-4 py-1 hover:bg-[--color-bg-secondary] disabled:opacity-50
                         disabled:cursor-not-allowed transition-colors"
            >
              {loadingOlder ? 'Loading\u2026' : 'Load older messages'}
            </button>
          </div>
        )}

        {allMessages.length === 0 && (
          <p className="text-center text-sm text-[--color-text-muted] mt-8">
            No messages yet.
          </p>
        )}

        {allMessages.map((msg) => (
          <div key={msg.rowid}>
            {/* Sender label for incoming group messages */}
            {isGroup && !msg.from_me && msg.sender_name && (
              <p className="text-[10px] text-[--color-text-muted] mb-0.5 ml-1">
                {msg.sender_name}
              </p>
            )}
            <MessageBubble
              msg={msg}
              pending={'pending' in msg && (msg as Message & { pending?: boolean }).pending === true}
            />
          </div>
        ))}
      </div>

      {/* Scroll-to-bottom button */}
      {showScrollBtn && (
        <button
          onClick={scrollToBottom}
          className="absolute bottom-4 right-4 w-9 h-9 rounded-full shadow-lg
                     bg-[--color-accent] text-[--color-bg-primary] text-lg flex items-center justify-center
                     hover:bg-[--color-accent-hover] transition-colors"
          aria-label="Scroll to bottom"
        >
          &#8595;
        </button>
      )}
    </div>
  )
}
