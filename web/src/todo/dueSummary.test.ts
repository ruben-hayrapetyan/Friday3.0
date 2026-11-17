// A due date said in words: a past one says how long ago, never "(in -1 days)" (17 Nov: an overdue assignment's
// detail read "Due Wed 11 Nov, 11:59pm (in -1 days)").
// @vitest-environment happy-dom
import { describe, expect, it } from "vitest"
import { dueSummary } from "./Pickers"

describe("dueSummary", () => {
  it("says a past due as how long ago", () => {
    expect(dueSummary("2026-11-11T23:59", "2026-11-12")).toBe("Due Wed 11 Nov, 11:59pm (yesterday)")
    expect(dueSummary("2026-11-09T17:00", "2026-11-12")).toBe("Due Mon 9 Nov, 5pm (3 days ago)")
  })
  it("says today, tomorrow and days to come as before", () => {
    expect(dueSummary("2026-11-12T23:59", "2026-11-12")).toBe("Due Thu 12 Nov, 11:59pm (today)")
    expect(dueSummary("2026-11-13T23:59", "2026-11-12")).toBe("Due Fri 13 Nov, 11:59pm (tomorrow)")
    expect(dueSummary("2026-11-19T23:59", "2026-11-12")).toBe("Due Thu 19 Nov, 11:59pm (in 7 days)")
  })
})
