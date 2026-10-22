import { describe, expect, it } from "vitest"
import { accentHex, oklch } from "./look"
import { AUTO_HUES, hueOf } from "./LookProvider"

describe("area colours", () => {
  it("reads a stored hue, the grey, an old hex colour's hue, or picks one by position", () => {
    expect(hueOf("265", 0)).toBe(265)
    expect(hueOf("n", 0)).toBe("n")
    expect(hueOf(null, 2)).toBe(AUTO_HUES[2])
    const blue = hueOf("#3b82f6", 0) as number
    expect(blue).toBeGreaterThan(250)
    expect(blue).toBeLessThan(270)
  })

  it("draws the design's default accent, hue 250 on dark", () => {
    expect(accentHex(250, false)).toBe(oklch(0.71, 0.14, 250))
    expect(oklch(1, 0, 0)).toBe("#ffffff")
  })
})
