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
export const TALLEST = 280 // a list is never taller: a longer one scrolls inside it

export type Placed = { top: number; left: number; maxHeight: number }

/** Where a list `width` × `height` goes beside a button at `button`, on a window `w` × `h`. */
export function placeList(button: { top: number; bottom: number; left: number; right: number }, width: number, height: number, w: number, h: number): Placed {
  const below = h - MARGIN - (button.bottom + GAP)
  const above = button.top - GAP - MARGIN
  const down = height <= below || below >= above
  const room = Math.min(TALLEST, Math.max(80, down ? below : above))
  // above the button, it sits as tall as it's drawn: its full height had put a long list's foot far above the button
  const tall = Math.min(height, room)
  const top = down ? button.bottom + GAP : button.top - GAP - tall
  const left = button.right - width
  return { top, left: left + slideInto(left, left + width, w, MARGIN), maxHeight: room }
}

/** While `open`, the list is fixed over the page beside its button, scrolling inside its height when it's longer
 * (20 Nov, a user's notes: the Breaks panel, three breaks long, ran out of its height and its buttons lay over the
 * calendar; New exam's focus list did so too, 19 Nov). A transformed parent (the Now bar) makes "fixed"
 * count from itself, not the window: where it lands is measured and the difference taken off. "At least as wide as
 * its button" is said in pixels: the stylesheet's `min-width: 100%`, fixed, meant the whole window (16 Nov, IMG 4240:
 * an event's Category list ran across the bottom of the screen, its left edge cut off). */
export function useMenuPlace(open: boolean, button: RefObject<HTMLElement | null>, list: RefObject<HTMLElement | null>) {
  useLayoutEffect(() => {
    const el = list.current
    const at = button.current
    if (!open || !el || !at) return
    // Its own scroll isn't the page's: placing it again clears its height to measure it, and the browser put a
    // scrolled list back at its top, so a long list never scrolled (20 Nov, the user: "the scroll for the dropdown is
    // bad", New exam's focus list). When the page scrolls, it's placed again where it was scrolled to.
    const place = (event?: Event) => {
      if (event?.target instanceof Node && el.contains(event.target)) return
      const scrolled = el.scrollTop
      const b = at.getBoundingClientRect()
      Object.assign(el.style, { position: "fixed", right: "auto", bottom: "auto", top: "0px", left: "0px", maxHeight: "", minWidth: `${b.width}px` })
      const origin = el.getBoundingClientRect() // where (0, 0) lands: the window's corner, or a transformed parent's
      const spot = placeList(b, el.offsetWidth, el.scrollHeight, window.innerWidth, window.innerHeight)
      Object.assign(el.style, { top: `${spot.top - origin.top}px`, left: `${spot.left - origin.left}px`, maxHeight: `${spot.maxHeight}px`, overflowY: "auto", overscrollBehavior: "contain" })
      el.scrollTop = scrolled
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
