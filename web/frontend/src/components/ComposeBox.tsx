/**
 * Text input + send button for outgoing messages.
 *
 * Behaviour:
 * - Enter sends (Shift+Enter inserts newline).
 * - Optimistic message added to zustand on submit; real message arrives
 *   via SSE / react-query refetch and the optimistic entry is cleared.
 * - Rate-limit / spam errors shown via Sonner toast.
 * - ImagePlus button opens a file picker; selected file is uploaded and
 *   sent via POST /api/ui/upload with a pending indicator.
 * - When the anti-spam fuse is active (steps 1-3) the compose area is
 *   replaced by a cooldown banner with a live countdown timer.
 */
import { useState, useRef, useEffect, KeyboardEvent } from 'react'
import { useQueryClient, useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ImagePlus, Send, Smile, TriangleAlert } from 'lucide-react'
import { sendMessage, sendFile, getFuseStatus } from '../api'
import { playSentSound } from '../hooks/useSounds'
import { useChatStore, nextOptimisticId } from '../store'
import { SlotRenderer } from '../plugins/SlotRenderer'
import { useOnline } from '../hooks/useOnline'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover'
import { EmojiPicker } from './emoji'
interface ComposeBoxProps {
  handle: string
  isGroup?: boolean
  /** If set, show a "Replying to…" banner and include this guid on send. */
  replyToGuid?: string
  /** Text excerpt shown in the reply banner. */
  replyToText?: string
  /** Called when the user dismisses the reply context. */
  onClearReply?: () => void
}

