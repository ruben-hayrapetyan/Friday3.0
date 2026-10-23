import { describe, expect, it } from "vitest"
import { dragged, movedSince } from "./drag"

const block = { start: 600, end: 690, grab: 20 } // 10:00–11:30, grabbed 20 minutes in

describe("dragging", () => {
  it("moves a block by where it was grabbed, snapped to 15 minutes, keeping its length", () => {
    expect(dragged({ kind: "move", ...block }, 727)).toEqual({ start: 705, end: 795 })
  })

  it("resizes from the bottom edge, never below 15 minutes", () => {
    expect(dragged({ kind: "resize", ...block }, 752)).toEqual({ start: 600, end: 750 })
    expect(dragged({ kind: "resize", ...block }, 560)).toEqual({ start: 600, end: 615 })
  })

  it("selects empty time either way from where it began", () => {
    const from = { kind: "select" as const, start: 600, end: 615, grab: 0 }
    expect(dragged(from, 668)).toEqual({ start: 600, end: 675 })
    expect(dragged(from, 541)).toEqual({ start: 540, end: 615 })
  })
})

describe("moved since you last looked", () => {
  it("names the items whose first block changed, with where it was", () => {
    const before = new Map([[1, "2026-10-20T15:00"], [2, "2026-10-20T16:00"]])
    const after = new Map([[1, "2026-10-21T09:00"], [2, "2026-10-20T16:00"], [3, "2026-10-22T10:00"]])
    expect([...movedSince(before, after)]).toEqual([[1, "2026-10-20T15:00"]])
  })
})
