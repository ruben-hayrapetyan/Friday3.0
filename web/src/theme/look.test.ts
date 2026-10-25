import { describe, expect, it } from "vitest"
import { accentHex, oklch } from "./look"
import { PIGMENTS, pigment } from "@/lib/pigments"
import { AUTO_PAINTS, hueOf, KIND_PAINT, paintOf, SCHOOLWORK } from "./LookProvider"

describe("area colours", () => {
  it("reads a pigment, a stored hue, the grey, an old hex colour's hue, or deals Chroma's paints by position", () => {
    expect(hueOf("green", 0)).toBe("green")
    expect(paintOf("green", false)).toBe(pigment("green", false))
    expect(hueOf("265", 0)).toBe(265)
    expect(hueOf("n", 0)).toBe("n")
    expect(hueOf(null, 2)).toBe(AUTO_PAINTS[2])
    const blue = hueOf("#3b82f6", 0) as number
    expect(blue).toBeGreaterThan(250)
    expect(blue).toBeLessThan(270)
  })

  it("paints schoolwork green and meals yellow, gives the other kinds and tags distinct paints, and keeps red", () => {
    const ids = PIGMENTS.map((p) => p.id)
    expect(new Set(AUTO_PAINTS).size).toBe(AUTO_PAINTS.length)
    expect(SCHOOLWORK.map((k) => KIND_PAINT[k])).toEqual(["green", "green", "green", "green"])
    expect(KIND_PAINT.Routine).toBe("yellow")
    const rest = Object.entries(KIND_PAINT).filter(([k]) => !SCHOOLWORK.includes(k)).map(([, p]) => p)
    expect(new Set(rest).size).toBe(rest.length)
    expect(rest).not.toContain("green")
    for (const paint of [...AUTO_PAINTS, ...Object.values(KIND_PAINT)]) expect(ids).toContain(paint)
    expect([...AUTO_PAINTS, ...Object.values(KIND_PAINT)]).not.toContain("red")
  })

  it("writes the chrome in ink: navy by default, dark on paper and light on the dark page", () => {
    expect(accentHex(255, true)).toBe(oklch(0.34, 0.075, 255))
    expect(accentHex(255, false)).toBe(oklch(0.76, 0.075, 255))
    expect(oklch(1, 0, 0)).toBe("#ffffff")
  })
})
