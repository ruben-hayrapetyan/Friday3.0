// Settings → Schedule's pickers: the half-hours offered, with a time saved off them shown among them; and the number
// boxes, saved only when they read as a number in range.
import { describe, expect, it } from "vitest"
import { heldNumber } from "./Held"
import { timesWith } from "./Schedule"

describe("the day's start and bedtime", () => {
  it("offers the half-hours, and a time saved between them in its place", () => {
    expect(timesWith(5, 11, "07:00")).toHaveLength(13)
    expect(timesWith(5, 11, "07:15").slice(4, 7)).toEqual(["07:00", "07:15", "07:30"])
    // past midnight sorts after the evening
    expect(timesWith(21, 26, "02:30").slice(-2)).toEqual(["02:00", "02:30"])
    expect(timesWith(21, 26, "20:45")[0]).toBe("20:45")
  })
})

describe("a number box", () => {
  it("saves only a number in range: empty is not 0", () => {
    expect(heldNumber("", 0, 16)).toBeNull()
    expect(heldNumber("  ", 0, 16)).toBeNull()
    expect(heldNumber("108", 0, 16)).toBeNull()
    expect(heldNumber("8", 0, 16)).toBe(8)
    expect(heldNumber("0", 0, 16)).toBe(0)
    expect(heldNumber("6.5", 0, 16)).toBe(6.5)
  })
})
