/**
 * Single message bubble. Renders:
 *  - Image gallery grid (1/2/3/4+ layout matching _messages.html)
 *  - Lightbox for full-size images with prev/next navigation
 *  - Inline HTML5 <video> and <audio> players
 *  - File attachment download links
 *  - Sync-pending spinner for not-yet-ready attachments
 *  - Link preview card
 *  - Text body with URL auto-linking
 *  - Timestamp + delivery status for outgoing messages
 *
 * Accessibility: each bubble has role="article" and an aria-label with
 * sender name + timestamp, matching the Jinja2 _messages.html template.
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import DOMPurify from 'dompurify'
import { toast } from 'sonner'
import type { Message, Attachment, LinkPreview } from '../api'
import { sendTapback, unsendMessage, editMessage } from '../api'
import { MediaGallery, PendingAttachment } from './MediaGallery'
import { SlotRenderer } from '../plugins/SlotRenderer'
import { Badge } from '@/components/ui/badge'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const URL_RE = /https?:\/\/[^\s<>"']+/g

function linkify(text: string): string {
  const linked = text.replace(
    URL_RE,
    (url) =>
      `<a href="${url}" target="_blank" rel="noopener noreferrer"
          class="text-info underline hover:text-primary"
        >${url}</a>`,
  )
  return DOMPurify.sanitize(linked, { ADD_ATTR: ['target'] })
}

// ---------------------------------------------------------------------------
// Non-image attachment renderers
// ---------------------------------------------------------------------------

function VideoAttachment({ att }: { att: Attachment }) {
  // No &dl= param for inline playback — browser will play instead of download.
  // The download fallback link below uses &dl= for explicit download.
  const inlineSrc = `/attachment?path=${encodeURIComponent(att.path)}`
  const downloadSrc = `/attachment?path=${encodeURIComponent(att.path)}&dl=${encodeURIComponent(att.name)}`
  const [videoError, setVideoError] = useState(false)
  if (videoError) {
    return (
      <a
        href={downloadSrc}
        download={att.name}
        className="flex items-center gap-2 px-3 py-2 rounded bg-muted
                   text-xs text-foreground hover:text-primary transition-colors"
      >
        <svg
          className="w-4 h-4 shrink-0 text-muted-foreground"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          viewBox="0 0 24 24"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="7 10 12 15 17 10"/>
          <line x1="12" y1="15" x2="12" y2="3"/>
        </svg>
        <span className="truncate max-w-[200px]">{att.name}</span>
      </a>
    )
  }
  return (
    <video
      className="w-full rounded"
      controls
      preload="metadata"
      aria-label={att.name}
      src={inlineSrc}
      onError={() => setVideoError(true)}
    />
  )
}

function AudioAttachment({ att }: { att: Attachment }) {
  const src = `/attachment?path=${encodeURIComponent(att.path)}&dl=${encodeURIComponent(att.name)}`
  return (
    <audio
      className="w-full px-2 py-1"
      controls
      preload="none"
      aria-label={att.name}
      src={src}
    />
  )
}

function FileAttachment({ att }: { att: Attachment }) {
  const href = `/attachment?path=${encodeURIComponent(att.path)}&dl=${encodeURIComponent(att.name)}`
  const sizeStr = att.total_bytes > 0
    ? att.total_bytes < 1024 * 1024
      ? `${Math.round(att.total_bytes / 1024)} KB`
      : `${(att.total_bytes / (1024 * 1024)).toFixed(1)} MB`
    : ''
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      download={att.name}
      className="flex items-center gap-2 px-3 py-2 rounded bg-muted
                 text-xs text-foreground hover:text-primary transition-colors"
    >
      <svg
        className="w-4 h-4 shrink-0 text-muted-foreground"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        viewBox="0 0 24 24"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
      </svg>
      <span className="truncate max-w-[200px]">{att.name}</span>
      {sizeStr && <span className="shrink-0 text-muted-foreground">{sizeStr}</span>}
    </a>
  )
}

// ---------------------------------------------------------------------------
// VCF contact card
// ---------------------------------------------------------------------------

interface VCardData {
  fn: string
  org: string
  tels: string[]
  emails: string[]
}

function parseVCard(text: string): VCardData {
  const get = (key: string): string => {
    const m = new RegExp(`^${key}[^:\\r\\n]*:([^\\r\\n]+)`, 'im').exec(text)
    return m ? m[1].trim() : ''
  }
  const getAll = (key: string): string[] =>
    [...text.matchAll(new RegExp(`^${key}[^:\\r\\n]*:([^\\r\\n]+)`, 'gim'))].map(
      (m) => m[1].trim(),
    ).filter(Boolean)
  return { fn: get('FN'), org: get('ORG'), tels: getAll('TEL'), emails: getAll('EMAIL') }
}

function VcfCard({ att }: { att: Attachment }) {
  const [card, setCard] = useState<VCardData | null>(null)
  const href = `/attachment?path=${encodeURIComponent(att.path)}&dl=${encodeURIComponent(att.name)}`

  useEffect(() => {
    fetch(href)
      .then((r) => r.text())
      .then((text) => setCard(parseVCard(text)))
      .catch(() => {/* fall through to FileAttachment below */})
  }, [href])

  if (!card) return <FileAttachment att={att} />

  return (
    <div className="flex flex-col gap-1 px-3 py-2 rounded bg-muted text-xs text-foreground min-w-[180px]">
      {card.fn && <p className="font-semibold text-sm">{card.fn}</p>}
      {card.org && <p className="text-muted-foreground">{card.org}</p>}
      {card.tels.map((t, i) => (
        <a key={i} href={`tel:${t}`} className="text-primary hover:underline">
          {t}
        </a>
      ))}
      {card.emails.map((e, i) => (
        <a key={i} href={`mailto:${e}`} className="text-info hover:underline">
          {e}
        </a>
      ))}
      <a
        href={href}
        download={att.name}
        className="mt-1 text-muted-foreground hover:text-primary underline text-[10px]"
      >
        Save contact
      </a>
    </div>
  )
}

