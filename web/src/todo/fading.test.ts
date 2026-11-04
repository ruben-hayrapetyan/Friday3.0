// "Fades once late" said on a task's page (3 Nov).
import { describe, expect, it } from "vitest"
import { fadingSaid, left } from "./fading"

describe("glass box", () => {
  it("halves every half-life", () => {
    expect(left(0, 3)).toBe(1)
    expect(left(3, 3)).toBeCloseTo(0.5)
    expect(left(6, 3)).toBeCloseTo(0.25)
  })
  it("early is on time", () => {
    expect(left(-2, 3)).toBe(1)
  })
  it("says the half-life and what's left a week late", () => {
    expect(fadingSaid("Reading", 3)).toBe("As for all readings: planned late if it can't be on time, mattering half as much for every 3 days late (a week late, 20%), so work still on time comes first.")
    expect(fadingSaid(null, 1)).toContain("every day late (a week late, 1%)")
  })
})

describe("black box", () => {
  it("never grows with time, and stays between 0 and 1", () => {
    for (const h of [0.5, 1, 3, 7]) {
      let was = 1
      for (let d = 0; d <= 30; d += 0.5) {
        const now = left(d, h)
        expect(now).toBeLessThanOrEqual(was)
        expect(now).toBeGreaterThan(0)
        was = now
      }
    }
  })
  it("matches the server's maths (settings.py FadingLate.factor: 0.5 ** (minutes / (half_life_days * 1440)))", () => {
    const server = (minutes: number, h: number) => 0.5 ** (Math.max(0, minutes) / (h * 1440))
    for (const d of [0, 1, 2.5, 7, 14]) expect(left(d, 3)).toBeCloseTo(server(d * 1440, 3), 12)
  })
})
