import { parseLength as readLength } from "./lengths"
import { dayStartClock } from "./dayStart"
import { ampm, fromMin, toMin } from "./time"

export { ampm }

const WEEKDAY = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
const MONTH = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

/** A local time on a 12-hour clock: "2:30pm". */
export function clock(local: string): string {
  return ampm(local.slice(11, 16))
}

export function weekday(date: string): string {
  return WEEKDAY[new Date(toMin(date) * 60000).getUTCDay()]
}

export function dayLabel(date: string): string {
  return `${weekday(date)} ${Number(date.slice(8, 10))} ${MONTH[Number(date.slice(5, 7)) - 1]}`
}

/** "2pm" today, "Tue 2pm" within the week, "Fri 6 Nov 5pm" further off; a bare date has no time. */
export function when(local: string, today: string): string {
  const date = local.slice(0, 10)
  const time = local.length > 10 ? clock(local) : ""
  // A repeat's window ends as the next planning day starts (your day start): that is the end of the day before.
  if (local.slice(11, 16) === dayStartClock()) return `${when(new Date((toMin(date) - 1440) * 60000).toISOString().slice(0, 10), today)}, end of day`
  if (local.startsWith(today) && time) return time
  const days = Math.abs(toMin(date) - toMin(today)) / 1440
  const day = days < 7 ? weekday(date) : `${weekday(date)} ${Number(date.slice(8, 10))} ${MONTH[Number(date.slice(5, 7)) - 1]}`
  return time ? `${day} ${time}` : day
}

export function length(minutes: number, estimated = false): string {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  const text = h && m ? `${h}h${m}` : h ? `${h}h` : `${m}m`
  return estimated ? `~${text}` : text
}

/** "2h 30m", "45m": lengths the way v22 writes them. */
export function dur(minutes: number): string {
  const m = Math.round(minutes)
  const h = Math.floor(m / 60)
  const r = m % 60
  return h ? `${h}h${r ? ` ${r}m` : ""}` : `${r}m`
}

/** A day's timed sittings, in order: "2:45–2:48pm, 3:11–3:36pm" (each from its start for as long as it ran; one
 * that picks up where the last ended, as a replan's cut leaves it, is the same sitting). */
export function sittings(rows: { source?: unknown; start?: unknown; minutes?: unknown }[], date: string): string {
  const spans = rows
    .filter((r) => r.source === "timer" && typeof r.start === "string" && r.start.startsWith(date))
    .map((r) => [toMin(r.start as string), toMin(r.start as string) + (Number(r.minutes) || 0)])
    .sort(([a], [b]) => a - b)
  const joined: number[][] = []
  for (const [from, to] of spans) {
    const last = joined[joined.length - 1]
    if (last && from <= last[1]) last[1] = Math.max(last[1], to)
    else joined.push([from, to])
  }
  return joined
    .map(([from, to]) => {
      const a = clock(fromMin(from))
      const b = clock(fromMin(to))
      return a.slice(-2) === b.slice(-2) ? `${a.slice(0, -2)}–${b}` : `${a}–${b}`
    })
    .join(", ")
}

/** How late the plan finishes something, roughly: "30m", "3h", "2 days". */
export function lateBy(hours: number): string {
  if (hours >= 24) return `${Math.round(hours / 24)} day${Math.round(hours / 24) === 1 ? "" : "s"}`
  return dur(Math.max(15, Math.round((hours * 60) / 15) * 15))
}

/** A typed length in minutes: "5", "5m", "45 min", "1h30", "1h 30m", "1.5h", "1:30"; null when it isn't one. */
/** A length typed in plain language, in whole minutes (personal's reader, lib/lengths.ts; COMBINED.md 42). */
export function parseLength(text: string): number | null {
  const minutes = readLength(text)
  return minutes === null ? null : Math.round(minutes)
}

/** "12:34" or "1:02:03", for a ticking timer. */
export function hms(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const two = (n: number) => String(n).padStart(2, "0")
  return h ? `${h}:${two(m)}:${two(s % 60)}` : `${m}:${two(s % 60)}`
}

/** "0:42", for time left or elapsed. */
export function span(minutes: number): string {
  const m = Math.max(0, Math.round(minutes))
  return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}`
}

const PALETTE = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6", "#f97316", "#6366f1"]

/** An area's colour: its own, or a steady pick from the palette by name. */
export function areaColor(area: string | null | undefined, colors: Record<string, string | null>): string {
  if (!area) return "#94a3b8"
  const own = colors[area]
  if (own) return own
  let hash = 0
  for (const ch of area) hash = (hash * 31 + ch.charCodeAt(0)) | 0
  return PALETTE[Math.abs(hash) % PALETTE.length]
}

/** Hours in a rule's length text: `2h`, `1.5h`, `1h30m` or `90m`. */
export function hours(text: string): number {
  const match = /^(?:(\d+(?:\.\d+)?)h)?(?:(\d+)m)?$/.exec(text.trim())
  return match ? Number(match[1] ?? 0) + Number(match[2] ?? 0) / 60 : 0
}

/** A due date as personal's to-do list showed it (COMBINED.md 21): the date while it's a day or more off, a
 * countdown within the day ("in 3h 12m"), and how long ago once it has passed ("2h 5m over"), in the now red. */
export function dueLabel(due: string, nowMinute: number, today: string): { text: string; tone: "plain" | "soon" | "over" } {
  const left = toMin(due) - nowMinute
  if (left < 0) return { text: `${spanText(-left)} over`, tone: "over" }
  if (left < 1440) return { text: `in ${spanText(left)}`, tone: "soon" }
  return { text: when(due, today), tone: "plain" }
}

function spanText(minutes: number): string {
  if (minutes < 60) return `${minutes}m`
  if (minutes < 1440) return minutes % 60 ? `${Math.floor(minutes / 60)}h ${minutes % 60}m` : `${minutes / 60}h`
  const days = Math.floor(minutes / 1440)
  return `${days}d${Math.floor((minutes % 1440) / 60) ? ` ${Math.floor((minutes % 1440) / 60)}h` : ""}`
}
