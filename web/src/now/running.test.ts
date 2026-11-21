import { describe, expect, it } from "vitest"
import type { Schemas } from "@/api/client"
import { runningNow } from "./running"

const timer = (item_id: number, title: string, started: string) => ({ item_id, title, started, minutes: 0, elapsed_s: 30, message: "" })

describe("what's going on at once (21 Nov: timing CATC, then lunch, then math)", () => {
  it("every timer and the meal you're eating, oldest first; the timer started last is the main one", () => {
    const status = { timer: timer(2, "MATH 1910", "2026-11-21T13:05"), alongside: [timer(1, "CATC", "2026-11-21T12:00")] } as unknown as Schemas["StatusOut"]
    const meals = { on: true, next: null, eating: { id: 7, kind: "lunch", date: "2026-11-21", start: "2026-11-21T12:40", end: null, minutes: null, skipped: false, item_id: null, nth: 1 } } as unknown as Schemas["MealsOut"]
    const going = runningNow(status, meals)
    expect(going.map((r) => [r.title, r.kind, !!r.main])).toEqual([["CATC", "timer", false], ["Lunch", "meal", false], ["MATH 1910", "timer", true]])
  })

  it("one thing, or none: no list to draw side by side", () => {
    expect(runningNow({ timer: timer(1, "CATC", "2026-11-21T12:00"), alongside: [] } as unknown as Schemas["StatusOut"], { on: true, eating: null } as unknown as Schemas["MealsOut"])).toHaveLength(1)
    expect(runningNow(undefined, undefined)).toEqual([])
  })

  it("a meal while meal tracking is off isn't one of them", () => {
    const meals = { on: false, eating: { id: 7, kind: "lunch", date: "2026-11-21", start: "2026-11-21T12:40", end: null, nth: 1 } } as unknown as Schemas["MealsOut"]
    expect(runningNow(undefined, meals)).toEqual([])
  })
})
