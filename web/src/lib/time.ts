// The API speaks local wall time ("2026-10-20T14:00"). The client never converts zones: it counts minutes on a
// zone-free clock, which is all drawing and ordering need.

export const ROW_MIN = 15

export function toMin(local: string): number {
  const [d, t = "00:00"] = local.split("T")
  const [y, m, day] = d.split("-").map(Number)
  const [h, mi] = t.split(":").map(Number)
  return Date.UTC(y, m - 1, day, h, mi) / 60000
}

export function fromMin(minutes: number): string {
  return new Date(minutes * 60000).toISOString().slice(0, 16)
}

export function addDays(date: string, days: number): string {
  return fromMin(toMin(date) + days * 1440).slice(0, 10)
}

export function dayRange(first: string, days: number): string[] {
  return Array.from({ length: days }, (_, n) => addDays(first, n))
}

export interface Axis {
  startMin: number // minutes after local midnight; the end may pass 1440
  endMin: number
}

/** A day column's span on the minute clock. Blocks after midnight belong to the evening before. */
export function columnSpan(date: string, axis: Axis): [number, number] {
  const midnight = toMin(date)
  return [midnight + axis.startMin, midnight + axis.endMin]
}

export interface Span {
  start: string
  end: string
}

const DAY_START = 4 * 60 // before 4am is the night before, as the server counts days

/** The axis stretched, to the hour, to take in what's on these days: a 6am class opens the day at 6am rather than
 * being cut at the wake time. Something after midnight belongs to the evening before; a day stays a day long. */
export function fitAxis(axis: Axis, things: Span[], dates: string[]): Axis {
  let { startMin, endMin } = axis
  const shown = new Set(dates)
  for (const t of things) {
    const date = t.start.slice(0, 10)
    const midnight = toMin(date)
    const night = toMin(t.start) - midnight < DAY_START
    const column = night ? addDays(date, -1) : date
    if (!shown.has(column)) continue
    const from = toMin(t.start) - toMin(column)
    const to = toMin(t.end) - toMin(column)
    if (to <= from) continue
    startMin = Math.min(startMin, Math.floor(from / 60) * 60)
    endMin = Math.max(endMin, Math.min(Math.ceil(to / 60) * 60, 1440 + DAY_START))
  }
  startMin = Math.max(startMin, DAY_START)
  return { startMin, endMin: Math.min(endMin, startMin + 1440) }
}

export interface Placed<T> {
  item: T
  top: number // minutes from the column's top
  height: number
  column: number // overlapping things share the width side by side
  columns: number
}

/** Things in one day column, clipped to it, with overlap columns. */
export function layout<T extends Span>(things: T[], date: string, axis: Axis): Placed<T>[] {
  const [lo, hi] = columnSpan(date, axis)
  const inside = things
    .map((item) => ({ item, s: Math.max(toMin(item.start), lo), e: Math.min(toMin(item.end), hi) }))
    .filter((p) => p.e > p.s)
    .sort((a, b) => a.s - b.s || b.e - a.e)
  const out: Placed<T>[] = []
  let cluster: { p: (typeof inside)[number]; column: number }[] = []
  let clusterEnd = -Infinity
  const flush = () => {
    const columns = Math.max(0, ...cluster.map((c) => c.column + 1))
    for (const c of cluster) {
      out.push({ item: c.p.item, top: c.p.s - lo, height: c.p.e - c.p.s, column: c.column, columns })
    }
    cluster = []
  }
  for (const p of inside) {
    if (p.s >= clusterEnd) flush()
    const busy = new Set(cluster.filter((c) => c.p.e > p.s).map((c) => c.column))
    let column = 0
    while (busy.has(column)) column++
    cluster.push({ p, column })
    clusterEnd = Math.max(clusterEnd, p.e)
  }
  flush()
  return out
}

/** A time on a 12-hour clock, from "HH:MM" or a local "YYYY-MM-DDTHH:MM": "2:30pm", "2pm", "12am". */
export function ampm(time: string): string {
  const [hour, minute] = time.slice(-5).split(":").map(Number)
  return `${((hour + 11) % 12) + 1}${minute ? `:${String(minute).padStart(2, "0")}` : ""}${hour % 24 < 12 ? "am" : "pm"}`
}

/** Hour labels down the axis, as minutes from the top with their clock text. */
export function hourMarks(axis: Axis): { top: number; label: string }[] {
  const out = []
  for (let m = Math.ceil(axis.startMin / 60) * 60; m < axis.endMin; m += 60) {
    out.push({ top: m - axis.startMin, label: ampm(`${String((m / 60) % 24).padStart(2, "0")}:00`) })
  }
  return out
}
