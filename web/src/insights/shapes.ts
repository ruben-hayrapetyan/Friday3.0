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

/** A suggested profile's changes, {rule, from, to}, as one sentence: which rules weigh more and which less. */
export function weighing(changes: { rule: string; from: number; to: number }[], said: (rule: string) => string): string {
  const list = (names: string[]) => (names.length < 2 ? names.join("") : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`)
  const quoted = (up: boolean) => changes.filter((c) => c.to !== c.from && c.to > c.from === up).map((c) => `“${said(c.rule)}”`)
  const more = quoted(true)
  const less = quoted(false)
  const parts = [more.length ? `more weight on ${list(more)}` : "", less.length ? `less on ${list(less)}` : ""].filter(Boolean)
  if (!parts.length) return ""
  const text = parts.join("; ")
  return `${text[0].toUpperCase()}${text.slice(1)}.`
}
