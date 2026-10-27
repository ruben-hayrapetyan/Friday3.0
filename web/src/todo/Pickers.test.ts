import { describe, expect, it } from "vitest"
import { everyN, repeatLabel, stepLength } from "./Pickers"

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

describe("− and + on a length", () => {
  it("step by a quarter hour, half an hour or an hour as the length grows, landing on the step", () => {
    const up = (m: number) => stepLength(m, true)
    const down = (m: number) => stepLength(m, false)
    expect([up(60), up(105), up(120), up(150), up(300), up(315), up(600)]).toEqual([75, 120, 150, 180, 360, 360, 660])
    expect([down(75), down(120), down(150), down(300), down(315), down(360), down(30), down(15)]).toEqual([60, 105, 120, 270, 300, 300, 15, 15])
  })

  it("come back to where they started, from a length on the step", () => {
    for (const m of [15, 45, 120, 150, 300, 420, 900]) expect(stepLength(stepLength(m, true), false)).toBe(m)
  })
})
