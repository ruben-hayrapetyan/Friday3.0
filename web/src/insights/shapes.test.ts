import { describe, expect, it } from "vitest"
import { clock } from "@/lib/format"
import { toMin } from "@/lib/time"
import { elsewhere, moved, spanOf, ticks, weighing } from "./shapes"

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

describe("weighing", () => {
  it("puts a profile's changes in words, never as objects", () => {
    const said = (rule: string) => ({ late_night: "Wind down before bed", finish_early: "Finish work a day before it’s due" })[rule] ?? rule.replaceAll("_", " ")
    const text = weighing(
      [
        { rule: "late_night", from: 1, to: 1.13 },
        { rule: "elastic_shortfall", from: 1, to: 1.19 },
        { rule: "finish_early", from: 1, to: 0.9 },
      ],
      said,
    )
    expect(text).toBe("More weight on “Wind down before bed” and “elastic shortfall”; less on “Finish work a day before it’s due”.")
    expect(weighing([], said)).toBe("")
  })
})
