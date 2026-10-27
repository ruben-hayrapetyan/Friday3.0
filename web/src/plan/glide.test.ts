import { describe, expect, it } from "vitest"
import { familyOf, offset, pairUp } from "./glide"

const at = (x: number, y: number) => ({ x, y, w: 180, h: 48 })

describe("replanning in motion", () => {
  it("knows an item's blocks as one family, whatever their start", () => {
    expect(familyOf("T4@2026-10-20T09:00")).toBe("T4")
    expect(familyOf("T4@2026-10-21T14:00")).toBe("T4")
    expect(familyOf("F9")).toBe("F9")
    expect(familyOf("S5@2026-10-20T09:00")).toBe("S5@2026-10-20T09:00")
  })

  it("pairs each block with the nearest of where the item's blocks were", () => {
    // Tue 9am and Thu 2pm before; a block added Mon morning, Tue's moved to 10am, Thu's unchanged.
    const was = [at(200, 100), at(600, 400)]
    const now = [at(0, 80), at(200, 148), at(600, 400)]
    expect(pairUp(was, now)).toEqual([null, 0, 1]) // the new one fades in; nothing slides a day along
  })

  it("lets a block go when there are fewer now", () => {
    expect(pairUp([at(0, 0), at(400, 0)], [at(390, 10)])).toEqual([1])
    expect(pairUp([], [at(0, 0)])).toEqual([null])
  })

  it("slides only what moved or changed size, from where it was", () => {
    const was = { x: 100, y: 40, w: 80, h: 48 }
    expect(offset(was, { ...was })).toBeNull()
    expect(offset(was, { ...was, y: 40.4 })).toBeNull() // under a pixel
    expect(offset(was, { x: 200, y: 140, w: 40, h: 48 })).toEqual({ x: -100, y: -100, w: 80, h: 48 })
  })
})
