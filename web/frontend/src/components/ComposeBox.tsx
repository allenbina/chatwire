/**
 * Text input + send button for outgoing messages.
 *
 * Behaviour:
 * - Enter sends (Shift+Enter inserts newline).
 * - Optimistic message added to zustand on submit; real message arrives
 *   via SSE / react-query refetch and the optimistic entry is cleared.
 * - Rate-limit / spam errors shown inline for 4 s.
 * - Paperclip button opens a file picker; selected file is uploaded and
 *   sent via POST /api/ui/upload with a pending indicator.
 */
import { useState, useRef, KeyboardEvent } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { sendMessage, sendFile } from '../api'
import { useChatStore, nextOptimisticId } from '../store'

interface ComposeBoxProps {
  handle: string
  isGroup?: boolean
}

export function ComposeBox({ handle, isGroup = false }: ComposeBoxProps) {
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
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

    // Add optimistic message immediately
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
    setError(null)

    // Auto-resize textarea back to one row
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }

    try {
      await sendMessage(handle, trimmed, isGroup)
      // Invalidate messages so react-query refetches and includes the real msg.
      await qc.invalidateQueries({ queryKey: ['messages', handle] })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Send failed')
      // Remove the optimistic entry on failure so the user can retry.
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
    setError(null)

    const optId = nextOptimisticId()
    const now = new Date()
    const ts = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    // Optimistic placeholder for the file
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
      setError(err instanceof Error ? err.message : 'Upload failed')
      clearOptimistic(handle, optId)
    } finally {
      setSending(false)
      clearOptimistic(handle, optId)
      // Reset file input so the same file can be re-selected
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
    // Auto-grow up to ~6 lines
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 144) + 'px'
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) doUpload(file)
  }

  // Clear inline error after 4 s
  if (error) {
    setTimeout(() => setError(null), 4_000)
  }

  return (
    <div className="border-t border-[--color-border] bg-[--color-bg-primary] px-4 py-3">
      {error && (
        <p className="mb-2 text-xs text-[--color-error]">{error}</p>
      )}
      <div
        className="flex items-end gap-2 rounded-xl border border-[--color-border]
                   bg-[--color-input-bg] px-3 py-2 focus-within:border-[--color-accent] transition-colors"
      >
        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          onChange={handleFileChange}
          accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.zip"
        />

        {/* Paperclip button */}
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={sending}
          aria-label="Attach file"
          title="Attach file"
          className="flex-shrink-0 w-7 h-7 rounded flex items-center justify-center
                     text-[--color-text-muted] hover:text-[--color-accent]
                     disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-base"
        >
          &#128206;
        </button>

        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          rows={1}
          placeholder="Message…"
          disabled={sending}
          className="flex-1 resize-none bg-transparent text-sm text-[--color-text-primary]
                     placeholder:text-[--color-text-muted] outline-none leading-snug"
          style={{ maxHeight: '144px' }}
        />
        <button
          onClick={doSend}
          disabled={!text.trim() || sending}
          aria-label="Send message"
          className="flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center
                     bg-[--color-accent] text-[--color-bg-primary] font-bold text-sm
                     hover:bg-[--color-accent-hover] disabled:opacity-40 disabled:cursor-not-allowed
                     transition-colors"
        >
          &#x27A4;
        </button>
      </div>
      <p className="mt-1 text-[10px] text-[--color-text-muted]">
        Enter to send &nbsp;&#183;&nbsp; Shift+Enter for newline
      </p>
    </div>
  )
}
