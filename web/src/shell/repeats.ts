// How an event repeats, said with its own day (27 Oct: "Every week" from a list didn't say which day, and a repeat was
// three rows down the drawer): the choices a calendar app offers, the days for "Certain days…", and how many times.
// Rules go to the server as "rrule:…", as `add` and `repeat` take them.

export const RRULE_DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"] as const
const NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
export const LETTERS = ["M", "T", "W", "T", "F", "S", "S"]
const WEEKDAYS = "MO,TU,WE,TH,FR"
export const CUSTOM = "custom"

/** The day of the week of a local "YYYY-MM-DD…", Monday 0. */
export function dayOf(start: string): number {
  return (new Date(`${start.slice(0, 10)}T12:00:00Z`).getUTCDay() + 6) % 7
}

function ordinal(n: number): string {
  const tail = n % 100 >= 11 && n % 100 <= 13 ? "th" : ["th", "st", "nd", "rd"][n % 10] ?? "th"
  return `${n}${tail}`
}

/** A rule without its end, and the end: how many times, if it says. */
export function splitCount(every: string): { base: string; count: number | null } {
  const m = /;COUNT=(\d+)/.exec(every)
  return { base: every.replace(/;COUNT=\d+/, ""), count: m ? Number(m[1]) : null }
}

export function withCount(base: string, count: number | null): string {
  return count && base.startsWith("rrule:") ? `${base};COUNT=${count}` : base
}

/** The days a weekly rule falls on, Monday 0; null for any other rule. */
export function daysIn(every: string): number[] | null {
  const m = /^rrule:FREQ=WEEKLY;BYDAY=([A-Z,]+)$/.exec(splitCount(every).base)
  return m ? m[1].split(",").map((d) => RRULE_DAYS.indexOf(d as (typeof RRULE_DAYS)[number])).filter((d) => d >= 0).sort() : null
}

export function onDays(days: number[]): string {
  return `rrule:FREQ=WEEKLY;BYDAY=${[...days].sort().map((d) => RRULE_DAYS[d]).join(",")}`
}

/** What a calendar app offers for an event on `start`'s day, "Doesn't repeat" first. */
export function repeatChoices(start: string): { value: string; label: string }[] {
  const d = dayOf(start)
  const date = Number(start.slice(8, 10))
  return [
    { value: "", label: "Doesn't repeat" },
    { value: "rrule:FREQ=DAILY", label: "Every day" },
    { value: `rrule:FREQ=WEEKLY;BYDAY=${RRULE_DAYS[d]}`, label: `Every week on ${NAMES[d]}` },
    { value: `rrule:FREQ=WEEKLY;INTERVAL=2;BYDAY=${RRULE_DAYS[d]}`, label: `Every other ${NAMES[d]}` },
    { value: `rrule:FREQ=WEEKLY;BYDAY=${WEEKDAYS}`, label: "Every weekday (Mon–Fri)" },
    { value: `rrule:FREQ=MONTHLY;BYMONTHDAY=${date}`, label: `Every month on the ${ordinal(date)}` },
  ]
}

/** A rule in words, for an event on `start`'s day. */
export function sayRepeat(every: string | null, start: string): string {
  if (!every) return "Doesn't repeat"
  const { base, count } = splitCount(every)
  const end = count ? `, ${count} times` : ""
  const known = repeatChoices(start).find((c) => c.value === base)
  if (known) return known.label + end
  const days = daysIn(base)
  if (days) return `Every ${days.map((d) => NAMES[d].slice(0, 3)).join(", ")}${end}`
  if (base === "rrule:FREQ=WEEKLY") return `Every week on ${NAMES[dayOf(start)]}${end}`
  if (base === "rrule:FREQ=WEEKLY;INTERVAL=2") return `Every other ${NAMES[dayOf(start)]}${end}`
  if (base === "rrule:FREQ=MONTHLY") return `Every month on the ${ordinal(Number(start.slice(8, 10)))}${end}`
  return `Repeats${end}`
}

/** When an event moves to another day, a weekly rule on its old day moves with it ("every Friday" to "every
 * Saturday"); any other rule stays as it is. */
export function movedRule(every: string | null, from: string, to: string): string | null {
  if (!every) return every
  const { base, count } = splitCount(every)
  const was = RRULE_DAYS[dayOf(from)]
  const m = new RegExp(`^(rrule:FREQ=WEEKLY(?:;INTERVAL=\\d+)?);BYDAY=${was}$`).exec(base)
  return m ? withCount(`${m[1]};BYDAY=${RRULE_DAYS[dayOf(to)]}`, count) : every
}