function NonImageAttachment({ att }: { att: Attachment }) {
  if (!att.ready) return <PendingAttachment name={att.name} />
  if (att.kind === 'video') return <VideoAttachment att={att} />
  if (att.kind === 'audio') return <AudioAttachment att={att} />
  if (att.kind === 'file' && att.name.toLowerCase().endsWith('.vcf')) return <VcfCard att={att} />
  return <FileAttachment att={att} />
}

// ---------------------------------------------------------------------------
// Link preview card
// ---------------------------------------------------------------------------

function PreviewCard({ preview }: { preview: LinkPreview }) {
  if (!preview.url) return null

  // image_path: local file served via /attachment endpoint (current backend)
  // image_url: external OG image (future backends)
  let imgSrc: string | null = null
  if (preview.image_path) {
    imgSrc = `/attachment?path=${encodeURIComponent(preview.image_path)}&size=thumb`
  } else if (preview.image_url) {
    imgSrc = preview.image_url
  }

  // Prefer explicit title; fall back to domain label.
  const label = preview.title ?? preview.domain ?? null

  // Extract just the domain for display
  const domain = preview.domain ?? (() => {
    try { return new URL(preview.url).hostname; } catch { return ''; }
  })()

  return (
    <a
      href={preview.url}
      target="_blank"
      rel="noopener noreferrer"
      className="block rounded-lg overflow-hidden hover:opacity-90 transition-opacity"
    >
      {imgSrc && (
        <img
          src={imgSrc}
          alt={label ?? ''}
          className="w-full object-cover"
          style={{ maxHeight: 300 }}
          loading="lazy"
        />
      )}
      <div className="px-3 py-2 bg-muted/80">
        {label && (
          <p className="text-sm font-medium text-foreground line-clamp-2">{label}</p>
        )}
        {preview.description && (
          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{preview.description}</p>
        )}
        {domain && domain !== label && (
          <p className="text-xs text-muted-foreground mt-1">{domain}</p>
        )}
      </div>
    </a>
  )
}

// ---------------------------------------------------------------------------
// Delivery status
// ---------------------------------------------------------------------------

