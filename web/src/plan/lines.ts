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
