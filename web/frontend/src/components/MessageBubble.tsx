/**
 * Single message bubble. Renders:
 *  - Text body (with basic URL auto-linking)
 *  - Image thumbnails (via the /attachment endpoint)
 *  - Non-image attachment chips
 *  - Link preview card (pluginPayloadAttachment or OG fallback)
 *  - Timestamp + delivery status for outgoing messages
 *
 * Outgoing (from_me) messages align right with --color-msg-me.
 * Incoming messages align left with --color-msg-them.
 */
import type { Message, Attachment, LinkPreview } from '../api'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const URL_RE = /https?:\/\/[^\s<>"']+/g

function linkify(text: string): string {
  return text.replace(
    URL_RE,
    (url) => `<a href="${url}" target="_blank" rel="noopener noreferrer"
        class="text-[--color-info] underline hover:text-[--color-accent]"
      >${url}</a>`,
  )
}

function statusIcon(status?: string): string {
  if (!status) return ''
  if (status === 'delivered') return '&#10003;&#10003;' // ✓✓
  if (status === 'read') return '&#10003;&#10003;'
  if (status === 'sent') return '&#10003;'
  if (status === 'failed') return '&#x26A0;' // ⚠
  return ''
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ImageAttachment({ att }: { att: Attachment }) {
  if (!att.ready) {
    return (
      <div className="h-24 w-40 rounded bg-[--color-bg-tertiary] flex items-center justify-center text-xs text-[--color-text-muted]">
        Downloading&hellip;
      </div>
    )
  }
  const src = `/attachment?path=${encodeURIComponent(att.path)}&size=thumb`
  const full = `/attachment?path=${encodeURIComponent(att.path)}`
  return (
    <a href={full} target="_blank" rel="noopener noreferrer" className="block">
      <img
        src={src}
        alt={att.name}
        className="max-h-48 max-w-xs rounded object-cover hover:opacity-90 transition-opacity"
        loading="lazy"
      />
    </a>
  )
}

function FileChip({ att }: { att: Attachment }) {
  const href = `/attachment?path=${encodeURIComponent(att.path)}&dl=1`
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-center gap-2 px-3 py-2 rounded bg-[--color-bg-tertiary]
                 text-xs text-[--color-text-secondary] hover:text-[--color-accent] transition-colors"
    >
      <span>&#128196;</span>
      <span className="truncate max-w-[180px]">{att.name}</span>
    </a>
  )
}

function PreviewCard({ preview }: { preview: LinkPreview }) {
  if (!preview.url && !preview.title) return null
  return (
    <a
      href={preview.url}
      target="_blank"
      rel="noopener noreferrer"
      className="block mt-1 rounded border border-[--color-border] overflow-hidden
                 hover:border-[--color-accent] transition-colors max-w-xs"
    >
      {preview.image_url && (
        <img
          src={preview.image_url}
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
// Main bubble
// ---------------------------------------------------------------------------

interface MessageBubbleProps {
  msg: Message
  /** True for optimistic (pending) messages */
  pending?: boolean
}

export function MessageBubble({ msg, pending = false }: MessageBubbleProps) {
  const isMine = msg.from_me

  const imageAtts = msg.attachments.filter((a) => a.kind === 'image')
  const otherAtts = msg.attachments.filter((a) => a.kind !== 'image')

  return (
    <div
      className={[
        'flex flex-col max-w-[75%] gap-0.5',
        isMine ? 'self-end items-end' : 'self-start items-start',
        pending ? 'opacity-60' : '',
      ].join(' ')}
    >
      {/* Attachment images above bubble */}
      {imageAtts.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {imageAtts.map((a, i) => (
            <ImageAttachment key={i} att={a} />
          ))}
        </div>
      )}

      {/* Text bubble */}
      {(msg.text || otherAtts.length > 0 || msg.link_preview) && (
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
              className="whitespace-pre-wrap"
              dangerouslySetInnerHTML={{ __html: linkify(msg.text) }}
            />
          )}

          {otherAtts.map((a, i) => (
            <FileChip key={i} att={a} />
          ))}

          {msg.link_preview && <PreviewCard preview={msg.link_preview} />}
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
          <span
            className={msg.status === 'failed' ? 'text-[--color-error]' : 'text-[--color-success]'}
            dangerouslySetInnerHTML={{ __html: statusIcon(msg.status) }}
          />
        )}
        {pending && <span className="italic">sending&hellip;</span>}
      </div>
    </div>
  )
}
