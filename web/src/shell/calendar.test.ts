import { describe, expect, it } from "vitest"
import type { Schemas } from "@/api/client"
import { dueOn } from "@/hooks/useDrop"
import { agendaOf } from "./DayAgenda"

describe("dropping a task on a day", () => {
  it("keeps the time it was due, or makes it due at the end of the day", () => {
    expect(dueOn("2026-10-30", "2026-10-25T17:00")).toBe("2026-10-30T17:00")
    expect(dueOn("2026-10-30", null)).toBe("2026-10-30T23:59")
  })
})

describe("the day's agenda", () => {
  it("runs all-day events first, then events, work and deadlines by the clock", () => {
    const plan = {
      fixed: [
        { id: 1, title: "Lecture", start: "2026-10-22T11:40", end: "2026-10-22T12:55" },
        { id: 2, title: "Fall break", start: "2026-10-22T00:00", end: "2026-10-23T00:00" },
        { id: 3, title: "Tomorrow", start: "2026-10-23T09:00", end: "2026-10-23T10:00" },
      ],
      blocks: [{ key: "T9@2026-10-22T09:00", item_id: 9, title: "Problem set", start: "2026-10-22T09:00", end: "2026-10-22T10:00" }],
    } as unknown as Schemas["PlanOut"]
    const calendar = { dues: [{ item_id: 9, title: "Problem set", due: "2026-10-22T23:59" }] } as unknown as Schemas["CalendarOut"]
    const agenda = agendaOf("2026-10-22", plan, calendar)
    expect(agenda.map((e) => [e.title, e.sort])).toEqual([
      ["Fall break", "allday"],
      ["Problem set", "work"],
      ["Lecture", "event"],
      ["Problem set", "due"],
    ])
  })
})

describe("the agenda's past", () => {
  it("is the work as it went: sittings in, timed and deleted blocks out, missed ones marked", () => {
    const block = (key: string, start: string, end: string, state?: "done" | "timed" | "missed" | "gone") => ({ key, item_id: 1, title: key, start, end, state })
    const plan = {
      plan_id: 1,
      blocks: [block("T1@a", "2026-10-25T09:00", "2026-10-25T10:00", "missed"), block("T1@b", "2026-10-25T11:00", "2026-10-25T12:00", "timed"), block("T1@c", "2026-10-25T13:00", "2026-10-25T14:00", "gone"), block("T1@d", "2026-10-25T15:00", "2026-10-25T16:00")],
      sessions: [block("S1@e", "2026-10-25T11:10", "2026-10-25T11:50")],
      fixed: [],
      day_hours: {},
    } as unknown as Schemas["PlanOut"]
    const agenda = agendaOf("2026-10-25", plan, undefined)
    expect(agenda.map((e) => [e.key, !!e.missed])).toEqual([
      ["T1@a", true],
      ["S1@e", false],
      ["T1@d", false],
    ])
  })
})
