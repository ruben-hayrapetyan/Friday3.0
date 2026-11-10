// The calendar's title for its days (10 Nov: on a phone "Thu 12 Nov" showed as "Thu …").
import { describe, expect, it } from "vitest"
import { rangeTitle } from "./PlanPage"

describe("the calendar's title", () => {
  it("on a phone is the month alone, the days saying their dates", () => {
    expect(rangeTitle("2026-11-12", 1, true, true)).toBe("Nov")
    expect(rangeTitle("2026-11-29", 3, true, true)).toBe("Nov–Dec")
    expect(rangeTitle("2026-11-09", 7, true, true)).toBe("Nov")
  })
  it("elsewhere is as before", () => {
    expect(rangeTitle("2026-11-12", 1)).toBe("Thursday 12 November")
    expect(rangeTitle("2026-11-12", 1, true)).toBe("Thu 12 Nov")
    expect(rangeTitle("2026-11-09", 7)).toBe("9 – 15 November")
    expect(rangeTitle("2026-11-01", "month", false, true)).toBe("November 2026")
  })
})
