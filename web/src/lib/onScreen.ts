// A menu or list opened beside its button stays on the screen (10 Nov, at phone width: the "Show" menu ran off the
// left edge, a day's deadlines off the right, and the page scrolled sideways). Measured when it opens and slid
// back inside, never past the other edge.

import { useLayoutEffect, useRef } from "react"

/** How far to slide something at [left, right] to stay on a screen `width` wide, `margin` from its edges. */
export function slideInto(left: number, right: number, width: number, margin = 12): number {
  if (right > width - margin) return -Math.min(right - (width - margin), Math.max(0, left - margin)) || 0
  if (left < margin) return Math.min(margin - left, Math.max(0, width - margin - right))
  return 0
}

/** A ref for a floating element: while `open`, it is slid onto the screen if it would run off it. */
export function useOnScreen<T extends HTMLElement>(open: boolean) {
  const ref = useRef<T>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!open || !el) return
    el.style.translate = ""
    const r = el.getBoundingClientRect()
    const dx = slideInto(r.left, r.right, window.innerWidth)
    if (dx) el.style.translate = `${dx}px 0`
  }, [open])
  return ref
}
