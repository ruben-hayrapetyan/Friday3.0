import { describe, expect, it } from "vitest"
import { pigment, PIGMENTS } from "@/lib/pigments"
import { counts } from "@/settings/CalendarsSection"
import { draftAt, draftOf } from "./EventPane"

describe("an event in the drawer", () => {
  it("drafts a new one an hour long from where it was asked for", () => {
    const d = draftAt("2026-10-21T14:15")
    expect([d.id, d.start, d.end, d.allDay, d.every]).toEqual([null, "2026-10-21T14:15", "2026-10-21T15:15", false, null])
    expect(draftAt("2026-10-21T23:30").end).toBe("2026-10-22T00:30")
  })

  it("reads midnight-to-midnight as all day, and keeps what the event had", () => {
    const base = { id: 7, title: "Fall break", series_id: null, color: "green", notes: "", calendar: "Personal", saves_to_calendar: true }
    const allDay = draftOf({ ...base, start: "2026-10-26T00:00", end: "2026-10-28T00:00" })
    expect([allDay.allDay, allDay.color, allDay.calendar, allDay.savesToCalendar]).toEqual([true, "green", "Personal", true])
    expect(draftOf({ ...base, start: "2026-10-26T00:00", end: "2026-10-26T00:00" }).allDay).toBe(false)
    expect(draftOf({ ...base, start: "2026-10-26T09:00", end: "2026-10-26T10:00" }).allDay).toBe(false)
  })
})

describe("pigments", () => {
  it("are personal's ten, light on paper and lifted on the dark page", () => {
    expect(PIGMENTS.map((p) => p.name)).toContain("Cobalt Violet")
    expect(PIGMENTS).toHaveLength(10)
    expect(pigment("blue", true)).toBe("#2a6c9c")
    expect(pigment("blue", false)).not.toBe(pigment("blue", true))
    expect([pigment(null, true), pigment("chartreuse", true)]).toEqual([null, null])
  })
})

describe("which calendars count as busy", () => {
  const busy = { count_filtered: false, count_free: false, count_reminders: false, calendars: {} as Record<string, boolean> }
  it("leaves room bookings out until you count them", () => {
    expect([counts("Library Rooms", busy), counts("Room Reservations", busy), counts("Classes", busy)]).toEqual([false, false, true])
    expect(counts("Library Rooms", { ...busy, calendars: { "Library Rooms": true } })).toBe(true)
    expect(counts("Classes", { ...busy, calendars: { Classes: false } })).toBe(false)
  })
})

import { isDueWork } from "@/todo/TodoPage"

describe("the Due view", () => {
  const item = (over: Record<string, unknown>) => ({ due: "2026-10-23T23:59", amount: "fixed", preset: "Assignment", ...over }) as never
  it("lists dated work, not meals or habits", () => {
    expect([isDueWork(item({})), isDueWork(item({ due: null })), isDueWork(item({ preset: "Routine" })), isDueWork(item({ amount: "elastic" })), isDueWork(item({ preset: "Habit" }))]).toEqual([true, false, false, false, false])
  })
})
