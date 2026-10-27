// A time typed into a 12-hour box keeps the am or pm the box showed: lunch at 12:30pm retyped as 11 became 11pm
// (27 Oct: "i didn't eat lunch at 11PM, that doesn't make sense"). So a typed time is read as the half of the day it
// most likely means: inside the hours the thing happens at, after what it follows, else nearest what the box had, as
// a time typed over the calendar already is (lib/timeRange.ts). Turning am into pm, or back, yourself is kept.

import { ampm } from "./time"

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

/** The time meant when `typed` replaces `was` in a box expecting `expect`: what was typed, or the same time in the
 * other half of the day when only that one fits, or, both fitting or neither, when it's nearer what's expected. */
export function meant(typed: string, was: string, expect: Expect = {}): string {
  if (!TIME.test(typed)) return typed
  if (TIME.test(was) && typed === otherHalf(was)) return typed // you turned am into pm, or back
  const other = otherHalf(typed)
  const after = expect.after && TIME.test(expect.after) ? expect.after : null
  const fits = (t: string) => (!expect.hours || inHours(t, expect.hours)) && (!after || forward(after, t) < 720)
  if (fits(typed) !== fits(other)) return fits(typed) ? typed : other
  const near = expect.near ?? was
  if (!TIME.test(near)) return typed
  return apart(other, near) < apart(typed, near) ? other : typed
}

/** What to say when a typed time was read the other way: "Made it 11:30am" and "keep 11:30pm". */
export function readAs(typed: string, as: string): { made: string; keep: string } | null {
  return typed === as || !TIME.test(typed) ? null : { made: ampm(as), keep: ampm(typed) }
}
