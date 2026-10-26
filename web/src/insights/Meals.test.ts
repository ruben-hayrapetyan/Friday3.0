import { describe, expect, it } from "vitest"
import { mealAlong, skipSaid } from "./Meals"

describe("a day of meals on the timeline", () => {
  it("runs from 6am to 2am the next day", () => {
    expect(mealAlong("2026-10-24", "2026-10-24T06:00")).toBe(0)
    expect(mealAlong("2026-10-24", "2026-10-25T02:00")).toBe(100)
    expect(mealAlong("2026-10-24", "2026-10-24T16:00")).toBe(50)
    expect(mealAlong("2026-10-24", "2026-10-24T05:00")).toBe(0) // clamped
  })

  it("says how often a meal is skipped in words", () => {
    expect(skipSaid(null)).toBe("")
    expect(skipSaid(0)).toBe("never skipped")
    expect(skipSaid(0.25)).toBe("skipped about 1 day in 4")
    expect(skipSaid(0.6)).toBe("skipped 60% of days")
    expect(skipSaid(1)).toBe("always skipped")
  })
})
