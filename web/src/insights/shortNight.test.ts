// 23 Nov, the user: "sleep durations that were really short were gray and vice versa": a night was yellow when an hour
// under its own plan, which moved from 6h30 to 8h15. Now one number for every night: an hour or more under your usual.
import { describe, expect, it } from "vitest"
import { shortNight } from "./Sleep"

describe("a short night", () => {
  it("is an hour or more under your usual night, whatever that night's plan was", () => {
    expect(shortNight(6 * 60, 8 * 60)).toBe(true) // planned 6h30 that night: gray before
    expect(shortNight(7 * 60, 8 * 60)).toBe(true) // exactly an hour under
    expect(shortNight(7 * 60 + 15, 8 * 60)).toBe(false) // planned 8h15 that night: yellow before
    expect(shortNight(null, 8 * 60)).toBe(false)
    expect(shortNight(5 * 60, null)).toBe(false)
  })
})
