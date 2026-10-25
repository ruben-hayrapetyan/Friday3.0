import { describe, expect, it } from "vitest"
import { along, usual } from "./Sleep"

describe("a night on the timeline", () => {
  it("runs from 8pm to the next 1pm", () => {
    expect(along("2026-10-24", "2026-10-24T20:00")).toBe(0)
    expect(along("2026-10-24", "2026-10-25T13:00")).toBe(100)
    expect(Math.round(along("2026-10-24", "2026-10-25T04:30"))).toBe(50)
    expect(along("2026-10-24", "2026-10-24T18:00")).toBe(0) // clamped
  })

  it("takes the usual bedtime across midnight, and the usual wake time", () => {
    expect(usual(["2026-10-24T23:00", "2026-10-26T01:00", "2026-10-26T00:10"], true)).toBe("00:15")
    expect(usual(["2026-10-25T08:10", "2026-10-26T07:50", "2026-10-27T09:00"], false)).toBe("08:15")
    expect(usual([], false)).toBeNull()
  })
})
