import { describe, expect, it } from "vitest"
import type { Block, Schemas } from "@/api/client"
import { layout, toMin } from "@/lib/time"
import { eatenRoutines, pastMeals } from "./pastMeals"

const meal = (over: Partial<Schemas["MealOut"]>): Schemas["MealOut"] => ({ id: 1, kind: "lunch", date: "2026-11-04", skipped: false, ...over }) as Schemas["MealOut"]
const meals = (list: Schemas["MealOut"][], over: Partial<Schemas["MealsOut"]> = {}): Schemas["MealsOut"] =>
  ({ on: true, days: [{ date: "2026-11-04", meals: list }], ...over }) as Schemas["MealsOut"]
const block = (over: Partial<Block>): Block => ({ key: "T7@2026-11-04T12:30", item_id: 7, title: "Lunch", area: "Home", preset: "Routine", start: "2026-11-04T12:30", end: "2026-11-04T13:00", ...over }) as Block
const now = toMin("2026-11-04T15:00")
const lunchPlanned = { blocks: [block({})] }

// Glass box: how a recorded meal becomes a block.
describe("a meal you ate becomes a done block", () => {
  it("at the time you ate it, dressed as the routine it ticked off", () => {
    const [m] = pastMeals(meals([meal({ id: 3, item_id: 7, start: "2026-11-04T11:20", end: "2026-11-04T11:40" })]), lunchPlanned, now)
    expect(m.eating).toBe(false)
    expect(m.block).toMatchObject({ key: "M3", item_id: 7, title: "Lunch", area: "Home", preset: "Routine", start: "2026-11-04T11:20", end: "2026-11-04T11:40", state: "done" })
  })

  it("with no routine, named for the meal, with a key of its own that no routine has", () => {
    const [m] = pastMeals(meals([meal({ id: 4, kind: "breakfast", start: "2026-11-04T08:00", end: "2026-11-04T08:20" })]), lunchPlanned, now)
    expect(m.block).toMatchObject({ title: "Breakfast", preset: "Routine", item_id: -4 })
    expect(eatenRoutines([m]).size).toBe(0)
  })

  it("the one you're eating runs to now, once, and isn't done yet", () => {
    const eating = meal({ id: 5, item_id: 7, start: "2026-11-04T14:40" })
    const found = pastMeals(meals([eating], { eating }), lunchPlanned, now)
    expect(found).toHaveLength(1)
    expect(found[0]).toMatchObject({ eating: true, block: { end: "2026-11-04T15:00", state: null } })
  })
})

// Black box: what the calendar is handed.
describe("the meals on the calendar", () => {
  it("are only the ones eaten: skipped meals and tracking off draw nothing", () => {
    expect(pastMeals(meals([meal({ skipped: true })]), lunchPlanned, now)).toEqual([])
    expect(pastMeals(meals([meal({ start: "2026-11-04T11:20", end: "2026-11-04T11:40" })], { on: false }), lunchPlanned, now)).toEqual([])
    expect(pastMeals(undefined, lunchPlanned, now)).toEqual([])
  })

  it("take the place of the routine they ticked off, whose planned pieces give way", () => {
    const found = pastMeals(meals([meal({ id: 3, item_id: 7, start: "2026-11-04T11:20", end: "2026-11-04T11:40" })]), lunchPlanned, now)
    expect([...eatenRoutines(found)]).toEqual([7])
  })

  it("sit on the day and hour you ate, labeled, like any block", () => {
    const found = pastMeals(meals([meal({ id: 3, item_id: 7, start: "2026-11-04T19:00", end: "2026-11-04T19:40", kind: "dinner" })]), { blocks: [] }, toMin("2026-11-04T21:00"))
    const [placed] = layout(found.map((m) => m.block), "2026-11-04", { startMin: 8 * 60, endMin: 24 * 60 })
    expect(placed).toMatchObject({ top: 11 * 60, height: 40 })
    expect(placed.item.title).toBe("Dinner")
    expect(layout(found.map((m) => m.block), "2026-11-03", { startMin: 8 * 60, endMin: 24 * 60 })).toEqual([])
  })
})
