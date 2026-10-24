// A project's timeline, worked out apart from drawing it: the days it spans, the hours of each day it shows
// (nights fold away so a two-hour session reads as more than a sliver), and where a time falls across them.

import { addDays, type Span, toMin } from "@/lib/time"

export interface Frame {
  first: string // the first day shown
  days: number
  from: number // minutes after midnight each day's column opens at
  to: number // and closes at
}

const OPEN = 7 * 60 // a day shows 7am to 11pm, wider when something is planned outside it
const CLOSE = 23 * 60

/** A due date without a time is due by the end of that day. */
export function dueAt(due: string): string {
  return due.length > 10 ? due : `${due}T23:59`
}

/** Today (or the first session, if earlier) through the due date or the last session, whichever is later; at
 * least three days. */
export function frame(today: string, due: string | null, blocks: Span[]): Frame {
  const starts = blocks.map((b) => b.start).sort()
  // A session ending at midnight ends the day before.
  const ends = blocks.map((b) => (b.end.slice(11, 16) === "00:00" ? addDays(b.end.slice(0, 10), -1) : b.end.slice(0, 10)))
  const first = [today, ...starts.map((s) => s.slice(0, 10))].sort()[0]
  const last = [first, ...(due ? [dueAt(due).slice(0, 10)] : []), ...ends].sort().at(-1) as string
  const days = Math.max(3, Math.round((toMin(last) - toMin(first)) / 1440) + 1)
  let from = OPEN
  let to = CLOSE
  for (const b of blocks) {
    const s = toMin(b.start) - toMin(b.start.slice(0, 10))
    const e = b.end.slice(0, 10) > b.start.slice(0, 10) ? 1440 : toMin(b.end) - toMin(b.end.slice(0, 10))
    from = Math.min(from, Math.floor(s / 60) * 60)
    to = Math.max(to, Math.ceil(e / 60) * 60)
  }
  return { first, days, from, to }
}

/** Where a time falls across the frame, from 0 (its first day opening) to 1 (its last day closing). A time in the
 * folded night sits at the edge of its day. */
export function place(f: Frame, local: string): number {
  const minute = toMin(local) - toMin(f.first)
  const day = Math.floor(minute / 1440)
  if (day < 0) return 0
  if (day >= f.days) return 1
  const within = Math.min(f.to, Math.max(f.from, minute - day * 1440))
  return (day + (within - f.from) / (f.to - f.from)) / f.days
}

/** How long before the due date, said plainly: "under an hour", "5 hours", "1 day", "3 days". */
export function ahead(minutes: number): string {
  if (minutes < 60) return "under an hour"
  const hours = Math.round(minutes / 60)
  const [n, unit] = hours < 24 ? [hours, "hour"] : [Math.round(minutes / 1440), "day"]
  return `${n} ${unit}${n === 1 ? "" : "s"}`
}
