// How many lines a block or event on the calendar has room for (15 Nov: a client's notes: titles and locations were
// cut to one line however tall the box, "Seminar room 4…" on a two-hour event). A box with room wraps its title to as
// many lines as fit, then its time and location on the line(s) under it, each clamped to what the box's height holds;
// a short one keeps its one line.

import type { CSSProperties } from "react"

export const PAD = 8 // a tall box's padding, top and bottom (Pieces.tsx box)
export const TITLE_LINE = 12 * 1.3 // px: the title's size and line height
export const DETAIL_LINE = 11 * 1.3 // px: the time and location line's

/** The most lines the title may take in a box `px` tall with `rows` other one-line rows under it (moved from, in an
 * event): what leaves a line for its time. At least one. */
export function titleLines(px: number, rows = 0): number {
  return Math.max(1, Math.floor((px - PAD - (rows + 1) * DETAIL_LINE) / TITLE_LINE + 0.01))
}

/** The most lines the time and location may take under a title of `titleUsed` lines. At least one. */
export function detailLines(px: number, titleUsed: number, rows = 0): number {
  return Math.max(1, Math.floor((px - PAD - rows * DETAIL_LINE - titleUsed * TITLE_LINE) / DETAIL_LINE + 0.01))
}

/** CSS for text clamped to `lines` lines, long words broken rather than cut. */
export function clamped(lines: number): CSSProperties {
  return { display: "-webkit-box", WebkitBoxOrient: "vertical", WebkitLineClamp: lines, overflow: "hidden", overflowWrap: "anywhere", whiteSpace: "normal" }
}

/** Something drawn over a box: its top (minutes from the column's top) and its share of the width, from 0 to 1. */
export interface Over {
  top: number
  from: number
  to: number
}

/** Minutes of a box clear before the first thing drawn over it (a meal you ate, a running timer), so its title, time
 * and location fit there rather than run under it (17 Nov, a client: a lab's long location wrapped under "Snack" and a
 * timer). The whole box when nothing covers it; never less than its first 15 minutes. */
export function roomAbove(box: { top: number; height: number; column: number; columns: number }, over: Over[]): number {
  const [from, to] = [box.column / box.columns, (box.column + 1) / box.columns]
  const tops = over.filter((o) => o.from < to && o.to > from && o.top > box.top && o.top < box.top + box.height).map((o) => o.top)
  return tops.length ? Math.max(15, Math.min(...tops) - box.top) : box.height
}
