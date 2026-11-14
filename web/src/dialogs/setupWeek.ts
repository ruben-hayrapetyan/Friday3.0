// The week drawn beside setup's questions (29 Oct: setup "like Opal... animations, information"): your answers as a
// week, redrawn as you change them, so each question shows what it does. An illustration, not the planner: example
// classes, and work laid into the gaps the way Friday lays it, in sittings no longer than your focus, kept off your
// sleep and your free time. Each bit keeps its id from one answer to the next, so the week moves rather than flickers.

import type { Schemas } from "@/api/client"

type Answers = Schemas["SetupInput"]

export type Kind = "sleep" | "class" | "work" | "heavy" | "free" | "essay" | "due" | "brief" | "event"

export interface Bit {
  id: string
  day: number // 0 Monday … 6 Sunday
  start: number // minutes from the day's midnight; past 24:00 is that night
  end: number
  kind: Kind
}

/** The hours drawn: 6 AM to 2 AM. */
export const VIEW = { from: 6 * 60, to: 26 * 60 }

/** Example classes, the same every time: a Monday-Wednesday-Friday pair and a Tuesday-Thursday pair. */
const CLASSES: [number[], string, string][] = [
  [[0, 2, 4], "10:10", "11:00"],
  [[0, 2, 4], "13:25", "14:15"],
  [[1, 3], "10:10", "11:25"],
  [[1, 3], "14:45", "16:00"],
]

const BREAK = 15 // between sittings
const DUE = { day: 4, at: 17 * 60 } // the example deadline: Friday, 5 PM

export function minutes(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number)
  return h * 60 + m
}

