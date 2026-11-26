// A dropdown's list over the page beside its button (15 Nov: the Projects page's tag menus were cut off by the card
// and the column they sat in): below it, above it when there's no room below, and never off the screen.
import { describe, expect, it } from "vitest"
import { placeList } from "./menuPlace"

const button = (top: number, left: number) => ({ top, bottom: top + 28, left, right: left + 120 })

describe("where a dropdown's list goes", () => {
  it("opens below its button, its right edge at the button's in the window's right half", () => {
    expect(placeList(button(100, 1000), 200, 150, 1440, 900)).toEqual({ top: 132, left: 920, maxHeight: 280 })
  })
  // 25 Nov, the user: the break dialog's Work menu, near the dialog's left, opened leftward over the sidebar
  it("in the window's left half its left edge is the button's", () => {
    expect(placeList(button(100, 400), 200, 150, 1440, 900)).toEqual({ top: 132, left: 400, maxHeight: 280 })
  })
  it("opens above when there's no room below", () => {
    const spot = placeList(button(820, 400), 200, 150, 1440, 900)
    expect(spot.top).toBe(820 - 4 - 150)
    expect(spot.top + 150).toBeLessThanOrEqual(820)
  })
  it("slides right rather than run off the left edge (a tag at the far left of a project's page)", () => {
    expect(placeList(button(100, 20), 200, 150, 390, 844).left).toBe(20) // at its button, on the screen
    expect(placeList(button(100, 300), 200, 150, 390, 844).left).toBe(390 - 12 - 200) // right half, past the edge: slid back on
  })
  it("a long list scrolls in the room there is, rather than running off the bottom", () => {
    const spot = placeList(button(400, 400), 200, 2000, 1440, 900)
    expect(spot.top).toBe(432)
    expect(spot.maxHeight).toBe(280)
    expect(placeList(button(100, 400), 200, 2000, 1440, 400).maxHeight).toBe(400 - 12 - 132) // less room than that
  })
  it("a long list above its button sits right above it, as tall as it's drawn (20 Nov)", () => {
    const spot = placeList(button(820, 400), 200, 2000, 1440, 900)
    expect(spot.maxHeight).toBe(280)
    expect(spot.top).toBe(820 - 4 - 280) // not 2000 above it
  })
})
