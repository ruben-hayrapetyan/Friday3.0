// The walk's route (29 Oct: "i want it to be like very well animated, similar to c-nell-portfolio.vercel.app", then
// "make it as realistic as possible though"): one street through a small college town in late October, from dawn on
// Monday to Sunday evening. Each question is asked somewhere along it, mostly inside: your room when you get up, the
// library for work, the notice board outside the lecture hall for deadlines, home in the evening, the park on Saturday,
// the café for the morning brief, the post office for what comes in. Pure: where each step is and what time it is
// there; walk/World.ts builds the street and walks it.

import type { Schemas } from "@/api/client"
import { clockSetting } from "@/lib/clock"

type Answers = Schemas["SetupInput"]

export type Place = "start" | "dorm" | "library" | "hall" | "home" | "night" | "park" | "cafe" | "post" | "end"

export interface Stop {
  place: Place
  spot: number // where in the place you stand (the library has three)
  title: string // "The library", as the card says where you are
  day: string // "Monday"
  at: (a: Answers) => number // minutes after midnight there
}

export function minutesOf(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number)
  return h * 60 + m
}

export const STOPS: Record<string, Stop> = {
  hello: { place: "start", spot: 0, title: "Friday", day: "Monday", at: () => 6 * 60 + 40 },
  school: { place: "dorm", spot: 1, title: "Your room", day: "Monday", at: (a) => minutesOf(a.wake) },
  wake: { place: "dorm", spot: 0, title: "Your room", day: "Monday", at: (a) => minutesOf(a.wake) },
  work: { place: "library", spot: 0, title: "The library", day: "Monday", at: () => 13 * 60 },
  heavy: { place: "library", spot: 1, title: "The library", day: "Thursday", at: () => 13 * 60 + 20 },
  focus: { place: "library", spot: 2, title: "The library", day: "Monday", at: () => 13 * 60 + 40 },
  deadline: { place: "hall", spot: 0, title: "Outside the lecture hall", day: "Wednesday", at: () => 16 * 60 + 30 },
  evening: { place: "home", spot: 0, title: "Home", day: "Monday", at: (a) => (a.evening_free > 0 ? minutesOf(a.evening_from) : 19 * 60) },
  bed: { place: "night", spot: 0, title: "Bedtime", day: "Monday", at: (a) => minutesOf(a.bedtime) },
  weekend: { place: "park", spot: 0, title: "The park", day: "Saturday", at: () => 13 * 60 },
  brief: { place: "cafe", spot: 0, title: "The café", day: "Tuesday", at: (a) => minutesOf(a.wake) + 30 },
  ai: { place: "post", spot: 0, title: "The post office", day: "Sunday", at: () => 11 * 60 },
  bring: { place: "post", spot: 1, title: "The post office", day: "Sunday", at: () => 11 * 60 + 10 },
  calendars: { place: "post", spot: 2, title: "The post office", day: "Sunday", at: () => 11 * 60 + 20 },
  build: { place: "end", spot: 0, title: "Your week", day: "Sunday", at: () => 18 * 60 + 15 },
  reveal: { place: "end", spot: 1, title: "Your week", day: "Sunday", at: () => 18 * 60 + 35 },
  start: { place: "end", spot: 2, title: "Your week", day: "Sunday", at: () => 18 * 60 + 55 },
}

/** The places along the street, in order, and the side each is on (1 east, -1 west), turn and turn about. Rooms you
 * see the sun rise in face east; the one you watch it set from faces west. */
export const ROUTE: [Place, number][] = [
  ["start", 0],
  ["dorm", 1],
  ["library", -1],
  ["hall", 1],
  ["home", -1],
  ["night", 1],
  ["park", -1],
  ["cafe", 1],
  ["post", -1],
  ["end", 0],
]

// Metres of street between places: each across the street from the last and a little further up, so getting from
// one to the next is a few steps out of a door and over the road (30 Oct: "make it walk less").
export const GAP = 10

/** How far up the street a place is (the street runs north, toward -z). */
export function placeZ(place: Place): number {
  return -ROUTE.findIndex(([p]) => p === place) * GAP
}

export function sideOf(place: Place): number {
  return ROUTE.find(([p]) => p === place)?.[1] ?? 0
}

/** "7:30 AM", or "07:30" on the 24-hour clock (lib/clock.ts): a time as a clock shows it. */
export function clockFace(minutes: number): string {
  const m = ((Math.round(minutes) % 1440) + 1440) % 1440
  const h = Math.floor(m / 60)
  if (clockSetting() === "24h") return `${String(h).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`
  return `${h % 12 || 12}:${String(m % 60).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`
}