function formatCountdown(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

function CooldownBanner({ countdown }: { countdown: number | null }) {
  return (
    <div className="rounded-lg border border-amber-500/40 bg-amber-50/5 px-4 py-3 text-sm">
      <p className="font-medium text-amber-600 dark:text-amber-400 flex items-center gap-1.5">
        <TriangleAlert className="w-4 h-4 flex-shrink-0" style={{ width: 'var(--icon-size-md)', height: 'var(--icon-size-md)' }} aria-hidden="true" />
        Sends paused{countdown != null && countdown > 0 ? ` for ${formatCountdown(countdown)}` : ''} — chatwire detected a broadcast pattern.
      </p>
      <p className="text-xs text-muted-foreground mt-1">Normal chatting resumes soon.</p>
    </div>
  )
}

function LockoutFooterNote({ step }: { step: number }) {
  const isPermanent = step >= 6
  return (
    <div
      className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm"
      data-testid="lockout-footer-note"
    >
      <p className="text-destructive/80 flex items-center gap-1.5">
        <TriangleAlert className="w-4 h-4 flex-shrink-0" style={{ width: 'var(--icon-size-md)', height: 'var(--icon-size-md)' }} aria-hidden="true" />
        {isPermanent
          ? <>Messaging permanently locked — enter unlock code in <a href="/settings" className="underline font-medium">Settings</a>.</>
          : <>Messaging locked — cooling down. View status in <a href="/settings" className="underline font-medium">Settings</a>.</>
        }
      </p>
    </div>
  )
}

export function ComposeBox({ handle, isGroup = false, replyToGuid = '', replyToText = '', onClearReply }: ComposeBoxProps) {
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [countdown, setCountdown] = useState<number | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const qc = useQueryClient()
  const addOptimistic = useChatStore((s) => s.addOptimistic)
  const clearOptimistic = useChatStore((s) => s.clearOptimistic)
  const isOnline = useOnline()

  const { data: fuseStatus } = useQuery({
    queryKey: ['fuse-status'],
    queryFn: getFuseStatus,
    staleTime: 0,
    refetchInterval: false,
  })

  // Sync countdown from API response whenever fuse status is refreshed
  useEffect(() => {
    if (
      fuseStatus?.locked &&
      fuseStatus.step >= 1 &&
      fuseStatus.step <= 3 &&
      fuseStatus.cooldown_remaining_s != null
    ) {
      setCountdown(Math.ceil(fuseStatus.cooldown_remaining_s))
    } else {
      setCountdown(null)
    }
  }, [fuseStatus])

  // Tick countdown; re-fetch fuse status when it reaches zero
  useEffect(() => {
    if (countdown == null) return
    if (countdown <= 0) {
      qc.invalidateQueries({ queryKey: ['fuse-status'] })
      return
    }
    const t = setTimeout(
      () => setCountdown((c) => (c != null ? c - 1 : null)),
      1000,
    )
    return () => clearTimeout(t)
  }, [countdown, qc])

  // True when the fuse is actively cooling down (steps 1-3 only)
  const isCoolingDown = !!(
    fuseStatus?.locked &&
    fuseStatus.step >= 1 &&
    fuseStatus.step <= 3
  )

  // True when full lockout is in effect (steps 4+)
  const isLockedOut = !!(fuseStatus?.locked && fuseStatus.step >= 4)

  async function doSend() {
    const trimmed = text.trim()
    if (!trimmed || sending) return

    const optId = nextOptimisticId()
    const now = new Date()
    const ts = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

    addOptimistic(handle, {
      rowid: optId,
      date: Math.floor(now.getTime() / 1000),
      from_me: true,
      ts,
      text: trimmed,
      attachments: [],
      link_preview: null,
      pending: true,
    } as never)

    setText('')
    setSending(true)

    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }

    try {
      await sendMessage(handle, trimmed, isGroup, replyToGuid)
      onClearReply?.()
      playSentSound()
      await qc.invalidateQueries({ queryKey: ['messages', handle] })
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Send failed')
      clearOptimistic(handle, optId)
      setText(trimmed)
    } finally {
      setSending(false)
      clearOptimistic(handle, optId)
      qc.invalidateQueries({ queryKey: ['fuse-status'] })
    }
  }

  async function doUpload(file: File) {
    if (sending) return
    setSending(true)

    const optId = nextOptimisticId()
    const now = new Date()
    const ts = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    addOptimistic(handle, {
      rowid: optId,
      date: Math.floor(now.getTime() / 1000),
      from_me: true,
      ts,
      text: '',
      attachments: [{
        path: '',
        name: file.name,
        mime: file.type,
        kind: file.type.startsWith('image/') ? 'image' : 'file',
        ready: false,
        is_plugin: false,
        total_bytes: file.size,
      }],
      link_preview: null,
      pending: true,
    } as never)

    try {
      await sendFile(handle, isGroup, file)
      await qc.invalidateQueries({ queryKey: ['messages', handle] })
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Upload failed')
      clearOptimistic(handle, optId)
    } finally {
      setSending(false)
      clearOptimistic(handle, optId)
      qc.invalidateQueries({ queryKey: ['fuse-status'] })
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      doSend()
    }
  }

  function handleInput() {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 144) + 'px'
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) doUpload(file)
  }

  return (
    <div className="border-t border-border bg-background px-4 py-3">
      <SlotRenderer slot="compose.extension" handle={handle} />

      {isLockedOut ? (
        <LockoutFooterNote step={fuseStatus!.step} />
      ) : (
        <>
      {/* Offline notice — shown above compose area when network is unavailable */}
      {!isOnline && (
        <div className="mb-2 px-3 py-1.5 rounded-md border border-destructive/30 bg-destructive/5 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-destructive flex-shrink-0" aria-hidden="true" />
          <span className="text-xs text-destructive">
            No connection — messages will send when back online
          </span>
        </div>
      )}

      {/* Reply context banner */}
      {replyToGuid && (
        <div className="mb-2 flex items-center justify-between gap-2 rounded-md border border-border bg-muted px-3 py-1.5 text-xs text-muted-foreground">
          <span className="truncate">
            <span className="font-medium text-foreground">Replying to: </span>
            {replyToText ? replyToText.slice(0, 80) : '…'}
          </span>
          <button
            type="button"
            onClick={onClearReply}
            className="flex-shrink-0 hover:text-foreground transition-colors"
            aria-label="Cancel reply"
          >
            ✕
          </button>
        </div>
      )}

      {isCoolingDown ? (
        <CooldownBanner countdown={countdown} />
      ) : (
        <>
          <div
            className="flex items-end gap-2 rounded-[var(--radius-input)] border border-border
                       bg-input px-3 py-2 focus-within:border-primary transition-colors"
          >
            {/* Hidden file input */}
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              onChange={handleFileChange}
              accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.zip"
            />

            {/* Attach button */}
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => fileInputRef.current?.click()}
              disabled={sending}
              aria-label="Attach file"
              title="Attach file"
              className="flex-shrink-0 h-7 w-7 text-muted-foreground hover:text-primary
                         hover:bg-transparent"
            >
              <ImagePlus className="h-4 w-4" style={{ width: 'var(--icon-size-md)', height: 'var(--icon-size-md)' }} />
            </Button>

            {/* Emoji picker — hidden on mobile (saves real estate, iOS keyboard has emoji) */}
            <Popover>
              <PopoverTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  disabled={sending}
                  aria-label="Insert emoji"
                  title="Insert emoji"
                  className="flex-shrink-0 h-7 w-7 text-muted-foreground hover:text-primary hover:bg-transparent hidden md:inline-flex"
                >
                  <Smile style={{ width: 'var(--icon-size-md)', height: 'var(--icon-size-md)' }} />
                </Button>
              </PopoverTrigger>
              <PopoverContent
                side="top"
                align="start"
                className="p-0 border shadow-lg rounded-xl overflow-hidden"
                style={{
                  backgroundColor: 'var(--reaction-panel-bg)',
                  borderColor: 'var(--reaction-panel-border)',
                  width: 350,
                }}
              >
                <EmojiPicker
                  onSelect={(emoji) => {
                    const ta = textareaRef.current
                    if (!ta) return
                    const start = ta.selectionStart ?? text.length
                    const end = ta.selectionEnd ?? text.length
                    const next = text.slice(0, start) + emoji + text.slice(end)
                    setText(next)
                    requestAnimationFrame(() => {
                      ta.focus()
                      const pos = start + emoji.length
                      ta.setSelectionRange(pos, pos)
                    })
                  }}
                />
              </PopoverContent>
            </Popover>

            {/* Message textarea */}
            <Textarea
              ref={textareaRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={handleKeyDown}
              onInput={handleInput}
              rows={1}
              placeholder="Message…"
              disabled={sending}
              aria-label="Type a message"
              className="flex-1 min-h-0 resize-none border-0 bg-transparent shadow-none
                         text-sm text-foreground placeholder:text-muted-foreground
                         focus-visible:ring-0 focus-visible:ring-offset-0 p-1 leading-snug"
              style={{ maxHeight: '144px' }}
            />

            {/* Send button */}
            <Button
              onClick={doSend}
              disabled={!text.trim() || sending}
              aria-label="Send message"
              size="icon"
              className="flex-shrink-0 h-8 w-8 rounded-lg"
            >
              <Send className="h-4 w-4" style={{ width: 'var(--icon-size-md)', height: 'var(--icon-size-md)' }} />
            </Button>
          </div>
          <p className="mt-1 text-[10px] text-muted-foreground hidden md:block">
            Enter to send &nbsp;&#183;&nbsp; Shift+Enter for newline
          </p>
        </>
      )}
        </>
      )}
    </div>
  )
}
