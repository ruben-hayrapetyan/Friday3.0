import { describe, expect, it } from "vitest"
import { dueLabel, hours, lateBy, parseLength, sittings, when } from "./format"
import { toMin } from "./time"

describe("rule lengths", () => {
  it("read as hours", () => {
    expect([hours("2h"), hours("1.5h"), hours("1h30m"), hours("90m"), hours("soon")]).toEqual([2, 1.5, 1.5, 1.5, 0])
  })
})

describe("when", () => {
  it("says the time today, the weekday this week, and the date further off", () => {
    expect(when("2026-10-19T14:00", "2026-10-19")).toBe("2pm")
    expect(when("2026-10-23T17:00", "2026-10-19")).toBe("Fri 5pm")
    expect(when("2026-11-06T17:00", "2026-10-19")).toBe("Fri 6 Nov 5pm")
    expect(when("2026-10-23", "2026-10-19")).toBe("Fri")
  })

  it("reads a repeat's window ending at the day start as the end of the day before", () => {
    expect(when("2026-10-27T04:00", "2026-10-20")).toBe("Mon, end of day")
  })
})

describe("typed lengths", () => {
  it("reads minutes and hours the way people type them", () => {
    // personal's reading (COMBINED.md 42): a bare number is hours up to 8, minutes above.
    const read = ["5", "45", "5m", "10 min", "45 minutes", "1h", "1h30", "1h 30m", "1.5h", "2 hrs", "1:15", "an hour and a half"].map(parseLength)
    expect(read).toEqual([300, 45, 5, 10, 45, 60, 90, 90, 90, 120, 75, 90])
  })
  it("refuses what isn't a length", () => {
    expect(["", "soon", "0", "2 days"].map(parseLength)).toEqual([null, null, null, null])
  })
})

describe("due labels", () => {
  const at = (local: string) => toMin(local)
  it("show the date a day out, count down within the day, and count up once past", () => {
    expect(dueLabel("2026-10-30T17:00", at("2026-10-23T09:00"), "2026-10-23")).toEqual({ text: "Fri 30 Oct 5pm", tone: "plain" })
    expect(dueLabel("2026-10-23T17:00", at("2026-10-23T13:48"), "2026-10-23")).toEqual({ text: "in 3h 12m", tone: "soon" })
    expect(dueLabel("2026-10-23T09:00", at("2026-10-23T11:05"), "2026-10-23")).toEqual({ text: "2h 5m over", tone: "over" })
    expect(dueLabel("2026-10-20T09:00", at("2026-10-23T11:00"), "2026-10-23")).toEqual({ text: "3d 2h over", tone: "over" })
  })
})

describe("how late, roughly", () => {
  it("rounds to the quarter hour, at least a quarter, and says days past a day", () => {
    expect([lateBy(0.1), lateBy(1.4), lateBy(3), lateBy(25), lateBy(59)]).toEqual(["15m", "1h 30m", "3h", "1 day", "2 days"])
  })
})

describe("timed sittings", () => {
  it("are a day's timer rows in order, each from its start for as long as it ran", () => {
    const rows = [
      { source: "timer", minutes: 19, start: "2026-10-25T15:11" },
      { source: "timer", minutes: 3, start: "2026-10-25T14:45" },
      { source: "review", minutes: 30, start: "2026-10-25T16:00" },
      { source: "timer", minutes: 40, start: "2026-10-25T11:40" },
      { source: "timer", minutes: 10, start: "2026-10-24T09:00" },
      { source: "timer", minutes: 6, start: "2026-10-25T15:30" }, // picks up where 3:11 left off: one sitting
    ]
    expect(sittings(rows, "2026-10-25")).toBe("11:40am–12:20pm, 2:45–2:48pm, 3:11–3:36pm")
    expect(sittings(rows, "2026-10-23")).toBe("")
  })
})
