// A time typed into a 12-hour box kept the am or pm the box showed: lunch at 12:30pm retyped as 11 became 11pm
// (27 Oct: "i didn't eat lunch at 11PM, that doesn't make sense"). So a time typed without am or pm is read as the
// half of the day it most likely means: inside the hours the thing happens at, after what it follows, else nearest
// what the box had, as a time typed over the calendar already is (lib/timeRange.ts). An am or pm typed is kept.

import { readTime } from "./timeRange"

export interface Expect {
  hours?: readonly [string, string] // when it happens at all, "HH:MM" to "HH:MM"; past midnight when the end is earlier
  after?: string // it comes after this, within 12 hours: a meal's end after its start
  near?: string // else the half nearest this; the time the box had when not given
}

// When each thing happens at all: wide, so only the other half of the day is ruled out (dinner at 1am still counts).
export const MEAL_HOURS = {
  breakfast: ["04:00", "12:59"],
  lunch: ["10:00", "17:00"],
  dinner: ["15:00", "03:00"],
} as const satisfies Record<string, readonly [string, string]>

export const SLEEP_HOURS = {
  done: ["15:00", "05:59"], // done with work
  bed: ["18:00", "07:59"],
  up: ["03:00", "15:59"],
  ready: ["03:00", "17:59"], // ready to work
} as const satisfies Record<string, readonly [string, string]>

export const EXAM_HOURS = ["07:00", "23:59"] as const
// A due or an event typed in the Inbox: in the day, not the small hours ("5" over a due's 11:59pm is 5pm, not 5am).
export const DAY_HOURS = ["06:00", "23:59"] as const

const TIME = /^([01]\d|2[0-3]):[0-5]\d$/
const minute = (t: string) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5))
const clockOf = (m: number) => `${String(Math.floor(m / 60) % 24).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`

/** The same time in the other half of the day: 11:30 and 23:30, 12:15 and 00:15. */
export function otherHalf(time: string): string {
  return clockOf((minute(time) + 720) % 1440)
}

/** Whether a time falls in a span of the day, which runs past midnight when it ends earlier. */
export function inHours(time: string, [from, to]: readonly [string, string]): boolean {
  const [t, a, b] = [minute(time), minute(from), minute(to)]
  return a <= b ? t >= a && t <= b : t >= a || t <= b
}

/** Minutes forward from one time of day to the next, 0 to 1439. */
const forward = (from: string, to: string) => (minute(to) - minute(from) + 1440) % 1440
const apart = (a: string, b: string) => Math.min(forward(a, b), forward(b, a))

/** A time typed in words into a time box, as "HH:MM", with whether Friday chose its half: "11:30", "1130" or "11" over
 * lunch is 11:30am; "11:30p", "11 pm" or "23:30" are as typed; "noon". An empty box takes the half the time is usually
 * meant in, 7 to 11 in the morning and noon to 6:59 in the afternoon, when nothing expected chooses (28 Oct: "the
 * AM/PM doesn't autofill in all time boxes": a box with no time yet left am or pm blank until it was typed). Null
 * when it can't be read. */
export function typedTime(text: string, was: string, expect: Expect = {}): { time: string; guessed: boolean } | null {
  const t = readTime(text)
  if (!t) return null
  if (t.half !== null || t.minute >= 720) return { time: clockOf(t.minute), guessed: false }
  const am = clockOf(t.minute)
  const pm = otherHalf(am)
  const after = expect.after && TIME.test(expect.after) ? expect.after : null
  const fits = (x: string) => (!expect.hours || inHours(x, expect.hours)) && (!after || forward(after, x) < 720)
  if (fits(am) !== fits(pm)) return { time: fits(am) ? am : pm, guessed: true }
  // Both fitting, or neither: the half nearer what the box had (a 1pm event retyped as 3 is 3pm); a tie, or nothing to
  // be near, the half it's usually meant in.
  const near = expect.near ?? (TIME.test(was) ? was : null)
  if (near && TIME.test(near) && apart(pm, near) !== apart(am, near)) return { time: apart(pm, near) < apart(am, near) ? pm : am, guessed: true }
  const hour = Math.floor(t.minute / 60) || 12
  return { time: hour >= 7 && hour <= 11 ? am : pm, guessed: true }
}

/** A span typed as two times of day, as local times from the day `day`: the end the next day when it's before the
 * start (a sitting from 11:30pm to 12:40am). */
export function spanOn(day: string, start: string, end: string): { start: string; end: string } {
  const next = (d: string) => {
    const t = new Date(`${d}T12:00:00Z`)
    t.setUTCDate(t.getUTCDate() + 1)
    return t.toISOString().slice(0, 10)
  }
  return { start: `${day}T${start}`, end: `${minute(end) <= minute(start) ? next(day) : day}T${end}` }
}
