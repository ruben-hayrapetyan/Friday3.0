import { describe, expect, it } from "vitest"
import { addDays, fromMin, hourMarks, layout, toMin } from "./time"

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
    expect(marks[0]).toEqual({ top: 30, label: "08:00" })
    expect(marks.at(-1)).toEqual({ top: 990, label: "00:00" })
  })
})
