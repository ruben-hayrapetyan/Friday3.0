// Friday Notes-3 (26 Nov, a Light break day): the brief said "14:15–14:45" and "12:45–13:45" for things Friday
// doesn't put at a time on a break.
import { describe, expect, it } from "vitest"
import { rockWhen } from "./rockWhen"

const block = { start: "2026-11-26T14:15", end: "2026-11-26T14:45" }

describe("what the brief says beside one of today's things (black box)", () => {
  it("names no time on a break day, though the plan holds one", () => {
    expect(rockWhen(true, {}, block)).toBe("")
    expect(rockWhen(true, { ticked: false }, block)).toBe("")
  })

  it("says done for a thing ticked off a break day's list", () => {
    expect(rockWhen(true, { ticked: true }, block)).toBe("done")
    expect(rockWhen(true, { ticked: true }, undefined)).toBe("done")
  })

  it("says nothing on a break day for a thing with no time left today either", () => {
    expect(rockWhen(true, {}, undefined)).toBe("")
  })

  it("names the next time on an ordinary day", () => {
    expect(rockWhen(false, {}, block)).toMatch(/^2:15\s?pm–2:45\s?pm$|^14:15–14:45$/)
  })

  it("says not today on an ordinary day for a thing not planned today", () => {
    expect(rockWhen(false, {}, undefined)).toBe("not today")
  })
})
