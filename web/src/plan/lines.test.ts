import { describe, expect, it } from "vitest"
import { detailLines, titleLines } from "./lines"
import { PX } from "./Pieces"

const px = (minutes: number) => minutes * PX - 2 // as Pieces draws a box

describe("lines in a box on the calendar", () => {
  it("gives a two-hour event's title several lines and still leaves its time and location room to wrap", () => {
    expect(titleLines(px(120))).toBe(4)
    // a one-line title leaves four lines for a long location: never cut to one
    expect(detailLines(px(120), 1)).toBe(4)
    expect(detailLines(px(120), 3)).toBe(2)
  })

  it("keeps an hour's box, and 45 minutes', to a line of title over a line of time, as before", () => {
    expect([titleLines(px(60)), detailLines(px(60), 1)]).toEqual([1, 1])
    expect([titleLines(px(90)), detailLines(px(90), 1)]).toEqual([3, 3])
    expect([titleLines(px(45)), detailLines(px(45), 1)]).toEqual([1, 1])
  })

  it("takes the rows under it (moved from, in an event) off the title's lines", () => {
    expect(titleLines(px(120), 1)).toBe(3)
    expect(detailLines(px(120), 1, 1)).toBe(3)
  })
})
