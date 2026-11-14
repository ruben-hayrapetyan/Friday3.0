// The screen tests' Friday runs as this week's Thursday at 2pm (server.ts shiftToThursday): the minutes to add, by the
// planning day. A day alone wasn't enough: the Inbox's late work read differently at 10:30pm than at 2pm (13 Nov).
import { describe, expect, it } from "vitest"
import { SCREEN_HOUR, shiftToThursday } from "./server"

const at = (local: string) => new Date(local) // the machine's zone, as the tests run
const H = 60
const D = 24 * H

describe("the screen tests' Thursday afternoon", () => {
  it("is 2pm on this planning week's Thursday, earlier or later in the week", () => {
    expect(SCREEN_HOUR).toBe(14)
    expect(shiftToThursday(at("2026-11-09T12:00"))).toBe(3 * D + 2 * H) // Monday noon
    expect(shiftToThursday(at("2026-11-12T14:00"))).toBe(0) // Thursday 2pm: no shift
    expect(shiftToThursday(at("2026-11-13T22:40"))).toBe(-(D + 8 * H + 40)) // Friday night
    expect(shiftToThursday(at("2026-11-15T23:00"))).toBe(-(3 * D + 9 * H)) // Sunday is the week's last day
  })

  it("counts the small hours with the day before, as Friday's days start at 4am", () => {
    expect(shiftToThursday(at("2026-11-13T01:30"))).toBe(-(11 * H + 30)) // 1:30am Friday is still Thursday
    expect(shiftToThursday(at("2026-11-16T03:59"))).toBe(-(3 * D + 13 * H + 59)) // 3:59am Monday is still Sunday
    expect(shiftToThursday(at("2026-11-16T04:00"))).toBe(3 * D + 10 * H)
  })

  it("lands at 2pm on a Thursday from any minute of the week", () => {
    for (let m = 0; m < 7 * D; m += 37) {
      const now = new Date(at("2026-11-09T00:00").getTime() + m * 60_000)
      const then = new Date(now.getTime() + shiftToThursday(now) * 60_000)
      expect([then.getDay(), then.getHours(), then.getMinutes()]).toEqual([4, SCREEN_HOUR, 0])
    }
  })
})
