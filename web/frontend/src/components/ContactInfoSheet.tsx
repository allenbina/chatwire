/**
 * Contact info sheet — slides in from the right when the user clicks the
 * conversation name/avatar in the chat header.
 *
 * Shows:
 *   - Contact name + subtitle (handle for 1:1, member count for groups)
 *   - Handle rows with capability labels (1:1 only)
 *   - Group member list (groups only)
 *   - Shared media thumbnail grid (first 30 shown; "Show all" expands)
 *   - "Remove from whitelist" button with a confirmation step
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import {
  fetchContactInfo,
  removeFromWhitelist,
  type ContactInfo,
} from '../api'
import { Lightbox } from './MediaGallery'
import type { Attachment } from '../api'

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const MEDIA_PAGE = 30

function MediaGrid({ media }: { media: ContactInfo['media'] }) {
  const [showAll, setShowAll] = useState(false)
  const [lightboxIdx, setLightboxIdx] = useState<number | null>(null)
  const visible = showAll ? media : media.slice(0, MEDIA_PAGE)

  // Build image-only list for the lightbox (videos can't be lightboxed)
  const imageMedia = media.filter((m) => m.kind === 'image')

  return (
    <section className="mb-6">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
        Media ({media.length})
      </h3>
      <div className="grid grid-cols-3 gap-1">
        {visible.map((m, i) => (
          <button
            key={i}
            type="button"
            className="aspect-square bg-card rounded overflow-hidden flex items-center justify-center
                       hover:opacity-80 transition-opacity cursor-pointer"
            title={m.name}
            onClick={() => {
              if (m.kind === 'image') {
                const imgIdx = imageMedia.findIndex((im) => im.path === m.path)
                if (imgIdx >= 0) setLightboxIdx(imgIdx)
              } else {
                // Open video/file in new tab
                window.open(`/attachment?path=${encodeURIComponent(m.path)}`, '_blank')
              }
            }}
          >
            {m.kind === 'image' ? (
              <img
                src={`/attachment?path=${encodeURIComponent(m.path)}&size=thumb`}
                alt={m.name}
                className="w-full h-full object-cover"
                loading="lazy"
              />
            ) : (
              <div className="flex flex-col items-center gap-0.5">
                <svg
                  className="text-muted-foreground"
                  style={{ width: 'var(--icon-size-lg)', height: 'var(--icon-size-lg)' }}
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="var(--icon-stroke)"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <polygon points="5 3 19 12 5 21 5 3" />
                </svg>
                <span className="text-[10px] text-muted-foreground">video</span>
              </div>
            )}
          </button>
        ))}
      </div>
      {!showAll && media.length > MEDIA_PAGE && (
        <button
          onClick={() => setShowAll(true)}
          className="mt-2 text-xs text-primary hover:underline"
        >
          Show all ({media.length})
        </button>
      )}

      {/* Lightbox for images */}
      {lightboxIdx !== null && imageMedia.length > 0 && (
        <Lightbox
          images={imageMedia as Attachment[]}
          startIndex={lightboxIdx}
          onClose={() => setLightboxIdx(null)}
        />
      )}
    </section>
  )
}

interface RemoveButtonProps {
  isGroup: boolean
  onConfirm: () => void
  isPending: boolean
}

function RemoveButton({ isGroup, onConfirm, isPending }: RemoveButtonProps) {
  const [confirming, setConfirming] = useState(false)
  const noun = isGroup ? 'group' : 'contact'

  if (confirming) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-destructive">
          Remove this {noun} from the whitelist? Messages will no longer be relayed.
        </p>
        <div className="flex gap-2">
          <button
            onClick={onConfirm}
            disabled={isPending}
            className="px-3 py-1 text-sm rounded bg-destructive text-white
                       hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {isPending ? 'Removing…' : 'Remove'}
          </button>
          <button
            onClick={() => setConfirming(false)}
            className="px-3 py-1 text-sm rounded border border-border
                       text-muted-foreground hover:bg-card transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    )
  }

  return (
    <button
      onClick={() => setConfirming(true)}
      className="text-sm text-destructive hover:underline"
    >
      Remove from whitelist
    </button>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface Props {
  open: boolean
  onClose: () => void
  /** Resolved real handle (1:1) or group GUID. */
  handle: string
  isGroup: boolean
  /**
   * Called after a successful "Remove from whitelist" deletion.
   * If provided, it is called instead of `onClose` so the caller can
   * navigate away from the now-removed conversation. Falls back to
   * `onClose` when omitted (e.g. in tests that don't need navigation).
   */
  onRemoved?: () => void
}

export function ContactInfoSheet({ open, onClose, handle, isGroup, onRemoved }: Props) {
  const qc = useQueryClient()

  const { data, isLoading, isError } = useQuery({
    queryKey: ['contact-info', handle],
    queryFn: () => fetchContactInfo(handle, isGroup),
    enabled: open && !!handle,
    staleTime: 60_000,
  })

  const removeMutation = useMutation({
    mutationFn: () => removeFromWhitelist(handle, isGroup),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conversations'] })
      // Prefer onRemoved (caller navigates away) over onClose (just hides sheet).
      ;(onRemoved ?? onClose)()
    },
  })

  const title = data?.name || (isLoading ? '' : handle)
  const subtitle = data?.subtitle ?? ''

  return (
    <Sheet open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <SheetContent
        side="right"
        className="w-80 sm:w-96 overflow-y-auto bg-background border-border"
      >
        <SheetHeader className="mb-5">
          <SheetTitle className="text-foreground">
            {isLoading ? <span className="animate-pulse">Loading…</span> : title}
          </SheetTitle>
          {subtitle && (
            <SheetDescription className="text-muted-foreground">
              {subtitle}
            </SheetDescription>
          )}
        </SheetHeader>

        {isError && (
          <p className="text-sm text-destructive">Failed to load contact info.</p>
        )}

        {data && (
          <>
            {/* Handles (1:1) */}
            {data.kind === 'handle' && data.handles.length > 0 && (
              <section className="mb-6">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                  Handles
                </h3>
                <ul className="space-y-2">
                  {data.handles.map((h) => (
                    <li key={h.handle}>
                      <span className="font-mono text-sm text-foreground break-all">
                        {h.handle}
                      </span>
                      {h.capability && (
                        <span className={`ml-2 text-xs ${h.cap_class}`}>
                          {h.capability}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* Members (group) */}
            {data.kind === 'group' && data.members.length > 0 && (
              <section className="mb-6">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                  Members ({data.members.length})
                </h3>
                <ul className="space-y-2">
                  {data.members.map((m) => (
                    <li key={m.handle} className="text-sm">
                      <span className="font-medium text-foreground">
                        {m.name || m.handle}
                      </span>
                      {m.name && (
                        <span className="ml-1 text-xs font-mono text-muted-foreground">
                          ({m.handle})
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* Shared media */}
            {data.media.length > 0 ? (
              <MediaGrid media={data.media} />
            ) : (
              <p className="text-sm text-muted-foreground mb-6">No shared media.</p>
            )}

            {/* Remove from whitelist */}
            <div className="border-t border-border pt-4">
              <RemoveButton
                isGroup={isGroup}
                onConfirm={() => removeMutation.mutate()}
                isPending={removeMutation.isPending}
              />
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  )
}
