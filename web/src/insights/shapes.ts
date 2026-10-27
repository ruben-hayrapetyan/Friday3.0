// What the Insights page works out before drawing: which blocks two versions of a day place differently, the span
// the day's mini columns cover, and a suggested set of weights in words.

import { ampm, toMin } from "@/lib/time"

export interface Piece {
  item_id: number
  title: string
  start: string
  end: string
}

const same = (a: Piece, b: Piece) => a.item_id === b.item_id && a.start === b.start && a.end === b.end

/** The pieces of `mine` the other version doesn't have at the same time: moved, resized, or only in this one. */
export function moved(mine: Piece[], theirs: Piece[]): Set<Piece> {
  return new Set(mine.filter((p) => !theirs.some((t) => same(p, t))))
}

/** Where the same thing sits in the other version, in words, for a moved piece's hover text. */
export function elsewhere(p: Piece, theirs: Piece[], clock: (local: string) => string): string {
  const there = theirs.filter((t) => t.item_id === p.item_id)
  return there.length ? `${there.map((t) => `${clock(t.start)}–${clock(t.end)}`).join(", ")} in the other version` : "not in the other version"
}

/** Minutes on the zone-free clock from half an hour before the first thing to half an hour after the last, to the
 * half hour; at least two hours. */
export function spanOf(things: { start: string; end: string }[]): { lo: number; hi: number } {
  const lo = Math.floor((Math.min(...things.map((t) => toMin(t.start))) - 30) / 30) * 30
  const hi = Math.ceil((Math.max(...things.map((t) => toMin(t.end))) + 30) / 30) * 30
  return { lo, hi: Math.max(hi, lo + 120) }
}

/** The whole hours inside a span, with their 12-hour labels: "9am", "12pm". */
export function ticks(lo: number, hi: number): { at: number; label: string }[] {
  const out = []
  for (let m = Math.ceil(lo / 60) * 60; m <= hi; m += 60) {
    const hour = (((m / 60) % 24) + 24) % 24
    out.push({ at: m, label: ampm(`${String(hour).padStart(2, "0")}:00`) })
  }
  return out
}

export interface Change {
  rule: string
  from: number
  to: number
}

export interface Weighed {
  rule: string
  factor: number // the new weight over the old
  word: string // how much, in words
  big: boolean // twice as much or more, half or less
}

/** How much a change weighs a rule, in words: ×1.16 is "a little more", ×0.4 "much less", ×0.02 "almost none". */
export function strength(factor: number): { word: string; big: boolean } {
  if (factor >= 2) return { word: "much more", big: true }
  if (factor >= 1.3) return { word: "more", big: false }
  if (factor > 1) return { word: "a little more", big: false }
  if (factor <= 0.1) return { word: "almost none", big: true }
  if (factor <= 0.5) return { word: "much less", big: true }
  if (factor <= 0.77) return { word: "less", big: false }
  return { word: "a little less", big: false }
}

/** A suggested profile's changes, {rule, from, to}, as what would matter more and what less, the biggest change
 * first on each side (27 Oct: one sentence quoting nineteen rules said neither which mattered nor how much). */
export function sides(changes: Change[]): { more: Weighed[]; less: Weighed[] } {
  const weighed = changes
    .filter((c) => c.from > 0 && c.to !== c.from)
    .map((c) => ({ rule: c.rule, factor: c.to / c.from, ...strength(c.to / c.from) }))
    .sort((a, b) => Math.abs(Math.log(b.factor)) - Math.abs(Math.log(a.factor)))
  return { more: weighed.filter((w) => w.factor > 1), less: weighed.filter((w) => w.factor < 1) }
}

/** "×1.2", "×0.02": a factor to two significant figures. */
export function times(factor: number): string {
  return `×${Number(factor.toPrecision(2))}`
}
