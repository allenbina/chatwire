/**
 * MediaGallery — image gallery grid matching the Jinja2 _messages.html layout.
 *
 * Grid rules (from the Jinja2 template):
 *  1 image  → full width
 *  2 images → side by side
 *  3 images → 2+1 grid
 *  4+ images → 2×2 grid with "+N" overflow badge on the 4th cell
 *
 * Clicking an image opens a full-size shadcn Dialog lightbox with prev/next
 * navigation (click buttons or ← → arrow keys). Escape closes via Radix.
 */
import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogPortal,
  DialogOverlay,
  DialogClose,
  DialogTitle,
} from '@/components/ui/dialog'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import type { Attachment } from '../api'

// ---------------------------------------------------------------------------
// Lightbox
// ---------------------------------------------------------------------------

function Lightbox({
  images,
  startIndex,
  onClose,
}: {
  images: Attachment[]
  startIndex: number
  onClose: () => void
}) {
  const [idx, setIdx] = useState(startIndex)
  const img = images[idx]
  const fullSrc = `/attachment?path=${encodeURIComponent(img.path)}`
  const counterLabel = `Image ${idx + 1} of ${images.length}`

  // Keyboard navigation: ← / → step through images; Escape handled by Radix.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'ArrowLeft') setIdx((i) => Math.max(0, i - 1))
      if (e.key === 'ArrowRight') setIdx((i) => Math.min(images.length - 1, i + 1))
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [images.length])

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogPortal>
        <DialogOverlay className="backdrop-blur-sm" />
        <DialogPrimitive.Content
          className="fixed inset-0 z-50 flex items-center justify-center p-4 focus:outline-none"
          aria-describedby={undefined}
        >
          {/* Visually-hidden title: accessible name for the dialog */}
          <DialogTitle className="sr-only">
            Image lightbox, {images.length} {images.length === 1 ? 'photo' : 'photos'}
          </DialogTitle>

          {/* Close */}
          <DialogClose asChild>
            <button
              className="absolute top-4 right-4 w-10 h-10 rounded-full bg-black/60 text-white
                         flex items-center justify-center text-xl hover:bg-black/80 transition-colors z-10"
              aria-label="Close lightbox"
            >
              ✕
            </button>
          </DialogClose>

          {/* Prev */}
          {images.length > 1 && idx > 0 && (
            <button
              className="absolute left-4 w-10 h-10 rounded-full bg-black/60 text-white
                         flex items-center justify-center text-xl hover:bg-black/80 transition-colors z-10"
              onClick={() => setIdx((i) => i - 1)}
              aria-label="Previous image"
            >
              ‹
            </button>
          )}

          {/* Full-size image */}
          <img
            src={fullSrc}
            alt={counterLabel}
            className="max-w-full max-h-full object-contain rounded-lg shadow-2xl"
          />

          {/* Next */}
          {images.length > 1 && idx < images.length - 1 && (
            <button
              className="absolute right-4 w-10 h-10 rounded-full bg-black/60 text-white
                         flex items-center justify-center text-xl hover:bg-black/80 transition-colors z-10"
              onClick={() => setIdx((i) => i + 1)}
              aria-label="Next image"
            >
              ›
            </button>
          )}

          {/* Counter */}
          {images.length > 1 && (
            <div
              aria-live="polite"
              className="absolute bottom-4 left-1/2 -translate-x-1/2 px-3 py-1 rounded-full
                         bg-black/60 text-white text-xs"
            >
              {idx + 1} / {images.length}
            </div>
          )}
        </DialogPrimitive.Content>
      </DialogPortal>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Gallery grid
// ---------------------------------------------------------------------------

interface MediaGalleryProps {
  images: Attachment[]
  senderName?: string
  fromMe?: boolean
}

export function MediaGallery({ images, senderName, fromMe }: MediaGalleryProps) {
  const [lightboxIdx, setLightboxIdx] = useState<number | null>(null)

  const shown = images.slice(0, 4)
  const overflow = images.length - 4

  // Grid class based on count
  const gridClass: Record<number, string> = {
    1: 'grid-cols-1',
    2: 'grid-cols-2',
    3: 'grid-cols-2',
    4: 'grid-cols-2',
  }
  const cols = gridClass[Math.min(images.length, 4)] ?? 'grid-cols-2'

  return (
    <>
      <div
        className={[
          'grid gap-0.5 overflow-hidden',
          cols,
          fromMe ? 'rounded-2xl rounded-br-sm' : 'rounded-2xl rounded-bl-sm',
          'max-w-xs',
        ].join(' ')}
        role="group"
        aria-label={`Image gallery, ${images.length} photo${images.length !== 1 ? 's' : ''}`}
      >
        {shown.map((att, i) => {
          const isLast = i === 3 && overflow > 0
          const thumbSrc = `/attachment?path=${encodeURIComponent(att.path)}&size=thumb`
          const altText = `Image sent by ${senderName ?? 'You'}`
          return (
            <div key={i} className="relative aspect-square overflow-hidden bg-card">
              <button
                type="button"
                className="block w-full h-full"
                onClick={() => setLightboxIdx(i)}
                aria-label={altText}
              >
                <img
                  src={thumbSrc}
                  alt={altText}
                  className="w-full h-full object-cover hover:opacity-90 transition-opacity"
                  loading="lazy"
                />
              </button>
              {isLast && (
                <div
                  className="absolute inset-0 bg-black/60 flex items-center justify-center
                               text-white font-bold text-lg pointer-events-none"
                >
                  +{overflow}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {lightboxIdx !== null && (
        <Lightbox
          images={images}
          startIndex={lightboxIdx}
          onClose={() => setLightboxIdx(null)}
        />
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Sync-pending spinner overlay (for not-yet-ready images)
// ---------------------------------------------------------------------------

export function PendingAttachment({ name }: { name: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground px-4 py-2">
      <svg
        aria-hidden="true"
        className="w-4 h-4 animate-spin text-primary"
        viewBox="0 0 24 24"
        fill="none"
      >
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
        />
      </svg>
      <span className="truncate max-w-[180px]">{name || 'syncing attachment…'}</span>
    </div>
  )
}
