// The planning day's start the helpers share (lib/dayStart.ts), and the helpers that follow it.
import { afterEach, describe, expect, it } from "vitest"
import { dayStartClock, dayStartMin, minutesOf, setDayStart } from "./dayStart"
import { when } from "./format"
import { fitAxis } from "./time"

afterEach(() => setDayStart("04:00"))

describe("the day start", () => {
  it("is 4am until settings say otherwise, and anything unreadable is 4am", () => {
    expect([dayStartMin(), dayStartClock()]).toEqual([240, "04:00"])
    for (const wrong of [undefined, null, "", "6am", "25:00", "6:5"]) expect(minutesOf(wrong)).toBe(240)
  })

  it("is what settings give, in minutes and as a clock", () => {
    setDayStart("06:30")
    expect([dayStartMin(), dayStartClock()]).toEqual([390, "06:30"])
    setDayStart("0:00")
    expect([dayStartMin(), dayStartClock()]).toEqual([0, "00:00"])
    setDayStart(undefined)
    expect(dayStartMin()).toBe(240)
  })
})

describe("what follows it", () => {
  const block = (start: string, end: string) => ({ start, end })
  const axis = { startMin: 8 * 60, endMin: 23 * 60 }

  it("a repeat's window ending at a 6am day start is the end of the day before; 4am is then just 4am", () => {
    setDayStart("06:00")
    expect(when("2026-10-27T06:00", "2026-10-20")).toBe("Mon, end of day")
    expect(when("2026-10-27T04:00", "2026-10-20")).toBe("Tue 27 Oct 4am") // a week off: with its date
  })

  it("the calendar opens at 12am for 5am when the day starts at 6am: the night's small hours; 6am opens at 6am", () => {
    setDayStart("06:00")
    const week = ["2026-10-26", "2026-10-27"]
    // 15 Nov: 5am Tuesday is under Tuesday's date, in the night's small hours, so the columns open at 12am
    expect(fitAxis(axis, [block("2026-10-27T05:00", "2026-10-27T05:30")], week)).toEqual({ startMin: 0, endMin: axis.endMin })
    expect(fitAxis(axis, [block("2026-10-26T06:00", "2026-10-26T07:00")], week).startMin).toBe(360)
  })
})
