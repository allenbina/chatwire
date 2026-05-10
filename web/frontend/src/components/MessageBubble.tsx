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
import type { Message, Attachment, LinkPreview } from '../api'
import { MediaGallery, PendingAttachment } from './MediaGallery'
import { SlotRenderer } from '../plugins/SlotRenderer'
import { Badge } from '@/components/ui/badge'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const URL_RE = /https?:\/\/[^\s<>"']+/g

function linkify(text: string): string {
  return text.replace(
    URL_RE,
    (url) =>
      `<a href="${url}" target="_blank" rel="noopener noreferrer"
          class="text-[--color-info] underline hover:text-[--color-accent]"
        >${url}</a>`,
  )
}

// ---------------------------------------------------------------------------
// Non-image attachment renderers
// ---------------------------------------------------------------------------

function VideoAttachment({ att }: { att: Attachment }) {
  const src = `/attachment?path=${encodeURIComponent(att.path)}&dl=${encodeURIComponent(att.name)}`
  return (
    <video
      className="w-full rounded"
      controls
      preload="metadata"
      aria-label={att.name}
      src={src}
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
      className="flex items-center gap-2 px-3 py-2 rounded bg-[--color-bg-tertiary]
                 text-xs text-[--color-text-primary] hover:text-[--color-accent] transition-colors"
    >
      <svg
        className="w-4 h-4 shrink-0 text-[--color-text-muted]"
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
      {sizeStr && <span className="shrink-0 text-[--color-text-muted]">{sizeStr}</span>}
    </a>
  )
}

function NonImageAttachment({ att }: { att: Attachment }) {
  if (!att.ready) return <PendingAttachment name={att.name} />
  if (att.kind === 'video') return <VideoAttachment att={att} />
  if (att.kind === 'audio') return <AudioAttachment att={att} />
  return <FileAttachment att={att} />
}

// ---------------------------------------------------------------------------
// Link preview card
// ---------------------------------------------------------------------------

function PreviewCard({ preview }: { preview: LinkPreview }) {
  if (!preview.url && !preview.title) return null
  // Use the attachment endpoint for preview images served from local storage,
  // otherwise fall back to image_url for external OG images.
  const imgSrc = preview.image_url
    ? preview.image_url.startsWith('/')
      ? `${preview.image_url}&size=thumb`
      : preview.image_url
    : null

  return (
    <a
      href={preview.url}
      target="_blank"
      rel="noopener noreferrer"
      className="block mt-1 rounded border border-[--color-border] overflow-hidden
                 hover:border-[--color-accent] transition-colors max-w-xs"
    >
      {imgSrc && (
        <img
          src={imgSrc}
          alt=""
          className="w-full h-32 object-cover"
          loading="lazy"
        />
      )}
      <div className="px-3 py-2 bg-[--color-bg-tertiary]">
        {preview.title && (
          <p className="text-sm font-medium text-[--color-text-primary] truncate">{preview.title}</p>
        )}
        {preview.description && (
          <p className="text-xs text-[--color-text-muted] mt-0.5 line-clamp-2">{preview.description}</p>
        )}
        {preview.url && (
          <p className="text-xs text-[--color-info] mt-0.5 truncate">{preview.url}</p>
        )}
      </div>
    </a>
  )
}

// ---------------------------------------------------------------------------
// Delivery status
// ---------------------------------------------------------------------------

function DeliveryBadge({ status, hint }: { status: string; hint?: string }) {
  if (!status || status === 'delivered') return null
  if (status === 'failed') {
    return (
      <Badge variant="destructive" className="text-[10px] px-1.5 py-0.5" title={hint}>
        failed
      </Badge>
    )
  }
  if (status === 'sent') {
    return (
      <Badge variant="secondary" className="text-[10px] px-1.5 py-0.5">
        sent
      </Badge>
    )
  }
  // ghost / other
  return (
    <Badge variant="outline" className="text-[10px] px-1.5 py-0.5 text-[--color-warning]" title={hint}>
      {status}
    </Badge>
  )
}

// ---------------------------------------------------------------------------
// Main bubble
// ---------------------------------------------------------------------------

interface MessageBubbleProps {
  msg: Message
  pending?: boolean
}

export function MessageBubble({ msg, pending = false }: MessageBubbleProps) {
  const isMine = msg.from_me
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
        'flex flex-col max-w-[75%] gap-0.5',
        isMine ? 'self-end items-end' : 'self-start items-start',
        pending ? 'opacity-60' : '',
      ].join(' ')}
    >
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
          className={[
            'rounded-2xl overflow-hidden flex flex-col gap-0.5',
            isMine ? 'rounded-br-sm' : 'rounded-bl-sm',
            'max-w-xs',
          ].join(' ')}
        >
          {otherAtts.map((a: Attachment, i: number) => (
            <NonImageAttachment key={i} att={a} />
          ))}
        </div>
      )}

      {/* Text bubble */}
      {(msg.text || msg.link_preview) && !msg.link_preview && msg.text && (
        <div
          className={[
            'rounded-2xl px-3 py-2 text-sm break-words',
            isMine
              ? 'rounded-br-sm bg-[--color-msg-me] text-[--color-text-primary]'
              : 'rounded-bl-sm bg-[--color-msg-them] text-[--color-text-primary]',
          ].join(' ')}
        >
          <p
            className="whitespace-pre-wrap"
            dangerouslySetInnerHTML={{ __html: linkify(msg.text) }}
          />
        </div>
      )}

      {/* Text + link preview together */}
      {msg.link_preview && (
        <div
          className={[
            'rounded-2xl px-3 py-2 text-sm break-words',
            isMine
              ? 'rounded-br-sm bg-[--color-msg-me] text-[--color-text-primary]'
              : 'rounded-bl-sm bg-[--color-msg-them] text-[--color-text-primary]',
          ].join(' ')}
        >
          {msg.text && (
            <p
              className="whitespace-pre-wrap mb-1"
              dangerouslySetInnerHTML={{ __html: linkify(msg.text) }}
            />
          )}
          <PreviewCard preview={msg.link_preview} />
        </div>
      )}

      {/* Timestamp + status */}
      <div
        className={[
          'flex items-center gap-1 text-[10px] text-[--color-text-muted]',
          isMine ? 'flex-row-reverse' : '',
        ].join(' ')}
      >
        <span>{msg.ts}</span>
        {isMine && msg.status && (
          <DeliveryBadge status={msg.status} hint={(msg as Message & { hint?: string }).hint} />
        )}
        {pending && <span className="italic">sending&hellip;</span>}
        {/* Plugin slot: extra toolbar items per message */}
        <SlotRenderer slot="message.toolbar" msgRowid={msg.rowid} fromMe={isMine} />
      </div>
    </div>
  )
}
