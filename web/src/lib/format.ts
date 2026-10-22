import { toMin } from "./time"

const WEEKDAY = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
const MONTH = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

export function clock(local: string): string {
  return local.slice(11, 16)
}

export function weekday(date: string): string {
  return WEEKDAY[new Date(toMin(date) * 60000).getUTCDay()]
}

export function dayLabel(date: string): string {
  return `${weekday(date)} ${Number(date.slice(8, 10))} ${MONTH[Number(date.slice(5, 7)) - 1]}`
}

/** "14:00" today, "Tue 14:00" within the week, "Fri 6 Nov 17:00" further off; a bare date has no time. */
export function when(local: string, today: string): string {
  const date = local.slice(0, 10)
  const time = local.length > 10 ? clock(local) : ""
  // A repeat's window ends as the next planning day starts (04:00): that is the end of the day before.
  // ponytail: assumes the default day start; read time.day_start if anyone changes it.
  if (time === "04:00") return `${when(new Date((toMin(date) - 1440) * 60000).toISOString().slice(0, 10), today)}, end of day`
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

/** A typed length in minutes: "5", "5m", "45 min", "1h30", "1h 30m", "1.5h", "1:30"; null when it isn't one. */
export function parseLength(text: string): number | null {
  const t = text.trim().toLowerCase().replace(/\s+/g, "")
  const clock = /^(\d+):(\d{1,2})$/.exec(t)
  if (clock) return Number(clock[1]) * 60 + Number(clock[2])
  const parts = /^(?:(\d+(?:\.\d+)?)h(?:ours?|rs?)?)?(?:(\d+)m?(?:in(?:ute)?s?)?)?$/.exec(t)
  if (!parts || (!parts[1] && !parts[2])) return null
  const minutes = Math.round(Number(parts[1] ?? 0) * 60 + Number(parts[2] ?? 0))
  return minutes > 0 ? minutes : null
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
