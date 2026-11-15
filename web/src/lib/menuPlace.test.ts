// A dropdown's list over the page beside its button (15 Nov: the Projects page's tag menus were cut off by the card
// and the column they sat in): below it, above it when there's no room below, and never off the screen.
import { describe, expect, it } from "vitest"
import { placeList } from "./menuPlace"

const button = (top: number, left: number) => ({ top, bottom: top + 28, left, right: left + 120 })

describe("where a dropdown's list goes", () => {
  it("opens below its button, its right edge at the button's", () => {
    expect(placeList(button(100, 400), 200, 150, 1440, 900)).toEqual({ top: 132, left: 320, maxHeight: 900 - 12 - 132 })
  })
  it("opens above when there's no room below", () => {
    const spot = placeList(button(820, 400), 200, 150, 1440, 900)
    expect(spot.top).toBe(820 - 4 - 150)
    expect(spot.top + 150).toBeLessThanOrEqual(820)
  })
  it("slides right rather than run off the left edge (a tag at the far left of a project's page)", () => {
    expect(placeList(button(100, 20), 200, 150, 390, 844).left).toBe(12)
  })
  it("a long list scrolls in the room there is, rather than running off the bottom", () => {
    const spot = placeList(button(400, 400), 200, 2000, 1440, 900)
    expect(spot.top).toBe(432)
    expect(spot.maxHeight).toBe(900 - 12 - 432)
  })
})
