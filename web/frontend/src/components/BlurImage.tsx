/**
 * Image component with LQIP (Low Quality Image Placeholder) blur effect.
 *
 * Shows a tiny (~20px) blurred placeholder immediately while the full
 * thumbnail loads. The LQIP is fetched as a base64 data URI from the
 * server's ?size=lqip endpoint and cached in a module-level Map.
 */
import { useState, useEffect, useRef, ImgHTMLAttributes } from 'react'

// Module-level LQIP cache — survives re-renders, shared across all instances.
const lqipCache = new Map<string, string>()

interface BlurImageProps extends ImgHTMLAttributes<HTMLImageElement> {
  /** The attachment path (used to derive the LQIP URL). */
  attachmentPath: string
}

export function BlurImage({ attachmentPath, src, className, style, ...rest }: BlurImageProps) {
  const [lqip, setLqip] = useState<string | null>(() => lqipCache.get(attachmentPath) ?? null)
  const [loaded, setLoaded] = useState(false)
  const imgRef = useRef<HTMLImageElement>(null)

  // Fetch LQIP on mount if not cached
  useEffect(() => {
    if (lqipCache.has(attachmentPath)) {
      setLqip(lqipCache.get(attachmentPath)!)
      return
    }
    const url = `/attachment?path=${encodeURIComponent(attachmentPath)}&size=lqip`
    fetch(url, { credentials: 'same-origin' })
      .then((r) => (r.ok ? r.text() : null))
      .then((dataUri) => {
        if (dataUri) {
          lqipCache.set(attachmentPath, dataUri)
          setLqip(dataUri)
        }
      })
      .catch(() => {})
  }, [attachmentPath])

  // Check if already cached by the browser (complete before onLoad fires)
  useEffect(() => {
    if (imgRef.current?.complete && imgRef.current.naturalWidth > 0) {
      setLoaded(true)
    }
  }, [])

  return (
    <span className="relative inline-block" style={style}>
      {/* LQIP blur placeholder */}
      {lqip && !loaded && (
        <img
          src={lqip}
          aria-hidden="true"
          className={className}
          style={{
            filter: 'blur(10px)',
            transform: 'scale(1.1)',
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            objectFit: 'cover',
          }}
        />
      )}
      {/* Real image */}
      <img
        ref={imgRef}
        src={src}
        className={className}
        onLoad={() => setLoaded(true)}
        style={{ opacity: loaded ? 1 : lqip ? 0 : 1 }}
        {...rest}
      />
    </span>
  )
}