function DeliveryBadge({ status, service, hint }: { status: string; service?: string; hint?: string }) {
  if (!status || status === 'delivered') return null
  // SMS "sent" is the normal terminal state — not worth showing a badge for
  if (status === 'sent' && service === 'SMS') return null
  if (status === 'failed') {
    return (
      <Badge variant="destructive" className="text-[10px] px-1.5 py-0.5" title={hint}>
        failed
      </Badge>
    )
  }
  // ghost / other
  return (
    <Badge variant="outline" className="text-[10px] px-1.5 py-0.5 text-warning" title={hint}>
      {status}
    </Badge>
  )
}

// ---------------------------------------------------------------------------
// Location share card
// ---------------------------------------------------------------------------

function LocationCard({ location }: { location: { lat: number | null; lon: number | null; maps_url: string | null } }) {
  if (location.maps_url) {
    return (
      <a
        href={location.maps_url}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center gap-2 rounded-xl bg-muted/60 px-3 py-2 text-sm hover:bg-muted/90 transition-colors"
      >
        <span className="text-lg">📍</span>
        <span className="font-medium">Shared Location</span>
        {location.lat !== null && location.lon !== null && (
          <span className="text-xs text-muted-foreground ml-auto">
            {location.lat.toFixed(4)}, {location.lon.toFixed(4)}
          </span>
        )}
      </a>
    )
  }
  return (
    <div className="flex items-center gap-2 rounded-xl bg-muted/60 px-3 py-2 text-sm">
      <span className="text-lg">📍</span>
      <span className="font-medium">Shared Location</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// iOS-style reply quote — ghost bubble above the reply message
// ---------------------------------------------------------------------------

function ReplyQuote({
  reply,
  fromMe,
  onScrollTo,
}: {
  reply: { rowid: number; text: string; sender: string; image_path?: string }
  fromMe: boolean
  onScrollTo?: (rowid: number) => void
}) {
  // sender is '' when the parent message was from me; non-empty = other person's name
  const parentFromMe = reply.sender === ''
  const senderLabel = reply.sender || 'You'

  const ghostBg = parentFromMe
    ? 'bg-primary/15 border border-primary/25'
    : 'bg-muted/70 border border-border/50'
  const senderColor = parentFromMe ? 'text-primary/80' : 'text-muted-foreground'
  const bodyColor = parentFromMe ? 'text-primary/65' : 'text-foreground/60'
  const connectorColor = parentFromMe ? 'bg-primary/30' : 'bg-muted-foreground/20'

  return (
    <div className={['flex flex-col', fromMe ? 'items-end' : 'items-start'].join(' ')}>
      {/* Ghost bubble — smaller, muted preview of the parent message */}
      <button
        type="button"
        onClick={() => onScrollTo?.(reply.rowid)}
        aria-label={`Reply to ${senderLabel}: ${reply.text || 'Photo'}`}
        className={[
          'text-left rounded-2xl px-3 py-1.5 max-w-[85%]',
          'hover:opacity-80 active:opacity-70 transition-opacity',
          ghostBg,
        ].join(' ')}
        style={{ fontSize: '0.8em' }}
      >
        <p className={['font-semibold truncate mb-0.5 text-[0.75em]', senderColor].join(' ')}>
          {senderLabel}
        </p>
        {reply.image_path ? (
          <img
            src={`/attachment?path=${encodeURIComponent(reply.image_path)}&size=thumb`}
            alt="Photo"
            width={32}
            height={32}
            className="w-8 h-8 rounded object-cover"
          />
        ) : (
          <p className={['line-clamp-2 whitespace-pre-wrap break-words', bodyColor].join(' ')}>
            {reply.text || '🖼️ Photo'}
          </p>
        )}
      </button>

      {/* Thin vertical connector between ghost bubble and reply bubble */}
      <div
        role="presentation"
        className={[
          'w-0.5 h-3 rounded-full',
          fromMe ? 'self-end mr-3.5' : 'self-start ml-3.5',
          connectorColor,
        ].join(' ')}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Hover action bar — reactions + reply + edit + unsend
// ---------------------------------------------------------------------------

const QUICK_REACTIONS = ['❤️', '👍', '👎', '😂', '‼️', '❓'] as const

interface HoverActionBarProps {
  msg: Message
  fromMe: boolean
  ventura: boolean
  onReply: () => void
  onClose: () => void
}

function HoverActionBar({ msg, fromMe, ventura, onReply, onClose }: HoverActionBarProps) {
  const [editMode, setEditMode] = useState(false)
  const [editText, setEditText] = useState(msg.text || '')

  async function handleTapback(emoji: string) {
    try {
      await sendTapback(msg.rowid, emoji)
    } catch {
      toast.error('Tapback failed — check macOS version and Messages.app access.')
    }
    onClose()
  }

  async function handleUnsend() {
    if (!confirm('Unsend this message? It will be retracted for everyone.')) return
    try {
      await unsendMessage(msg.rowid)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Unsend failed')
    }
    onClose()
  }

  async function handleEdit() {
    if (!editMode) {
      setEditMode(true)
      return
    }
    const trimmed = editText.trim()
    if (!trimmed || trimmed === msg.text) {
      setEditMode(false)
      return
    }
    try {
      await editMessage(msg.rowid, trimmed)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Edit failed')
    }
    setEditMode(false)
    onClose()
  }

  function handleReply() {
    onReply()
    onClose()
  }

  const barClass = [
    'flex items-center gap-0.5 rounded-xl px-1.5 py-1',
    'bg-popover border border-border shadow-lg text-sm',
  ].join(' ')

  if (editMode) {
    return (
      <div className={['absolute bottom-full mb-1 z-30 flex gap-1', fromMe ? 'right-0' : 'left-0'].join(' ')}>
        <input
          autoFocus
          className="rounded-lg border border-border bg-input px-2 py-1 text-sm text-foreground min-w-[200px]"
          value={editText}
          onChange={(e) => setEditText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') { e.preventDefault(); handleEdit() }
            if (e.key === 'Escape') { setEditMode(false); onClose() }
          }}
        />
        <button
          type="button"
          onClick={handleEdit}
          className="px-2 py-1 rounded-lg bg-primary text-primary-foreground text-xs hover:opacity-90"
        >
          Save
        </button>
        <button
          type="button"
          onClick={() => { setEditMode(false); onClose() }}
          className="px-2 py-1 rounded-lg bg-muted text-muted-foreground text-xs hover:text-foreground"
        >
          Cancel
        </button>
      </div>
    )
  }

  return (
    <div
      className={['absolute bottom-full mb-1 z-30 flex items-center gap-1', fromMe ? 'right-0' : 'left-0'].join(' ')}
    >
      {/* Reaction pills */}
      <div className={barClass}>
        {QUICK_REACTIONS.map((emoji) => (
          <button
            key={emoji}
            type="button"
            onClick={() => handleTapback(emoji)}
            className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-accent transition-colors leading-none"
            title={emoji}
            aria-label={`React with ${emoji}`}
          >
            {emoji}
          </button>
        ))}
      </div>
      {/* Action pills */}
      <div className={barClass}>
        <button
          type="button"
          onClick={handleReply}
          className="px-2 py-1 rounded-lg text-xs text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
          title="Reply"
        >
          Reply
        </button>
        {fromMe && (
          <button
            type="button"
            onClick={handleEdit}
            disabled={!ventura}
            className="px-2 py-1 rounded-lg text-xs text-muted-foreground hover:text-foreground hover:bg-accent transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            title={ventura ? 'Edit message' : 'Requires macOS 13 (Ventura)'}
          >
            Edit
          </button>
        )}
        {fromMe && (
          <button
            type="button"
            onClick={handleUnsend}
            disabled={!ventura}
            className="px-2 py-1 rounded-lg text-xs text-destructive hover:bg-destructive/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            title={ventura ? 'Unsend message' : 'Requires macOS 13 (Ventura)'}
          >
            Unsend
          </button>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tapback reactions — iMessage-style corner overlay
// ---------------------------------------------------------------------------

function TapbackBar({
  tapbacks,
  fromMe,
}: {
  tapbacks: { type: string; senders: { name: string; time: string }[] }[]
  fromMe: boolean
}) {
  if (!tapbacks || tapbacks.length === 0) return null
  return (
    <div
      className={[
        'absolute -bottom-3 z-10',
        'flex items-center gap-0.5 rounded-full px-1.5 py-0.5',
        'bg-card shadow-sm border border-border/60 text-sm leading-none',
        fromMe ? 'right-1' : 'left-1',
      ].join(' ')}
    >
      {tapbacks.map((tb) => {
        const count = tb.senders.length
        const tooltip = tb.senders.map((s) => (s.time ? `${s.name} · ${s.time}` : s.name)).join('\n')
        return (
          <span
            key={tb.type}
            className="inline-flex items-center gap-[2px] cursor-default"
            title={tooltip}
            aria-label={`${tb.type} ${count}`}
          >
            {tb.type}
            {count > 1 && <span className="text-[10px] text-muted-foreground">{count}</span>}
          </span>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main bubble
// ---------------------------------------------------------------------------

interface MessageBubbleProps {
  msg: Message
  pending?: boolean
  /** In a self-chat, alternate messages are rendered on the opposite side. */
  selfChatAlt?: boolean
  /** Called when user clicks a reply quote to scroll to the original message. */
  onScrollToRowid?: (rowid: number) => void
  /** Called when user triggers a reply from the hover action bar. */
  onReply?: (msg: Message) => void
  /** Whether the host is running macOS 13+ (enables Edit/Unsend). */
  ventura?: boolean
}

export function MessageBubble({
  msg,
  pending = false,
  selfChatAlt = false,
  onScrollToRowid,
  onReply,
  ventura = false,
}: MessageBubbleProps) {
  const [showBar, setShowBar] = useState(false)
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleClose = useCallback(() => setShowBar(false), [])

  // Desktop: show bar on hover. Hide when mouse leaves the entire bubble group.
  function handleMouseEnter() { setShowBar(true) }
  function handleMouseLeave() { setShowBar(false) }

  // Mobile: 500 ms long-press
  function handleTouchStart() {
    longPressTimer.current = setTimeout(() => setShowBar(true), 500)
  }
  function handleTouchEnd() {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current)
      longPressTimer.current = null
    }
  }

  // In a self-chat every message is from_me, but we alternate alignment by
  // rowid parity so odd-rowid bubbles appear on the left as if from another "you".
  const isMine = msg.from_me && !selfChatAlt
  const senderLabel = msg.sender_name ?? (isMine ? 'You' : 'Them')

  // Split attachments: ready images → gallery; everything else → inline
  const readyImages = msg.attachments.filter((a) => a.kind === 'image' && a.ready)
  const otherAtts = [
    ...msg.attachments.filter((a) => a.kind !== 'image'),
    ...msg.attachments.filter((a) => a.kind === 'image' && !a.ready),
  ]

  return (
    <div
      role="article"
      aria-label={`${senderLabel}, ${msg.ts}`}
      className={[
        'flex flex-col max-w-[75%] gap-0.5 group/bubble',
        isMine ? 'self-end items-end' : 'self-start items-start',
        pending ? 'opacity-60' : '',
      ].join(' ')}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
      onTouchMove={handleTouchEnd}
    >
      {/* Inline reply quote */}
      {msg.reply_to && (
        <ReplyQuote reply={msg.reply_to} fromMe={isMine} onScrollTo={onScrollToRowid} />
      )}

      {/* Main content area — wrapped in relative so tapbacks can overlay the corner */}
      <div className={['relative', msg.tapbacks && msg.tapbacks.length > 0 ? 'mb-3' : ''].join(' ')}>

        {/* Gallery grid for ready images */}
        {readyImages.length > 0 && (
          <MediaGallery
            images={readyImages}
            senderName={senderLabel}
            fromMe={isMine}
          />
        )}

        {/* Non-image / pending attachments */}
        {otherAtts.length > 0 && (
          <div
            className="overflow-hidden flex flex-col gap-0.5 max-w-xs"
            style={{
              borderRadius: 'var(--radius-bubble)',
              ...(isMine
                ? { borderBottomRightRadius: 'var(--bubble-tail)' }
                : { borderBottomLeftRadius: 'var(--bubble-tail)' }),
            }}
          >
            {otherAtts.map((a: Attachment, i: number) => (
              <NonImageAttachment key={i} att={a} />
            ))}
          </div>
        )}

        {/* Text bubble */}
        {msg.text && !msg.link_preview && (
          <div
            className={[
              'px-4 py-2 break-words',
              isMine && msg.service === 'SMS'
                ? 'bg-msg-sms text-msg-sms-text'
                : isMine
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-msg-them text-foreground',
            ].join(' ')}
            style={{
              fontSize: 'var(--font-size-message)',
              borderRadius: 'var(--radius-bubble)',
              boxShadow: 'var(--bubble-shadow)',
              ...(isMine
                ? { borderBottomRightRadius: 'var(--bubble-tail)' }
                : { borderBottomLeftRadius: 'var(--bubble-tail)' }),
            }}
          >
            <p
              className="whitespace-pre-wrap"
              dangerouslySetInnerHTML={{ __html: linkify(msg.text) }}
            />
          </div>
        )}

        {/* Link preview — strip the URL from text since the card shows it */}
        {msg.link_preview && (() => {
          // Remove the preview URL from message text to avoid showing it twice
          const strippedText = msg.text && msg.link_preview.url
            ? msg.text.replace(msg.link_preview.url, '').trim()
            : (msg.text ?? '')
          const bubbleClass = [
            'overflow-hidden break-words',
            isMine && msg.service === 'SMS'
              ? 'bg-msg-sms text-msg-sms-text'
              : isMine
                ? 'bg-primary text-primary-foreground'
                : 'bg-msg-them text-foreground',
          ].join(' ')
          return (
            <div
              className={bubbleClass}
              style={{
                fontSize: 'var(--font-size-message)',
                borderRadius: 'var(--radius-bubble)',
                boxShadow: 'var(--bubble-shadow)',
                ...(isMine
                  ? { borderBottomRightRadius: 'var(--bubble-tail)' }
                  : { borderBottomLeftRadius: 'var(--bubble-tail)' }),
              }}
            >
              {strippedText && (
                <p
                  className="whitespace-pre-wrap px-4 py-2"
                  dangerouslySetInnerHTML={{ __html: linkify(strippedText) }}
                />
              )}
              <PreviewCard preview={msg.link_preview} />
            </div>
          )
        })()}

        {/* Location share card */}
        {msg.location && (
          <LocationCard location={msg.location} />
        )}

        {/* Hover action bar — reactions + reply + edit + unsend */}
        {showBar && !pending && (
          <HoverActionBar
            msg={msg}
            fromMe={isMine}
            ventura={ventura}
            onReply={() => onReply?.(msg)}
            onClose={handleClose}
          />
        )}

        {/* Tapback reactions — iMessage-style corner overlay */}
        {msg.tapbacks && msg.tapbacks.length > 0 && (
          <TapbackBar tapbacks={msg.tapbacks} fromMe={isMine} />
        )}
      </div>

      {/* Timestamp + status */}
      <div
        className={[
          'flex items-center gap-1 text-xs text-muted-foreground',
          isMine ? 'flex-row-reverse' : '',
        ].join(' ')}
      >
        <span>{msg.ts}</span>
        {isMine && msg.status && (
          <DeliveryBadge status={msg.status} service={msg.service} hint={(msg as Message & { hint?: string }).hint} />
        )}
        {pending && <span className="italic">sending&hellip;</span>}
        {/* Plugin slot: extra toolbar items per message */}
        <SlotRenderer slot="message.toolbar" msgRowid={msg.rowid} fromMe={isMine} />
      </div>

      {/* Read receipt — shown for sent iMessage messages when recipient read it */}
      {isMine && msg.read && msg.read_at && (
        <p className="text-[10px] text-muted-foreground">
          Read at {msg.read_at}
        </p>
      )}

      {/* SMS fallback: green bubble color is sufficient — no text note needed */}
    </div>
  )
}
