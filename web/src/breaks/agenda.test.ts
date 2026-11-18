// A break day in the sidebar's agenda (found in the demo, 18 Nov: Today listed the classes the break paused, and the
// timed work a break day doesn't have): it keeps one-off events, what you timed and what's due, and drops the rest.
import { describe, expect, it } from "vitest"
import type { Schemas } from "@/api/client"
import { agendaOf } from "@/shell/DayAgenda"

const DAY = "2026-11-18"
const event = (id: number, title: string, left_out: string | null = null) =>
  ({ id, title, start: `${DAY}T09:00`, end: `${DAY}T10:00`, left_out }) as unknown as Schemas["ItemOut"]
const block = (key: string, title: string) => ({ key, item_id: 9, title, start: `${DAY}T15:30`, end: `${DAY}T16:45` }) as Schemas["BlockOut"]
const plan = {
  fixed: [event(1, "ENGL 1170 Seminar", "paused"), event(2, "Advising appointment")],
  blocks: [block("T9@1", "Prep: PHYS 1112 Prelim 2")],
  sessions: [block("S5@1", "Reading, timed")],
} as unknown as Schemas["PlanOut"]
const day = (vacation: unknown) => ({ dues: [], days: [{ date: DAY, vacation }] }) as unknown as Schemas["CalendarOut"]

describe("a break day's agenda", () => {
  it("keeps one-off events and what you timed; paused events and planned times go", () => {
    const titles = agendaOf(DAY, plan, day({ id: 1, name: "Thanksgiving break", mode: "light", day_n: 1, days: 5, per_day: 3 })).map((e) => e.title)
    expect(titles).toEqual(["Advising appointment", "Reading, timed"])
  })
  it("a day off a break shows everything, as before", () => {
    expect(agendaOf(DAY, plan, day(null)).map((e) => e.title)).toHaveLength(4)
  })
})
