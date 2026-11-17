// A length box is at least as wide as its hint (17 Nov: an ongoing project's "e.g. 12h, 2.5 hours" was cut off).
import { describe, expect, it } from "vitest"
import { boxWidth } from "./Pickers"

describe("a length box's width", () => {
  it("fits its hint, a mono character a ch, beside its padding", () => {
    expect(boxWidth(150, "e.g. 12h, 2.5 hours")).toBe("max(150px, calc(22ch + 18px))")
  })
  it("keeps the width asked for when the hint is short", () => {
    expect(boxWidth(110, "")).toBe("max(110px, calc(3ch + 18px))")
  })
})
