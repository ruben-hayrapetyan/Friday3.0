import { describe, expect, it } from "vitest"
import { fixedToday } from "./fixedToday"

const ev = (id: number, start: string, end: string) => ({ id, start, end })

describe("the brief's fixed today (black box)", () => {
  it("says All day for a whole-day event, never 12am", () => {
    const shown = fixedToday([ev(1, "2026-11-04T00:00", "2026-11-05T00:00")])
    expect(shown.map((s) => s.time)).toEqual(["All day"])
  })

  it("puts whole-day events first, then the rest by the clock", () => {
    const shown = fixedToday([
      ev(1, "2026-11-04T14:30", "2026-11-04T15:20"),
      ev(2, "2026-11-04T09:05", "2026-11-04T09:55"),
      ev(3, "2026-11-04T00:00", "2026-11-05T00:00"),
    ])
    expect(shown.map((s) => [s.item.id, s.time])).toEqual([
      [3, "All day"],
      [2, "9:05am"],
      [1, "2:30pm"],
    ])
  })

  it("keeps an event starting at midnight but ending that day as a time", () => {
    expect(fixedToday([ev(1, "2026-11-04T00:00", "2026-11-04T01:00")])[0].time).toBe("12am")
  })

  it("loses nothing", () => {
    const fixed = Array.from({ length: 9 }, (_, n) => ev(n, n % 2 ? "2026-11-04T00:00" : `2026-11-04T1${n}:00`, n % 2 ? "2026-11-06T00:00" : `2026-11-04T1${n}:30`))
    expect(fixedToday(fixed).map((s) => s.item.id).sort()).toEqual(fixed.map((f) => f.id).sort())
  })
})

describe("the brief's fixed today (glass box)", () => {
  it("reads a whole-day event begun on an earlier day as whole-day too", () => {
    // a three-day trip that started yesterday: start and end are midnights, as plan/wholeDay.isWholeDay reads them
    expect(fixedToday([ev(1, "2026-11-03T00:00", "2026-11-06T00:00")])[0].time).toBe("All day")
  })

  it("shows no time for an item without a start", () => {
    expect(fixedToday([{ id: 1, start: null, end: null }])).toEqual([{ item: { id: 1, start: null, end: null }, time: "" }])
  })
})
