// How a break says itself (core/vacations.py): its days, how much work, and what it pauses, in words.

import type { Schemas } from "@/api/client"
import { weekday } from "@/lib/format"
import { addDays, toMin } from "@/lib/time"

const MONTH = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

/** What a break pauses, every list there (the server leaves out what's empty). */
export type Pause = Required<Schemas["PauseIn"]>

/** A pause as the server sent it, its empty lists filled in. */
export function full(p?: Schemas["PauseIn"] | null): Pause {
  return { repeating: p?.repeating ?? "all", calendars: p?.calendars ?? [], series_kept: p?.series_kept ?? [], series_paused: p?.series_paused ?? [], tags: p?.tags ?? [] }
}
export type Vacation = Schemas["VacationOut"]
export type Choices = Schemas["BreakChoicesOut"]

/** "Mon, Dec 21" */
export function dayWords(date: string): string {
  return `${weekday(date)}, ${MONTH[Number(date.slice(5, 7)) - 1]} ${Number(date.slice(8, 10))}`
}

/** "Mon, Dec 21 – Sun, Dec 27", or the one day. */
export function rangeWords(start: string, end: string): string {
  return start === end ? dayWords(start) : `${dayWords(start)} – ${dayWords(end)}`
}

/** Days from `start` to `end`, both counted. */
export function daysIn(start: string, end: string): number {
  return Math.round((toMin(end) - toMin(start)) / 1440) + 1
}

export const things = (n: number) => `${n} thing${n === 1 ? "" : "s"}`

/** "Light, about 3 things a day", "Off: nothing to do" */
export function modeWords(mode: string, perDay: number): string {
  return mode === "off" ? "Off: nothing to do" : `Light, about ${things(perDay)} a day`
}

/** What a break pauses, said as a value (UI-PRINCIPLES: say the value, not a name for it). */
export function pauseWords(pause: Pause, choices?: Choices): string {
  const calendars = choices?.calendars.length ?? 0
  const kept = pause.series_kept.length
  const tags = pause.tags.length ? `; tasks tagged ${listed(pause.tags)} wait` : ""
  if (pause.repeating === "all") {
    const except = pause.calendars.length ? ` except ${pause.calendars.length === 1 ? pause.calendars[0] : `${pause.calendars.length} calendars`}` : ""
    const keeps = kept ? `, ${kept} kept` : ""
    return `Every repeating event${except}${keeps}${tags}`
  }
  const only = pause.calendars.length ? `${pause.calendars.length === 1 ? pause.calendars[0] : `${pause.calendars.length}${calendars ? ` of ${calendars}` : ""} calendars`}` : "no calendar"
  const more = pause.series_paused.length ? ` and ${pause.series_paused.length} more` : ""
  return `Repeating events on ${only}${more}${tags}`
}

/** "Work, Home and 2 more" */
export function listed(names: string[], most = 2): string {
  if (names.length <= most + 1) return names.length > 1 ? `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}` : (names[0] ?? "")
  return `${names.slice(0, most).join(", ")} and ${names.length - most} more`
}

/** Whether a repeating event (by its series and calendar) pauses: as the server says (core/vacations.py `pauses`). */
export function pauses(pause: Pause, seriesId: number, calendar: string): boolean {
  if (pause.series_kept.includes(seriesId)) return false
  if (pause.series_paused.includes(seriesId)) return true
  return pause.repeating === "all" ? !pause.calendars.includes(calendar) : pause.calendars.includes(calendar)
}

/** Whether a calendar's repeats pause. */
export const calendarPaused = (pause: Pause, calendar: string) => (pause.repeating === "all" ? !pause.calendars.includes(calendar) : pause.calendars.includes(calendar))

/** A calendar switched: paused or kept, as it was the other way. */
export function flipCalendar(pause: Pause, calendar: string): Pause {
  const listedNow = pause.calendars.includes(calendar)
  return { ...pause, calendars: listedNow ? pause.calendars.filter((c) => c !== calendar) : [...pause.calendars, calendar] }
}

/** A repeat switched against what its calendar says. */
export function flipSeries(pause: Pause, seriesId: number, calendar: string): Pause {
  const now = pauses(pause, seriesId, calendar)
  const byCalendar = calendarPaused(pause, calendar)
  const kept = pause.series_kept.filter((s) => s !== seriesId)
  const paused = pause.series_paused.filter((s) => s !== seriesId)
  // back to what its calendar says, or against it
  if (now !== byCalendar) return { ...pause, series_kept: kept, series_paused: paused }
  return now ? { ...pause, series_kept: [...kept, seriesId], series_paused: paused } : { ...pause, series_kept: kept, series_paused: [...paused, seriesId] }
}

/** Every calendar paused, or none ("Pause all", "Keep all"). */
export function allCalendars(pause: Pause, on: boolean): Pause {
  return { ...pause, repeating: on ? "all" : "only", calendars: [], series_kept: [], series_paused: [] }
}

/** The presets: everything that repeats, or only these calendars. */
export const EVERYTHING: Pause = { repeating: "all", calendars: [], series_kept: [], series_paused: [], tags: [] }

/** A break's days in the week shown: the column it starts at and how many it covers there. */
export function inView(start: string, end: string, dates: string[]): { from: number; to: number; clippedStart: boolean; clippedEnd: boolean } | null {
  const first = dates[0]
  const last = dates[dates.length - 1]
  if (!first || end < first || start > last) return null
  const from = Math.max(0, dates.indexOf(start < first ? first : start))
  const to = dates.indexOf(end > last ? last : end)
  return { from, to, clippedStart: start < first, clippedEnd: end > last }
}

/** The day after a date, for a new break's end. */
export const nextDay = (date: string) => addDays(date, 1)

/** What a calendar cell or list shows of a day (breaks/): on a break day only events that stay, no planned work and
 * nothing a break paused; any other day, everything. */
export function keptOnBreakDay(onBreak: boolean, thing: { event: boolean; left_out?: string | null }): boolean {
  if (!onBreak) return true
  return thing.event && thing.left_out !== "paused"
}

/** When planned work is, said as a row says it: on a break day the day's list, not a time ("today's list", "Fri's
 * list"); any other day by `when`. */
export function plannedWords(start: string, today: string, breaks: { start: string; end: string }[], when: (at: string) => string): string {
  const day = start.slice(0, 10)
  if (!breaks.some((b) => b.start <= day && day <= b.end)) return when(start)
  return day === today ? "today's list" : `${weekday(day)}'s list`
}
