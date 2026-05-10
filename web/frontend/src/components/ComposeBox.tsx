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
 */
import { useState, useRef, KeyboardEvent } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ImagePlus, Send } from 'lucide-react'
import { sendMessage, sendFile } from '../api'
import { useChatStore, nextOptimisticId } from '../store'
import { SlotRenderer } from '../plugins/SlotRenderer'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'

interface ComposeBoxProps {
  handle: string
  isGroup?: boolean
}

export function ComposeBox({ handle, isGroup = false }: ComposeBoxProps) {
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const qc = useQueryClient()
  const addOptimistic = useChatStore((s) => s.addOptimistic)
  const clearOptimistic = useChatStore((s) => s.clearOptimistic)

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
      await sendMessage(handle, trimmed, isGroup)
      await qc.invalidateQueries({ queryKey: ['messages', handle] })
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Send failed')
      clearOptimistic(handle, optId)
      setText(trimmed)
    } finally {
      setSending(false)
      clearOptimistic(handle, optId)
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
      <div
        className="flex items-end gap-2 rounded-[var(--radius-input)] border border-border
                   bg-input px-2 py-1.5 focus-within:border-primary transition-colors"
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
          <ImagePlus className="h-4 w-4" />
        </Button>

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
          <Send className="h-4 w-4" />
        </Button>
      </div>
      <p className="mt-1 text-[10px] text-muted-foreground">
        Enter to send &nbsp;&#183;&nbsp; Shift+Enter for newline
      </p>
    </div>
  )
}
