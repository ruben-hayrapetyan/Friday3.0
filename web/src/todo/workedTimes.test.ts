// Logging time worked without the timer, from a task's page (3 Nov).
import { describe, expect, it } from "vitest"
import { spanOn } from "@/lib/ampm"
import { lastHour, recentDays } from "./workedTimes"

describe("glass box", () => {
  it("offers today, yesterday and the five days before", () => {
    const days = recentDays("2026-11-03")
    expect(days.map((d) => d.value)).toEqual(["2026-11-03", "2026-11-02", "2026-11-01", "2026-10-31", "2026-10-30", "2026-10-29", "2026-10-28"])
    expect(days.slice(0, 3).map((d) => d.label)).toEqual(["Today", "Yesterday", "Sun 1 Nov"])
  })
  it("guesses the hour just gone, on the quarter hour", () => {
    expect(lastHour("14:37")).toEqual({ from: "13:30", to: "14:30" })
    expect(lastHour("09:00")).toEqual({ from: "08:00", to: "09:00" })
  })
  it("just after midnight the hour began the evening before", () => {
    expect(lastHour("00:20")).toEqual({ from: "23:15", to: "00:15" })
  })
})

describe("black box", () => {
  it("what is sent is always a span that ends after it starts, an hour long by default", () => {
    for (const now of ["00:00", "00:14", "06:45", "12:00", "23:59"]) {
      const { from, to } = lastHour(now)
      const span = spanOn("2026-11-03", from, to)
      const minutes = (Date.parse(`${span.end}:00Z`) - Date.parse(`${span.start}:00Z`)) / 60000
      expect(minutes).toBe(60)
    }
  })
  it("never offers a day still to come", () => {
    for (const d of recentDays("2026-01-01")) expect(d.value <= "2026-01-01").toBe(true)
  })
})
