// Dragging across days (glass box): the span is the same whichever way you drag, and holds its ends.
import { describe, expect, it } from "vitest"
import { inSpan, ordered } from "./daySpan"

describe("a span of days", () => {
  it("runs from the earlier day to the later, dragged either way", () => {
    expect(ordered({ from: "2026-11-27", to: "2026-11-25" })).toEqual({ from: "2026-11-25", to: "2026-11-27" })
    expect(ordered({ from: "2026-11-25", to: "2026-11-27" })).toEqual({ from: "2026-11-25", to: "2026-11-27" })
  })
  it("holds its first and last day and those between, and nothing without a span", () => {
    const span = { from: "2026-11-27", to: "2026-11-25" }
    expect(["2026-11-24", "2026-11-25", "2026-11-26", "2026-11-27", "2026-11-28"].map((d) => inSpan(span, d))).toEqual([false, true, true, true, false])
    expect(inSpan(null, "2026-11-25")).toBe(false)
  })
})
