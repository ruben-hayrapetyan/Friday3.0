import { describe, expect, it } from "vitest"
import { addDays, ampm, dayRange, fitAxis, fromMin, hourMarks, layout, nearestAt, pageStart, toMin } from "./time"

const axis = { startMin: 7 * 60 + 30, endMin: 24 * 60 + 30 }
const block = (start: string, end: string, name = "") => ({ start, end, name })

describe("the minute clock", () => {
  it("round-trips local times and steps over month ends", () => {
    expect(fromMin(toMin("2026-10-20T14:15"))).toBe("2026-10-20T14:15")
    expect(addDays("2026-10-31", 1)).toBe("2026-11-01")
  })
})

describe("layout", () => {
  it("places a block by its minutes from the column's top", () => {
    const [placed] = layout([block("2026-10-20T09:00", "2026-10-20T10:30")], "2026-10-20", axis)
    expect([placed.top, placed.height, placed.column, placed.columns]).toEqual([90, 90, 0, 1])
  })

  it("puts a block after midnight in the evening before and clips at the axis", () => {
    const late = block("2026-10-21T00:00", "2026-10-21T01:00")
    expect(layout([late], "2026-10-20", axis).map((p) => [p.top, p.height])).toEqual([[990, 30]])
    expect(layout([late], "2026-10-21", axis)).toEqual([])
  })

  it("shares the width between overlapping blocks only", () => {
    const placed = layout(
      [
        block("2026-10-20T09:00", "2026-10-20T11:00", "a"),
        block("2026-10-20T10:00", "2026-10-20T12:00", "b"),
        block("2026-10-20T11:00", "2026-10-20T12:00", "c"),
        block("2026-10-20T14:00", "2026-10-20T15:00", "d"),
      ],
      "2026-10-20",
      axis,
    )
    const by = Object.fromEntries(placed.map((p) => [p.item.name, [p.column, p.columns]]))
    expect(by).toEqual({ a: [0, 2], b: [1, 2], c: [0, 2], d: [0, 1] })
  })
})

describe("hour marks", () => {
  it("label each whole hour on the axis, past midnight too", () => {
    const marks = hourMarks(axis)
    expect(marks[0]).toEqual({ top: 30, label: "8am" })
    expect(marks.at(-1)).toEqual({ top: 990, label: "12am" })
  })
})

describe("ampm", () => {
  it("reads times on a 12-hour clock", () => {
    expect(["00:00", "00:30", "09:05", "12:00", "13:10", "23:59"].map(ampm)).toEqual(["12am", "12:30am", "9:05am", "12pm", "1:10pm", "11:59pm"])
    expect(ampm("2026-10-20T14:30")).toBe("2:30pm")
  })
})

describe("fitAxis", () => {
  const week = ["2026-10-26", "2026-10-27"]
  it("opens the day at the hour of anything before the wake time, and closes it after anything later", () => {
    expect(fitAxis(axis, [block("2026-10-26T06:00", "2026-10-26T08:00")], week)).toEqual({ startMin: 360, endMin: axis.endMin })
    expect(fitAxis(axis, [block("2026-10-27T06:45", "2026-10-27T07:00")], week).startMin).toBe(360)
    expect(fitAxis(axis, [block("2026-10-27T23:30", "2026-10-28T01:10")], week).endMin).toBe(26 * 60)
  })
  it("leaves it be for what fits, what's on other days, and past midnight's own small hours", () => {
    expect(fitAxis(axis, [block("2026-10-26T09:00", "2026-10-26T10:00"), block("2026-10-29T05:00", "2026-10-29T06:00")], week)).toEqual(axis)
    // 1am Tuesday is Monday night: it stretches Monday's end, never Tuesday's start back to 1am
    expect(fitAxis(axis, [block("2026-10-27T01:00", "2026-10-27T02:00")], week)).toEqual({ startMin: axis.startMin, endMin: 26 * 60 })
    expect(fitAxis(axis, [block("2026-10-26T05:00", "2026-10-26T05:00")], week)).toEqual(axis) // no length
  })
  it("stays a day long at most", () => {
    const late = { startMin: 360, endMin: 28 * 60 }
    expect(fitAxis(late, [block("2026-10-26T04:00", "2026-10-26T05:00")], week)).toEqual({ startMin: 240, endMin: 28 * 60 })
  })
})

describe("a corrected time", () => {
  it("lands on the date nearest the time it replaces", () => {
    expect(nearestAt("2026-10-21T00:20", "23:50")).toBe("2026-10-20T23:50") // a bedtime after midnight, made earlier
    expect(nearestAt("2026-10-20T23:40", "00:30")).toBe("2026-10-21T00:30") // and the other way
    expect(nearestAt("2026-10-21T07:30", "08:15")).toBe("2026-10-21T08:15") // the same morning
  })
})

describe("calendar pages are centred on the day (4 Nov)", () => {
  it("a week shows three days either side, whatever weekday it is", () => {
    expect(dayRange(pageStart("2026-11-04", 7), 7)).toEqual(["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-07"])
    expect(pageStart("2026-11-02", 7)).toBe("2026-10-30") // a Monday sits in the middle too, not first
    expect(pageStart("2027-01-01", 7)).toBe("2026-12-29") // across a year
  })

  it("three days are the day before, the day, and the day after", () => {
    expect(dayRange(pageStart("2026-11-04", 3), 3)).toEqual(["2026-11-03", "2026-11-04", "2026-11-05"])
    expect(pageStart("2026-03-01", 3)).toBe("2026-02-28")
  })

  it("a day is that day; the middle of every page is the day it was asked for", () => {
    expect(pageStart("2026-10-28", 1)).toBe("2026-10-28")
    for (const days of [1, 3, 7]) for (const day of ["2026-10-26", "2026-11-01", "2026-12-31"]) expect(dayRange(pageStart(day, days), days)[Math.floor(days / 2)]).toBe(day)
  })
})
