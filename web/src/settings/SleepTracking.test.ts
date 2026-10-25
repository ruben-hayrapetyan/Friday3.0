import { describe, expect, it } from "vitest"
import { daysSaid } from "./SleepTracking"

describe("learned sleep times in words", () => {
  it("names the usual groups of nights and mornings", () => {
    expect(daysSaid(["mon", "tue", "wed", "thu", "sun"], "bedtime")).toBe("Sunday to Thursday nights")
    expect(daysSaid(["fri", "sat"], "bedtime")).toBe("Friday and Saturday nights")
    expect(daysSaid(["mon", "tue", "wed", "thu", "fri"], "wake")).toBe("Weekday mornings")
    expect(daysSaid(["sat", "sun"], "wake")).toBe("Weekend mornings")
  })

  it("lists the days otherwise", () => {
    expect(daysSaid(["tue", "thu"], "wake")).toBe("Tue, Thu mornings")
  })
})
