import { describe, expect, it } from "vitest"
import { slideInto } from "./onScreen"

describe("a menu kept on a phone's screen (390px)", () => {
  it("slides left by what runs off the right: a day's deadlines, 412px on a 388px screen", () => {
    expect(slideInto(132, 412, 388)).toBe(-36)
  })
  it("slides right by what runs off the left: the Show menu", () => expect(slideInto(-60, 240, 388)).toBe(72))
  it("stays where it is when it fits", () => expect(slideInto(40, 320, 388)).toBe(0))
  it("never slides past the other edge", () => {
    expect(slideInto(20, 600, 388)).toBe(-8)
    expect(slideInto(-60, 380, 388)).toBe(0) // wider than the room: the right edge stays
  })
})
