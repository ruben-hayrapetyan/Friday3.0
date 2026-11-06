// More than one of a meal in a day (5 Nov: "sometimes i have 4 meals (2 dinners)").
import { describe, expect, it } from "vitest"
import type { Schemas } from "@/api/client"
import { pastMeals } from "@/plan/pastMeals"
import { toMin } from "@/lib/time"
import { addable, mealLabel } from "./mealNames"

const meal = (over: Partial<Schemas["MealOut"]>): Schemas["MealOut"] => ({ id: 1, kind: "dinner", date: "2026-11-04", skipped: false, nth: 1, ...over }) as Schemas["MealOut"]

describe("a meal's name by its place that day (black box)", () => {
  it("is the meal, then second, third…, then a number", () => {
    expect([1, 2, 3, 5, 6].map((n) => mealLabel("dinner", n))).toEqual(["Dinner", "Second dinner", "Third dinner", "Fifth dinner", "Dinner 6"])
  })
  it("never counts snacks", () => expect(mealLabel("snack", 4)).toBe("Snack"))
})

describe("a day's + choices (black box)", () => {
  it("offer the meals not recorded, and another of each one eaten, numbered after the ones had", () => {
    const day = [meal({ id: 1, kind: "dinner" }), meal({ id: 2, kind: "dinner", nth: 2 }), meal({ id: 3, kind: "lunch" })]
    expect(addable(day)).toEqual({ missing: ["breakfast"], another: [{ kind: "lunch", nth: 2 }, { kind: "dinner", nth: 3 }] })
  })
  it("a skipped meal is recorded but no meal to have another of", () => {
    expect(addable([meal({ kind: "lunch", skipped: true })])).toEqual({ missing: ["breakfast", "dinner"], another: [] })
  })
  it("a day with nothing offers every meal and nothing more", () => {
    expect(addable([])).toEqual({ missing: ["breakfast", "lunch", "dinner"], another: [] })
  })
})

describe("two dinners on the calendar (black box)", () => {
  it("are two done blocks, the second named for its place, not for the routine the first ticked off", () => {
    const routine = { key: "T7@2026-11-04T18:00", item_id: 7, title: "Dinner", area: null, preset: "Routine", start: "2026-11-04T18:00", end: "2026-11-04T18:45" }
    const day = [meal({ id: 1, item_id: 7, start: "2026-11-04T18:00", end: "2026-11-04T18:45" }), meal({ id: 2, item_id: 7, nth: 2, start: "2026-11-04T22:00", end: "2026-11-04T22:30" })]
    const found = pastMeals({ on: true, days: [{ date: "2026-11-04", meals: day }] } as Schemas["MealsOut"], { blocks: [routine as never] }, toMin("2026-11-04T23:00"))
    expect(found.map((m) => [m.block.key, m.block.title, m.block.start])).toEqual([
      ["M1", "Dinner", "2026-11-04T18:00"],
      ["M2", "Second dinner", "2026-11-04T22:00"],
    ])
  })
})
