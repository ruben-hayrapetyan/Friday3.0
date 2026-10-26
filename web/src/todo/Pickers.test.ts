import { describe, expect, it } from "vitest"
import { everyN, repeatLabel } from "./Pickers"

describe("a repeat in words", () => {
  it("says every other week, every month and every few days", () => {
    expect(everyN("rrule:FREQ=WEEKLY;INTERVAL=2")).toBe("Every other week")
    expect(everyN("rrule:FREQ=WEEKLY;INTERVAL=4")).toBe("Every 4 weeks")
    expect(everyN("rrule:FREQ=MONTHLY")).toBe("Every month")
    expect(everyN("rrule:FREQ=DAILY;INTERVAL=3")).toBe("Every 3 days")
    expect(everyN("rrule:FREQ=WEEKLY;BYDAY=MO")).toBeNull()
    expect(repeatLabel({ every: "rrule:FREQ=MONTHLY", perWindow: null })).toBe("Every month")
  })
})
