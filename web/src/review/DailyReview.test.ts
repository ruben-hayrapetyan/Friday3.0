import { describe, expect, it } from "vitest"
import { spans } from "./DailyReview"

describe("when a task's time was, in the Review's rows", () => {
  it("drops the first am or pm when both ends share it", () => {
    expect(spans({ spans: [["2026-10-28T08:00", "2026-10-28T08:45"]] })).toBe("8–8:45am")
  })
  it("keeps both when the time crosses noon", () => {
    expect(spans({ spans: [["2026-10-28T11:30", "2026-10-28T12:30"]] })).toBe("11:30am–12:30pm")
  })
  it("lists each block", () => {
    const two = spans({ spans: [["2026-10-28T08:00", "2026-10-28T08:45"], ["2026-10-28T22:15", "2026-10-28T23:30"]] })
    expect(two).toBe("8–8:45am, 10:15–11:30pm")
  })
})
