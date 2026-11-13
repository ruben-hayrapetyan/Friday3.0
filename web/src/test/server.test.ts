// The screen tests' Friday runs as a Thursday (server.ts shiftToThursday): the days to add, by the planning day.
import { describe, expect, it } from "vitest"
import { shiftToThursday } from "./server"

const at = (local: string) => new Date(local) // the machine's zone, as the tests run

describe("the screen tests' Thursday", () => {
  it("is this planning week's Thursday, earlier or later in the week", () => {
    expect(shiftToThursday(at("2026-11-09T12:00"))).toBe(3) // Monday
    expect(shiftToThursday(at("2026-11-12T12:00"))).toBe(0) // Thursday: no shift
    expect(shiftToThursday(at("2026-11-13T14:30"))).toBe(-1) // Friday
    expect(shiftToThursday(at("2026-11-15T23:00"))).toBe(-3) // Sunday is the week's last day
  })

  it("counts the small hours with the day before, as Friday's days start at 4am", () => {
    expect(shiftToThursday(at("2026-11-13T01:30"))).toBe(0) // 1:30am Friday is still Thursday
    expect(shiftToThursday(at("2026-11-16T03:59"))).toBe(-3) // 3:59am Monday is still Sunday
    expect(shiftToThursday(at("2026-11-16T04:00"))).toBe(3)
  })
})
