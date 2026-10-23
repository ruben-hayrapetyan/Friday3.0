import { describe, expect, it } from "vitest"
import type { Schemas } from "@/api/client"
import { shown, withShown } from "./shown"

const off = { toolbar: ["Library Rooms"], showing: [], showFiltered: false }

describe("an event on two of your calendars", () => {
  it("is drawn once; one at another time, or with another title, is its own", () => {
    const lecture = { title: "Chem 2090 Lecture", start: "2026-10-23T12:20", end: "2026-10-23T13:10" }
    const plan = {
      fixed: [
        { id: 1, calendar: "Calendar", ...lecture },
        { id: 2, calendar: "me@gmail.com", ...lecture },
        { id: 3, calendar: "Calendar", ...lecture, start: "2026-10-26T12:20", end: "2026-10-26T13:10" },
        { id: 4, calendar: "Calendar", ...lecture, title: "Chem 2090 Discussion" },
      ],
      blocks: [],
    } as unknown as Schemas["PlanOut"]
    expect(withShown(plan, { toolbar: [], showing: [], showFiltered: true }).fixed.map((f) => f.id)).toEqual([1, 3, 4])
  })
})

describe("events you toggle in the title row", () => {
  it("stay off the calendar until you switch them on", () => {
    expect(shown({ calendar: "Library Rooms" }, off)).toBe(false)
    expect(shown({ calendar: "Library Rooms" }, { ...off, showing: ["Library Rooms"] })).toBe(true)
    expect(shown({ calendar: "Home", filtered: true }, off)).toBe(false)
    expect(shown({ calendar: "Home", filtered: true }, { ...off, showFiltered: true })).toBe(true)
  })

  it("leaves every other event alone", () => {
    expect(shown({ calendar: "Home" }, off)).toBe(true)
    expect(shown({ calendar: null }, off)).toBe(true)
    expect(shown({}, off)).toBe(true)
  })

  it("filtered office hours on a toggled calendar need both switched on", () => {
    const both = { calendar: "Library Rooms", filtered: true }
    expect(shown(both, { ...off, showing: ["Library Rooms"] })).toBe(false)
    expect(shown(both, { ...off, showing: ["Library Rooms"], showFiltered: true })).toBe(true)
  })

  it("drops them from the plan the calendar draws, and keeps the plan as it is when nothing is hidden", () => {
    const plan = {
      fixed: [
        { id: 1, title: "Dentist", calendar: "Home" },
        { id: 2, title: "Olin 603", calendar: "Library Rooms" },
        { id: 3, title: "CS 2112 Office Hours", filtered: true },
      ],
      blocks: [],
    } as unknown as Schemas["PlanOut"]
    expect(withShown(plan, off).fixed.map((f) => f.id)).toEqual([1])
    const all = { toolbar: [], showing: [], showFiltered: true }
    expect(withShown(plan, all)).toBe(plan)
  })
})
