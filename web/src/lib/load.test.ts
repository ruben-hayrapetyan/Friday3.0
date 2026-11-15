import { describe, expect, it } from "vitest"
import { hoursSaid, overSentence, weekLabel } from "./load"
import { weekday } from "./format"

describe("a week over your usual", () => {
  it("says what's planned, how far past your usual, and that nothing will be late when nothing will", () => {
    expect(overSentence(weekLabel("2026-11-09", weekday), 16, 15, 0)).toBe("Mon 9’s week: 16 h planned, 1 h past your usual 15 h. Nothing will be late.")
  })

  it("says how many things will be late when some will", () => {
    expect(overSentence("Thursday", 9.5, 8, 1)).toBe("Thursday: 9.5 h planned, 1.5 h past your usual 8 h. 1 thing will be late.")
    expect(overSentence("Thursday", 9, 8, 3)).toMatch(/3 things will be late\.$/)
  })

  it("says hours to the tenth, without a trailing .0", () => {
    expect([hoursSaid(16), hoursSaid(0.96), hoursSaid(15.64)]).toEqual(["16 h", "1 h", "15.6 h"])
    expect(overSentence("Thursday", 16.44, 15.56, 0)).toContain("16.4 h planned, 0.8 h past your usual 15.6 h")
  })
})
