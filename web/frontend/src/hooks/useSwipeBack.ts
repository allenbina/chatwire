/**
 * Swipe-from-left-edge gesture hook for mobile back navigation.
 *
 * When enabled, a touch that starts within 20px of the left viewport edge
 * and drags horizontally past 75px triggers navigation to '/'.
 *
 * Only active on mobile (< 768px). Does not conflict with vertical swipes
 * (e.g. fullscreen photo overlay dismiss).
 */
import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

const EDGE_THRESHOLD = 20 // px from left edge to start tracking
const DRAG_THRESHOLD = 75 // px horizontal drag to commit navigation

export function useSwipeBack(enabled: boolean) {
  const navigate = useNavigate()

  useEffect(() => {
    if (!enabled) return

    let startX = 0
    let startY = 0
    let tracking = false

    function handleTouchStart(e: TouchEvent) {
      const touch = e.touches[0]
      if (touch.clientX <= EDGE_THRESHOLD) {
        startX = touch.clientX
        startY = touch.clientY
        tracking = true
      }
    }

    function handleTouchMove(e: TouchEvent) {
      if (!tracking) return
      const touch = e.touches[0]
      const dx = touch.clientX - startX
      const dy = Math.abs(touch.clientY - startY)

      // If vertical movement exceeds horizontal, cancel — this is a scroll
      if (dy > dx) {
        tracking = false
        return
      }

      if (dx >= DRAG_THRESHOLD) {
        tracking = false
        navigate('/')
      }
    }

    function handleTouchEnd() {
      tracking = false
    }

    document.addEventListener('touchstart', handleTouchStart, { passive: true })
    document.addEventListener('touchmove', handleTouchMove, { passive: true })
    document.addEventListener('touchend', handleTouchEnd, { passive: true })

    return () => {
      document.removeEventListener('touchstart', handleTouchStart)
      document.removeEventListener('touchmove', handleTouchMove)
      document.removeEventListener('touchend', handleTouchEnd)
    }
  }, [enabled, navigate])
}
