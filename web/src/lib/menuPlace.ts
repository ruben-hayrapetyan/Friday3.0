// A dropdown's list is drawn over the page, measured from its button, so no column or card that clips its content can
// cut it off (15 Nov, the user: "under the projects page, the dropdown to select a tag gets cut off": an exam card
// clips its corners and the list fell past its foot; a project's column clips sideways and the list ran past its left
// edge). Below the button, or above it when there's no room below; its right edge at the button's, slid to stay on the
// screen. The list stays where it is in the page, so a click on it is still a click inside its menu, its dialog or its
// panel. Kept in place as the page scrolls or the window resizes.

import { type RefObject, useLayoutEffect } from "react"
import { slideInto } from "./onScreen"

const GAP = 4
const MARGIN = 12

export type Placed = { top: number; left: number; maxHeight: number }

/** Where a list `width` × `height` goes beside a button at `button`, on a window `w` × `h`. */
export function placeList(button: { top: number; bottom: number; left: number; right: number }, width: number, height: number, w: number, h: number): Placed {
  const below = h - MARGIN - (button.bottom + GAP)
  const above = button.top - GAP - MARGIN
  const down = height <= below || below >= above
  const room = Math.max(80, down ? below : above)
  const tall = Math.min(height, room)
  const top = down ? button.bottom + GAP : button.top - GAP - tall
  const left = button.right - width
  return { top, left: left + slideInto(left, left + width, w, MARGIN), maxHeight: room }
}

/** While `open`, the list is fixed over the page beside its button. A transformed parent (the Now bar) makes "fixed"
 * count from itself, not the window: where it lands is measured and the difference taken off. */
export function useMenuPlace(open: boolean, button: RefObject<HTMLElement | null>, list: RefObject<HTMLElement | null>) {
  useLayoutEffect(() => {
    const el = list.current
    const at = button.current
    if (!open || !el || !at) return
    const place = () => {
      const b = at.getBoundingClientRect()
      Object.assign(el.style, { position: "fixed", right: "auto", bottom: "auto", top: "0px", left: "0px", maxHeight: "" })
      const origin = el.getBoundingClientRect() // where (0, 0) lands: the window's corner, or a transformed parent's
      const spot = placeList(b, el.offsetWidth, el.scrollHeight, window.innerWidth, window.innerHeight)
      Object.assign(el.style, { top: `${spot.top - origin.top}px`, left: `${spot.left - origin.left}px`, maxHeight: `${Math.min(280, spot.maxHeight)}px` })
    }
    place()
    window.addEventListener("scroll", place, true)
    window.addEventListener("resize", place)
    return () => {
      window.removeEventListener("scroll", place, true)
      window.removeEventListener("resize", place)
    }
  }, [open, button, list])
}
