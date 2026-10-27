import { describe, expect, it } from "vitest"
import { clock } from "@/lib/format"
import { toMin } from "@/lib/time"
import { elsewhere, moved, sides, spanOf, strength, ticks, times } from "./shapes"

const piece = (item_id: number, start: string, end: string) => ({ item_id, title: `#${item_id}`, start: `2026-10-25T${start}`, end: `2026-10-25T${end}` })

describe("moved", () => {
  it("marks what the other version places differently or not at all", () => {
    const lunch = piece(1, "12:00", "12:30")
    const dinner = piece(2, "18:00", "18:45")
    const only = piece(3, "19:00", "22:30")
    const out = moved([lunch, dinner, only], [piece(1, "12:00", "12:30"), piece(2, "18:15", "19:15")])
    expect([out.has(lunch), out.has(dinner), out.has(only)]).toEqual([false, true, true])
  })

  it("says where the other version has it", () => {
    expect(elsewhere(piece(2, "18:00", "18:45"), [piece(2, "18:15", "19:15")], clock)).toBe("6:15pm–7:15pm in the other version")
    expect(elsewhere(piece(3, "19:00", "20:00"), [], clock)).toBe("not in the other version")
  })
})

describe("the mini day's span", () => {
  it("runs half an hour either side, to the half hour, with 12-hour hour labels", () => {
    const { lo, hi } = spanOf([piece(1, "10:00", "10:45"), piece(2, "20:15", "23:20")])
    expect([lo - toMin("2026-10-25"), hi - toMin("2026-10-25")]).toEqual([9 * 60 + 30, 24 * 60])
    expect(ticks(lo, hi).map((t) => t.label)).toEqual(["10am", "11am", "12pm", "1pm", "2pm", "3pm", "4pm", "5pm", "6pm", "7pm", "8pm", "9pm", "10pm", "11pm", "12am"])
  })
})

describe("a suggested set of weights", () => {
  // Your 27 Oct suggestion, in part: from 11 blocks you moved.
  const changes = [
    { rule: "late_night", from: 1, to: 0.78 },
    { rule: "deep_run", from: 1, to: 1.16 },
    { rule: "soft_late", from: 1, to: 0.02 },
    { rule: "you:keep-fri-sat-lighter", from: 1, to: 0.49 },
    { rule: "you:climbing-club-only-when-ahead", from: 1, to: 1.21 },
    { rule: "spread", from: 1, to: 1 },
    { rule: "new_rule", from: 0, to: 1 },
  ]

  it("splits into what matters more and what less, the biggest change first on each side", () => {
    const { more, less } = sides(changes)
    expect(more.map((w) => w.rule)).toEqual(["you:climbing-club-only-when-ahead", "deep_run"])
    expect(less.map((w) => w.rule)).toEqual(["soft_late", "you:keep-fri-sat-lighter", "late_night"])
  })

  it("leaves out what doesn't change, and a weight it can't compare with", () => {
    const { more, less } = sides(changes)
    expect([...more, ...less].map((w) => w.rule)).not.toContain("spread")
    expect([...more, ...less].map((w) => w.rule)).not.toContain("new_rule")
    expect(sides([])).toEqual({ more: [], less: [] })
  })

  it("says how much in words, and marks a big change", () => {
    expect([1.16, 1.4, 2.5, 0.9, 0.7, 0.49, 0.02].map((f) => strength(f).word)).toEqual(["a little more", "more", "much more", "a little less", "less", "much less", "almost none"])
    expect([1.16, 2, 0.51, 0.5, 0.02].map((f) => strength(f).big)).toEqual([false, true, false, true, true])
    expect(sides(changes).less.map((w) => w.big)).toEqual([true, true, false])
  })

  it("writes the factor short", () => {
    expect([times(1.1612), times(0.0213), times(0.49), times(2)]).toEqual(["×1.2", "×0.021", "×0.49", "×2"])
  })
})
