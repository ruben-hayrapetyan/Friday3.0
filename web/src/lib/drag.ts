// Drag geometry (DESIGN §18.4): where a moved, resized or selected span lands, snapped to 15 minutes. Minutes are
// on the zone-free clock of `time.ts`.

import { ROW_MIN } from "./time"

export type DragKind = "move" | "resize" | "resize-top" | "row" | "select"

export interface DragStart {
  kind: DragKind
  start: number // the block's start, or where a selection began
  end: number
  grab: number // for a move: minutes from the block's start to where it was grabbed
}

export const snap = (minute: number) => Math.round(minute / ROW_MIN) * ROW_MIN

/** The span a drag points at when the pointer is over `minute`. */
export function dragged(from: DragStart, minute: number): { start: number; end: number } {
  const length = from.end - from.start
  switch (from.kind) {
    case "move":
    case "row": {
      const start = snap(minute - from.grab)
      return { start, end: start + length }
    }
    case "resize":
      return { start: from.start, end: Math.max(from.start + ROW_MIN, snap(minute)) }
    case "resize-top": // its top edge: an earlier or later start, the same end
      return { start: Math.min(from.end - ROW_MIN, snap(minute)), end: from.end }
    case "select": {
      const anchor = from.start
      const at = snap(minute)
      return at >= anchor
        ? { start: anchor, end: Math.max(anchor + ROW_MIN, at) }
        : { start: at, end: anchor + ROW_MIN }
    }
  }
}

/** Items whose first block moved since the plan was last seen, with where it was. */
export function movedSince(
  before: Map<number, string>,
  after: Map<number, string>,
): Map<number, string> {
  const out = new Map<number, string>()
  for (const [id, start] of after) {
    const was = before.get(id)
    if (was !== undefined && was !== start) out.set(id, was)
  }
  return out
}