/** A time `by` minutes later, as "HH:MM", round midnight. */
export function shift(hhmm: string, by: number): string {
  const total = (((minutes(hhmm) + by) % 1440) + 1440) % 1440
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`
}

/** A bedtime after midnight belongs to the same night. */
function night(hhmm: string): number {
  const t = minutes(hhmm)
  return t < 12 * 60 ? t + 24 * 60 : t
}

const weekend = (day: number) => day >= 5

export function wakeOf(a: Answers, day: number): number {
  return minutes(weekend(day) ? a.weekend_wake : a.wake)
}

export function bedOf(a: Answers, day: number): number {
  return night(weekend(day) ? a.weekend_bedtime : a.bedtime)
}

/** Hours of sleep a night, weekday and weekend. */
export function sleepHours(a: Answers): { weekday: number; weekend: number } {
  const of = (day: number) => (wakeOf(a, day) + 24 * 60 - bedOf(a, day)) / 60
  return { weekday: of(0), weekend: of(5) }
}

/** "All of it": the largest amount each free-time question offers. */
export const ALL_EVENING = 5
export const ALL_WEEKEND = 13

function freeOf(a: Answers, day: number): [number, number] | null {
  const bed = bedOf(a, day)
  if (weekend(day)) {
    if (a.weekend_free <= 0) return null
    if (a.weekend_free >= ALL_WEEKEND) return [wakeOf(a, day), bed]
    return [Math.max(wakeOf(a, day), bed - a.weekend_free * 60), bed]
  }
  if (a.evening_free <= 0) return null
  const from = minutes(a.evening_from)
  return [from, a.evening_free >= ALL_EVENING ? bed : Math.min(bed, from + a.evening_free * 60)]
}

function classesOn(day: number): [number, number][] {
  return CLASSES.filter(([days]) => days.includes(day)).map(([, s, e]) => [minutes(s), minutes(e)])
}

/** Sittings of at most `focus` minutes from `from` to `to`, around `busy`, until `want` minutes are placed; none
 * shorter than half an hour (you asked for no slivers of work), so a last bit too small to sit down for is left. */
export function sittings(from: number, to: number, busy: [number, number][], want: number, focus: number): [number, number][] {
  const out: [number, number][] = []
  let t = from
  let left = want
  const blocked = [...busy].sort((x, y) => x[0] - y[0])
  while (left >= 30 && t < to) {
    const hit = blocked.find(([s, e]) => s < t + 15 && e > t)
    if (hit) {
      t = hit[1] + BREAK
      continue
    }
    const next = blocked.find(([s]) => s >= t)
    const room = Math.min(to, next ? next[0] - BREAK : to) - t
    if (room < 30) {
      t = next ? next[1] + BREAK : to
      continue
    }
    const length = Math.min(focus, left, room)
    out.push([t, t + length])
    left -= length
    t += length + BREAK
  }
  return out
}

export interface Week {
  bits: Bit[]
  workHours: number // in this week, as drawn
}

/** The week for `answers`, as the question `stage` shows it (the heavy day on "load", the deadline from "early" on, the
 * new event of "how"'s second beat). */
export function weekOf(a: Answers, stage: string, beat = 0): Week {
  const bits: Bit[] = []
  const focus = Math.max(15, Math.round(a.focus_hours * 60))
  const shown = (from: string) => ORDER.indexOf(stage) >= ORDER.indexOf(from)
  let work = 0
  for (let day = 0; day < 7; day++) {
    const wake = wakeOf(a, day)
    const bed = bedOf(a, day)
    if (wake > VIEW.from) bits.push({ id: `sleep-am-${day}`, day, start: VIEW.from, end: wake, kind: "sleep" })
    if (bed < VIEW.to) bits.push({ id: `sleep-pm-${day}`, day, start: bed, end: VIEW.to, kind: "sleep" })
    const classes = classesOn(day)
    classes.forEach(([s, e], i) => bits.push({ id: `class-${day}-${i}`, day, start: s, end: e, kind: "class" }))
    const free = freeOf(a, day)
    if (free) bits.push({ id: `free-${day}`, day, start: free[0], end: free[1], kind: "free" })
    const event: [number, number][] = stage === "how" && beat === 1 && day === 2 ? [[minutes("15:00"), minutes("16:00")]] : []
    event.forEach(([s, e]) => bits.push({ id: `event-${day}`, day, start: s, end: e, kind: "event" }))
    const start = wake + 60 // breakfast, getting going
    const end = free ? Math.min(free[0], bed - 60) : bed - 60 // free time, or an hour before bed, ends the day's work
    const want = weekend(day) ? Math.round((a.normal_hours * 60) / 2) : Math.round(a.normal_hours * 60)
    const placed = sittings(start, end, [...classes, ...event], want, focus)
    placed.forEach(([s, e], i) => bits.push({ id: `work-${day}-${i}`, day, start: s, end: e, kind: "work" }))
    work += placed.reduce((sum, [s, e]) => sum + e - s, 0)
    if (stage === "load" && day === 3 && a.most_hours > a.normal_hours) {
      // A heavy day: more, later, into the evening if it must
      const after = placed.length ? placed[placed.length - 1][1] + BREAK : start
      const more = sittings(after, bed - 30, [...classes], Math.round((a.most_hours - a.normal_hours) * 60), focus)
      more.forEach(([s, e], i) => bits.push({ id: `heavy-${day}-${i}`, day, start: s, end: e, kind: "heavy" }))
    }
    if (shown("brief") && a.brief) bits.push({ id: `brief-${day}`, day, start: wake, end: wake + 20, kind: "brief" })
  }
  if (shown("early")) markEssay(bits, a.finish_early_days)
  return { bits, workHours: Math.round(work / 30) / 2 }
}

/** The example deadline's work: the last two sittings ending by the day you'd finish (`early` days before Friday at
 * 5 PM), drawn in gold, with the deadline's flag. */
function markEssay(bits: Bit[], early: number): void {
  const day = Math.max(0, DUE.day - early)
  const by = day === DUE.day ? DUE.at : 24 * 60
  const work = bits.filter((b) => b.kind === "work" && (b.day < day || (b.day === day && b.end <= by)) && b.day >= day - 1)
  work
    .sort((x, y) => x.day - y.day || x.start - y.start)
    .slice(-2)
    .forEach((b) => (b.kind = "essay"))
  bits.push({ id: "due", day: DUE.day, start: DUE.at, end: DUE.at + 1, kind: "due" })
}

/** The screens, in order: the two that introduce Friday, the questions, and the summary. */
export const ORDER = ["welcome", "how", "day", "load", "focus", "free", "early", "calendars", "brief", "ai", "bring", "ready"]

/** What the week shows for each screen, brightest: the rest is drawn dimmer. */
export const FOCUS: Record<string, Kind[]> = {
  day: ["sleep"],
  load: ["work", "heavy"],
  focus: ["work"],
  free: ["free"],
  early: ["essay", "due"],
  calendars: ["class"],
  brief: ["brief"],
  how: ["work", "event"],
}

/** How far from either end of a day bar (in % of its width) a time's label starts leaning in: a label centered on
 * its time is about this wide on each side ("Bed 12:30am" under the walk's bar). */
export const EDGE = 12

/** Where a time's label sits under a day bar, at `pct` of its width: centered on the time, leaning in near either
 * end so it never leaves the bar (13 Nov: a 6am wake and a 2am bed put "Up 6am" and "Bed 2am" half outside). */
export function underBar(pct: number): { left: string; translate: string } {
  const at = Math.min(Math.max(pct, 0), 100)
  const share = at < EDGE ? (at / EDGE) * 0.5 : at > 100 - EDGE ? 0.5 + ((at - (100 - EDGE)) / EDGE) * 0.5 : 0.5
  return { left: `${at}%`, translate: `${-share * 100}% 0` }
}
