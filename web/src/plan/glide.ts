// Replanning in motion (27 Oct): when a new plan, or the quick placement before it, moves a block, the block slides
// from where it was to where it is now, as calendar apps slide an event you moved; one that's new fades in. An item's
// blocks are matched with where its blocks were, nearest first (the key names the start, so it can't match them; by
// their order, a block added early in the week sent every later one sliding a day on), placed by the clock of their
// day. Nothing slides on a change of week or of the calendar's width, nor a block you placed yourself (it's there
// already), nor with reduced motion.

import { type RefObject, useLayoutEffect, useRef } from "react"
import { PX } from "./Pieces"

const MS = 420
const EASE = "cubic-bezier(0.2, 0.8, 0.2, 1)"
const BY_HAND_MS = 3000

export interface Rect {
  x: number
  y: number
  w: number
  h: number
}

// Items you just dragged or retimed: their block is where you let go, so it doesn't slide there again.
const byHand = new Map<number, number>()

export function placedByHand(itemId: number): void {
  byHand.set(itemId, Date.now())
}

function wasByHand(itemId: number): boolean {
  const at = byHand.get(itemId)
  return at !== undefined && Date.now() - at < BY_HAND_MS
}

/** What a box is one of, across plans: an item's blocks are all its blocks ("T42"), anything else its own key. */
export function familyOf(key: string): string {
  const m = /^T(\d+)@/.exec(key)
  return m ? `T${m[1]}` : key
}

/** For each box now, the box it was (an index into `was`), nearest pairs first; null for one that's new. */
export function pairUp(was: Rect[], now: Rect[]): (number | null)[] {
  const pairs: [number, number, number][] = []
  for (const [j, n] of now.entries()) for (const [i, w] of was.entries()) pairs.push([Math.hypot(w.x - n.x, w.y - n.y), i, j])
  pairs.sort((a, b) => a[0] - b[0])
  const out: (number | null)[] = now.map(() => null)
  const used = new Set<number>()
  for (const [, i, j] of pairs) {
    if (used.has(i) || out[j] !== null) continue
    out[j] = i
    used.add(i)
  }
  return out
}

/** How far a box moved, as the offset that puts it back where it was; null when it didn't move. */
export function offset(was: Rect, now: Rect): Rect | null {
  const dx = was.x - now.x
  const dy = was.y - now.y
  if (Math.abs(dx) < 1 && Math.abs(dy) < 1 && Math.abs(was.w - now.w) < 1 && Math.abs(was.h - now.h) < 1) return null
  return { x: dx, y: dy, w: was.w, h: was.h }
}

const itemOf = (key: string) => {
  const m = /^T(\d+)@/.exec(key)
  return m ? Number(m[1]) : null
}

type Boxes = Map<string, { el: HTMLElement; rect: Rect }[]>

/** The calendar's boxes (`data-block-key`) inside `root`, by family, each placed by its day's clock: a taller day
 * header or an earlier first hour moves every box on the page without any of them changing time. */
function measure(root: HTMLElement): Boxes {
  const box = root.getBoundingClientRect()
  const out: Boxes = new Map()
  for (const el of root.querySelectorAll<HTMLElement>("[data-block-key]")) {
    const r = el.getBoundingClientRect()
    const day = el.closest<HTMLElement>("[data-top-min]")
    const y = day ? (Number(day.dataset.topMin) % 1440) * PX + r.top - day.getBoundingClientRect().top : r.top - box.top + root.scrollTop
    const family = familyOf(el.dataset.blockKey ?? "")
    out.set(family, [...(out.get(family) ?? []), { el, rect: { x: r.left - box.left + root.scrollLeft, y, w: r.width, h: r.height } }])
  }
  return out
}

/** Slides the calendar's boxes inside `panel` when `plan` changes. `place` names what's shown (the dates); a new
 * one starts afresh. */
export function useGlide(panel: RefObject<HTMLElement | null>, plan: unknown, place: string): void {
  const last = useRef<{ plan: unknown; place: string; width: number; boxes: Map<string, Rect[]> } | null>(null)
  useLayoutEffect(() => {
    const root = panel.current
    if (!root) return
    const width = root.getBoundingClientRect().width
    const boxes = measure(root)
    const before = last.current
    last.current = { plan, place, width, boxes: new Map([...boxes].map(([k, v]) => [k, v.map((b) => b.rect)])) }
    if (!before || before.plan === plan || before.place !== place || Math.abs(before.width - width) > 1) return
    if (typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return
    for (const [family, now] of boxes) {
      const item = itemOf(family.startsWith("T") ? `${family}@` : "")
      if (item !== null && wasByHand(item)) continue
      const was = before.boxes.get(family) ?? []
      const pairs = pairUp(was, now.map((b) => b.rect))
      for (const [j, { el, rect }] of now.entries()) {
        if (typeof el.animate !== "function") continue
        const from = pairs[j]
        if (from === null) {
          el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: MS * 0.6, easing: "ease-out" })
          continue
        }
        const off = offset(was[from], rect)
        if (!off) continue
        el.animate(
          [
            { transform: `translate(${off.x}px, ${off.y}px)`, width: `${off.w}px`, height: `${off.h}px` },
            { transform: "translate(0, 0)", width: `${rect.w}px`, height: `${rect.h}px` },
          ],
          { duration: MS, easing: EASE },
        )
      }
    }
  })
}
