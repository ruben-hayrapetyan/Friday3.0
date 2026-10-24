import { describe, expect, it } from "vitest"
import { choiceOf, fromChoice, saying } from "./calendarChoice"

describe("a calendar's one choice", () => {
  it("round-trips the three choices", () => {
    for (const c of ["around", "over", "hidden"] as const) expect(choiceOf(fromChoice(c).shown, fromChoice(c).busy)).toBe(c)
  })
  it("hides from planning too, and says so when a hidden one is still kept clear", () => {
    expect(fromChoice("hidden")).toEqual({ shown: false, busy: false })
    expect(choiceOf(false, true)).toBe("hidden")
    expect(saying(false, true)).toMatch(/still keeps work off/)
    expect(saying(true, false)).toMatch(/dashed/)
  })
})
