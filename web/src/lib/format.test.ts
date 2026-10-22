import { describe, expect, it } from "vitest"
import { hours, parseLength, when } from "./format"

describe("rule lengths", () => {
  it("read as hours", () => {
    expect([hours("2h"), hours("1.5h"), hours("1h30m"), hours("90m"), hours("soon")]).toEqual([2, 1.5, 1.5, 1.5, 0])
  })
})

describe("when", () => {
  it("says the time today, the weekday this week, and the date further off", () => {
    expect(when("2026-10-19T14:00", "2026-10-19")).toBe("14:00")
    expect(when("2026-10-23T17:00", "2026-10-19")).toBe("Fri 17:00")
    expect(when("2026-11-06T17:00", "2026-10-19")).toBe("Fri 6 Nov 17:00")
    expect(when("2026-10-23", "2026-10-19")).toBe("Fri")
  })

  it("reads a repeat's window ending at the day start as the end of the day before", () => {
    expect(when("2026-10-27T04:00", "2026-10-20")).toBe("Mon, end of day")
  })
})

describe("typed lengths", () => {
  it("reads minutes and hours the way people type them", () => {
    const read = ["5", "5m", "10 min", "45 minutes", "1h", "1h30", "1h 30m", "1.5h", "2 hrs", "1:15"].map(parseLength)
    expect(read).toEqual([5, 5, 10, 45, 60, 90, 90, 90, 120, 75])
  })
  it("refuses what isn't a length", () => {
    expect(["", "soon", "0", "h"].map(parseLength)).toEqual([null, null, null, null])
  })
})
