/**
 * SlidingHighlight — a magnetic hover effect where a single highlight
 * element smoothly transitions between hovered children.
 *
 * Wrap a list of items; the highlight slides to whichever child the
 * mouse enters. On mouse leave it fades out.
 *
 * Uses CSS transitions for the smooth movement — no JS animation frames.
 */
import { useRef, useState, useCallback, type ReactNode } from 'react'

interface Props {
  children: ReactNode
  /** Tailwind classes for the highlight pill (color, radius, etc.) */
  highlightClass?: string
  /** Layout direction */
  direction?: 'vertical' | 'horizontal'
  className?: string
}

export function SlidingHighlight({
  children,
  highlightClass = 'bg-accent rounded-lg',
  direction = 'vertical',
  className = '',
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [rect, setRect] = useState<{ top: number; left: number; width: number; height: number } | null>(null)
  const [visible, setVisible] = useState(false)

  const handleMouseEnter = useCallback((e: React.MouseEvent) => {
    const container = containerRef.current
    if (!container) return
    // Find the closest direct child that was entered
    const target = (e.target as HTMLElement).closest('[data-slide-item]') as HTMLElement | null
    if (!target) return
    const containerRect = container.getBoundingClientRect()
    const targetRect = target.getBoundingClientRect()
    setRect({
      top: targetRect.top - containerRect.top,
      left: targetRect.left - containerRect.left,
      width: targetRect.width,
      height: targetRect.height,
    })
    setVisible(true)
  }, [])

  const handleMouseLeave = useCallback(() => {
    setVisible(false)
  }, [])

  return (
    <div
      ref={containerRef}
      className={`relative ${className}`}
      onMouseOver={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {/* Sliding highlight */}
      <div
        className={`absolute pointer-events-none transition-all duration-200 ease-out ${highlightClass}`}
        style={{
          top: rect?.top ?? 0,
          left: rect?.left ?? 0,
          width: rect?.width ?? 0,
          height: rect?.height ?? 0,
          opacity: visible && rect ? 1 : 0,
        }}
      />
      {/* Content rendered on top */}
      <div className={`relative z-10 ${direction === 'horizontal' ? 'flex items-center' : ''}`}>
        {children}
      </div>
    </div>
  )
}
