/**
 * Popout — minimal chat view (no sidebar, no settings bar).
 *
 * Accepts ?handle=X for 1:1 chats or ?chat=X for group chats.
 * Matches the behaviour of the Jinja2 _popout.html template.
 *
 * Route: /app/popout
 */
import { useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { MessageList } from '../components/MessageList'
import { ComposeBox } from '../components/ComposeBox'
import { applyTheme } from '../hooks/useTheme'
import { useChatStore } from '../store'
import { useSSE, type SSEEvent } from '../hooks/useSSE'

function isGroupHandle(handle: string): boolean {
  return handle.includes(';')
}

export function PopoutPage() {
  const [params] = useSearchParams()
  const qc = useQueryClient()
  const clearOptimistic = useChatStore((s) => s.clearOptimistic)

  const handle = params.get('handle') ?? params.get('chat') ?? ''
  const isGroup = !!params.get('chat') || isGroupHandle(handle)

  // Apply saved theme (same as main app)
  useEffect(() => {
    const saved = localStorage.getItem('chatwire-theme')
    applyTheme(saved ?? 'dracula')
  }, [])

  useSSE({
    onEvent: (event: SSEEvent) => {
      if (event.handle && decodeURIComponent(event.handle) === handle) {
        qc.invalidateQueries({ queryKey: ['messages', handle] })
        if (event.rowid != null) {
          clearOptimistic(handle, event.rowid)
        }
      }
    },
  })

  if (!handle) {
    return (
      <div className="h-screen flex items-center justify-center bg-[--color-bg-primary]
                      text-[--color-text-muted] text-sm">
        No conversation specified. Pass <code>?handle=X</code> or <code>?chat=X</code>.
      </div>
    )
  }

  return (
    <div className="flex flex-col h-screen bg-[--color-bg-primary] text-[--color-text-primary]">
      {/* Minimal header */}
      <header className="flex items-center px-4 py-2 border-b border-[--color-border]
                         bg-[--color-bg-tertiary] flex-shrink-0">
        <span className="text-sm font-medium text-[--color-text-primary] truncate">
          {isGroup ? handle.split(';').pop() || handle : handle}
        </span>
      </header>

      {/* Message feed */}
      <main
        id="messages"
        aria-label="Conversation messages"
        className="flex-1 flex flex-col min-h-0"
        role="log"
        aria-live="polite"
      >
        <MessageList handle={handle} isGroup={isGroup} />
      </main>

      {/* Compose */}
      <ComposeBox handle={handle} isGroup={isGroup} />
    </div>
  )
}
