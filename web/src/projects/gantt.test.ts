import { describe, expect, it } from "vitest"
import { ahead, dueAt, frame, place } from "./gantt"

describe("the timeline's frame", () => {
  it("runs from today through the due date, showing 7am to 11pm", () => {
    expect(frame("2026-10-24", "2026-10-31T23:59", [])).toEqual({ first: "2026-10-24", days: 8, from: 420, to: 1380 })
  })

  it("is at least three days, and takes in a session past the due date", () => {
    expect(frame("2026-10-24", null, []).days).toBe(3)
    expect(frame("2026-10-24", "2026-10-25", [{ start: "2026-10-28T14:00", end: "2026-10-28T15:00" }]).days).toBe(5)
  })

  it("widens the hours to a session outside them, to the whole night when one crosses midnight", () => {
    expect(frame("2026-10-24", null, [{ start: "2026-10-25T06:30", end: "2026-10-25T08:00" }])).toMatchObject({ from: 360, to: 1380 })
    expect(frame("2026-10-24", null, [{ start: "2026-10-25T23:00", end: "2026-10-26T00:00" }])).toMatchObject({ days: 3, to: 1440 })
  })
})

describe("place", () => {
  const f = frame("2026-10-24", "2026-10-25", []) // three days, 7am to 11pm
  it("puts a time in its day's column, proportionally through the hours shown", () => {
    expect(place(f, "2026-10-24T07:00")).toBe(0)
    expect(place(f, "2026-10-25T15:00")).toBeCloseTo(1.5 / 3)
    expect(place(f, "2026-10-26T23:00")).toBe(1)
  })

  it("puts the folded night at the edge of its day, and clamps outside the frame", () => {
    expect(place(f, "2026-10-25T03:00")).toBeCloseTo(1 / 3)
    expect(place(f, "2026-10-25T23:59")).toBeCloseTo(2 / 3)
    expect(place(f, "2026-10-20T12:00")).toBe(0)
    expect(place(f, "2026-11-20T12:00")).toBe(1)
  })
})

describe("ahead", () => {
  it("says one day, not one days", () => {
    expect([ahead(20), ahead(60), ahead(300), ahead(1500), ahead(4000)]).toEqual(["under an hour", "1 hour", "5 hours", "1 day", "3 days"])
  })
})

describe("dueAt", () => {
  it("reads a bare due date as the end of that day", () => {
    expect([dueAt("2026-10-31"), dueAt("2026-10-31T17:00")]).toEqual(["2026-10-31T23:59", "2026-10-31T17:00"])
  })
})
