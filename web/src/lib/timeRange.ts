// A time typed over a block's or an event's time on the calendar: "10–11:30", "2pm-3pm", "9:15am to 10am", or a
// lone start ("3pm") that keeps the length. Times without am or pm take the one nearest what was there, as a person
// typing "3" over a 2pm class means 3pm; an end without one comes after the start.

import { ampm, fromMin, type Span, toMin } from "./time"

/** The text a time starts out as: "9:30am–10:30am". */
export function rangeText(span: Span): string {
  return `${ampm(span.start)}–${ampm(span.end)}`
}

interface Typed {
  minute: number // after midnight; with no am or pm, on the 12-hour clock (0 to 719)
  half: "am" | "pm" | null // null when it could be either
}

const TIME = /^(\d{1,2})(?::?(\d{2}))?\s*(a|p)?\.?\s*(?:m\.?)?$/

function readTime(text: string): Typed | null {
  const t = text.trim().toLowerCase()
  if (t === "noon" || t === "midday") return { minute: 720, half: "pm" }
  if (t === "midnight") return { minute: 0, half: "am" }
  // "930" and "1030" read as 9:30 and 10:30.
  const squeezed = /^\d{3,4}$/.test(t) ? `${t.slice(0, -2)}:${t.slice(-2)}` : t
  const match = TIME.exec(squeezed)
  if (!match) return null
  const hour = Number(match[1])
  const minute = Number(match[2] ?? 0)
  if (minute > 59) return null
  if (match[3]) {
    if (hour < 1 || hour > 12) return null
    const pm = match[3] === "p"
    return { minute: ((hour % 12) + (pm ? 12 : 0)) * 60 + minute, half: pm ? "pm" : "am" }
  }
  if (hour > 23) return null
  // On the 24-hour clock ("14:30", "0:15"), it can only be the one time.
  if (hour === 0 || hour > 12) return { minute: hour * 60 + minute, half: hour < 12 ? "am" : "pm" }
  return { minute: (hour % 12) * 60 + minute, half: null }
}

/** The minute of the day a time is at, given its half or, without one, the half nearest `near`. */
function resolve(t: Typed, near: number): number {
  if (t.half === "am" || t.half === "pm" || t.minute >= 720) return t.minute
  const am = t.minute
  const pm = t.minute + 720
  return Math.abs(pm - near) < Math.abs(am - near) ? pm : am
}

const SPLIT = /\s*(?:–|—|-|\bto\b|\buntil\b|\btill\b|\bthru\b|\bthrough\b)\s*/i

/** The span typed, on the day `was` starts; null when it can't be read. */
export function readTimeRange(text: string, was: Span): Span | null {
  const parts = text.trim().split(SPLIT)
  if (parts.length > 2 || parts.some((p) => p === "")) return null
  const day = was.start.slice(0, 10)
  const midnight = toMin(day)
  const startWas = toMin(was.start) - midnight
  const length = toMin(was.end) - toMin(was.start)
  const first = readTime(parts[0])
  if (!first) return null
  if (parts.length === 1) {
    const start = midnight + resolve(first, startWas)
    return { start: fromMin(start), end: fromMin(start + length) }
  }
  const second = readTime(parts[1])
  if (!second) return null
  const after = (from: number, to: number, step: number) => {
    while (to <= from) to += step
    return to
  }
  const loose = (t: Typed) => t.half === null && t.minute < 720
  let from: number
  let to: number
  if (loose(first) && !loose(second)) {
    // "11–1pm", "11–1am": the start is whichever reading makes the shorter span to the end.
    const [am, pm] = [first.minute, first.minute + 720]
    from = after(am, second.minute, 1440) - am <= after(pm, second.minute, 1440) - pm ? am : pm
    to = after(from, second.minute, 1440)
  } else {
    from = resolve(first, startWas)
    // The end is the first reading of it after the start, past midnight if need be.
    to = after(from, second.minute, loose(second) ? 720 : 1440)
  }
  if (to - from >= 1440) return null
  return { start: fromMin(midnight + from), end: fromMin(midnight + to) }
}
