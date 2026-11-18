// The Now bar on a break day (found in the demo, 18 Nov: it offered "Now 3:30–4:45pm, Prep: PHYS 1112 Prelim 2, 0:08
// left, Start" on a day with a list and no times): only what you're timing, or an event you're in, gets its row.
import { describe, expect, it } from "vitest"
import { nowRow } from "@/now/Dock"

describe("the Now bar's main row", () => {
  it("on a break day: none for planned work or free time", () => {
    expect(nowRow({ onBreak: true, timing: false, inEvent: false })).toBe(false)
  })
  it("on a break day: what you're timing, and an event you're in, still show", () => {
    expect(nowRow({ onBreak: true, timing: true, inEvent: false })).toBe(true)
    expect(nowRow({ onBreak: true, timing: false, inEvent: true })).toBe(true)
  })
  it("any other day: always", () => {
    expect(nowRow({ onBreak: false, timing: false, inEvent: false })).toBe(true)
  })
})
