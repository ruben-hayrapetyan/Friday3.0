// Whole-day events in the week's header (3 Nov: "reserve that space for full day events only and make the full day
// events look better then just plain white text"): one bar per event across the days it covers, as Google Calendar
// draws them, packed into as few rows as fit.

import { addDays } from "@/lib/time"

export type WholeDay = { start: string; end: string } // local midnights; the end is the day after the last
export type Bar<T> = { event: T; from: number; to: number; row: number; clippedStart: boolean; clippedEnd: boolean }

/** Whether an event fills whole days: midnight to a later midnight. */
export function isWholeDay(e: { start?: string | null; end?: string | null }): boolean {
  return !!e.start && !!e.end && e.start.endsWith("T00:00") && e.end.endsWith("T00:00") && e.end > e.start
}

/** Each event shown on `dates` (consecutive days) as a bar over columns `from`..`to` (inclusive), in the first row
 * where it overlaps no other; longer and earlier events first, so they sit on top. */
export function bars<T extends WholeDay>(events: T[], dates: string[]): Bar<T>[] {
  if (!dates.length) return []
  const first = dates[0]
  const after = addDays(dates[dates.length - 1], 1)
  const shown = events
    .filter((e) => e.start.slice(0, 10) < after && e.end.slice(0, 10) > first)
    .sort((a, b) => a.start.localeCompare(b.start) || b.end.localeCompare(a.end))
  const rows: number[] = [] // the last column taken in each row
  const out: Bar<T>[] = []
  for (const event of shown) {
    const startDay = event.start.slice(0, 10)
    const lastDay = addDays(event.end.slice(0, 10), -1)
    const from = Math.max(0, dates.indexOf(startDay))
    const to = lastDay >= dates[dates.length - 1] ? dates.length - 1 : dates.indexOf(lastDay)
    let row = rows.findIndex((taken) => taken < from)
    if (row === -1) row = rows.push(-1) - 1
    rows[row] = to
    out.push({ event, from, to, row, clippedStart: startDay < first, clippedEnd: lastDay > dates[dates.length - 1] })
  }
  return out
}

export const MAX_ROWS = 3

/** At most `maxRows` rows of bars; the rest folded into a count per day ("+2"), which opens them all. */
export function folded<T>(placed: Bar<T>[], days: number, maxRows = MAX_ROWS): { shown: Bar<T>[]; more: number[] } {
  const rows = placed.reduce((n, b) => Math.max(n, b.row + 1), 0)
  if (rows <= maxRows) return { shown: placed, more: Array(days).fill(0) }
  const keep = maxRows - 1 // the last row holds the counts
  const more = Array(days).fill(0)
  for (const b of placed) if (b.row >= keep) for (let c = b.from; c <= b.to; c++) more[c]++
  return { shown: placed.filter((b) => b.row < keep), more }
}

/** Whether an event is on a day: a whole-day one on every day it covers, any other on the day it starts. */
export function isOnDay(e: { start?: string | null; end?: string | null }, date: string): boolean {
  if (isWholeDay(e)) return (e.start as string).slice(0, 10) <= date && date < (e.end as string).slice(0, 10)
  return !!e.start?.startsWith(date)
}
