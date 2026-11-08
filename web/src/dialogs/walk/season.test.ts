import { describe, expect, it } from "vitest"
import { chosenSeason, DAYLIGHT, FAR, hasFallenLeaves, LEAVES, seasonOf, SEASONS, snows } from "./season"
import { sunAt, useDaylight } from "./sky"

describe("the walk in the season outside (8 Nov)", () => {
  it("goes by the month, as the north has it", () => {
    const on = (m: number) => seasonOf(new Date(2026, m, 15))
    expect([0, 1, 11].map(on)).toEqual(["winter", "winter", "winter"])
    expect([2, 3, 4].map(on)).toEqual(["spring", "spring", "spring"])
    expect([5, 6, 7].map(on)).toEqual(["summer", "summer", "summer"])
    expect([8, 9, 10].map(on)).toEqual(["fall", "fall", "fall"])
    expect(seasonOf(new Date(2026, 10, 30, 23, 59))).toBe("fall")
    expect(seasonOf(new Date(2026, 11, 1, 0, 0))).toBe("winter")
  })

  it("draws another when the address asks, and today's otherwise", () => {
    const today = new Date(2026, 10, 8)
    expect(chosenSeason("?season=winter", today)).toBe("winter")
    expect(chosenSeason("?season=monsoon", today)).toBe("fall")
    expect(chosenSeason("", today)).toBe("fall")
  })

  it("leaves maples and birches bare in winter, an oak a few dry leaves, and every tree leafy otherwise", () => {
    expect(LEAVES.winter.maple).toEqual([])
    expect(LEAVES.winter.birch).toEqual([])
    expect(LEAVES.winter.oak.length).toBeGreaterThan(0)
    for (const season of ["spring", "summer", "fall"] as const) for (const kind of ["maple", "birch", "oak"] as const) expect(LEAVES[season][kind].length).toBeGreaterThan(3)
  })

  it("has leaves on the ground only in fall and snow only in winter", () => {
    expect(SEASONS.filter(hasFallenLeaves)).toEqual(["fall"])
    expect(SEASONS.filter(snows)).toEqual(["winter"])
  })

  it("gives winter snowy hills and summer green ones", () => {
    const light = (hex: number) => ((hex >> 16) & 255) + ((hex >> 8) & 255) + (hex & 255)
    expect(light(FAR.winter.hills)).toBeGreaterThan(600)
    expect((FAR.summer.hills >> 8) & 255).toBeGreaterThan((FAR.summer.hills >> 16) & 255) // more green than red
  })

  it("makes winter's days short and low and summer's long and high", () => {
    expect(DAYLIGHT.winter.set - DAYLIGHT.winter.rise).toBeLessThan(DAYLIGHT.summer.set - DAYLIGHT.summer.rise)
    useDaylight("winter")
    const fivePm = sunAt(17 * 60).elevation
    const winterNoon = sunAt(12 * 60).elevation
    useDaylight("summer")
    expect(fivePm).toBeLessThan(0) // dark by five in December
    expect(sunAt(17 * 60).elevation).toBeGreaterThan(0)
    expect(sunAt(12 * 60).elevation).toBeGreaterThan(winterNoon)
    useDaylight("fall")
  })
})
