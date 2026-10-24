import { describe, expect, it } from "vitest"
import { readRelative } from "./Pickers"

describe("typed due dates the grammar leaves to personal's reader", () => {
  const now = "2026-10-24T14:10"
  it("reads in so many minutes, hours, days or weeks, and the end of today", () => {
    expect(readRelative("in 2 hours", now)).toBe("2026-10-24T16:10")
    expect(readRelative("in 30 min", now)).toBe("2026-10-24T14:40")
    expect(readRelative("in 3 days", now)).toBe("2026-10-27T23:59")
    expect(readRelative("in a week", now)).toBe("2026-10-31T23:59")
    expect(readRelative("eod", now)).toBe("2026-10-24T23:59")
    expect(readRelative("tonight", now)).toBe("2026-10-24T23:59")
  })
  it("leaves the rest to the grammar", () => {
    expect(readRelative("fri 5pm", now)).toBeNull()
    expect(readRelative("in a bit", now)).toBeNull()
  })
})
