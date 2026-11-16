// The screen tests' Friday runs as Thursday 12 November 2026 at 2pm (server.ts shiftToThursday): the minutes to add.
// Its week mattered as much as its hour: run as each week's Thursday, the sample's homework moved on every Monday and the
// tests naming last week's failed (16 Nov).
import { describe, expect, it } from "vitest"
import { SCREEN_DAY, SCREEN_HOUR, shiftToThursday } from "./server"

const at = (local: string) => new Date(local) // the machine's zone, as the tests run
const H = 60
const D = 24 * H

describe("the screen tests' Thursday afternoon", () => {
  it("is 2pm on Thursday 12 November 2026, whenever they run", () => {
    expect([SCREEN_DAY, SCREEN_HOUR]).toEqual(["2026-11-12", 14])
    expect(shiftToThursday(at("2026-11-12T14:00"))).toBe(0)
    expect(shiftToThursday(at("2026-11-09T12:00"))).toBe(3 * D + 2 * H) // that Monday noon
    expect(shiftToThursday(at("2026-11-13T22:40"))).toBe(-(D + 8 * H + 40)) // that Friday night
  })

  it("is the same Thursday the week after, and months on (it was each week's Thursday, and failed on 16 Nov)", () => {
    expect(shiftToThursday(at("2026-11-16T12:00"))).toBe(-(4 * D - 2 * H)) // the next Monday: back to the 12th
    const then = (now: Date) => new Date(now.getTime() + shiftToThursday(now) * 60_000)
    for (const now of [at("2026-11-16T09:00"), at("2026-11-26T23:30"), at("2027-03-01T08:15")]) {
      const t = then(now)
      expect([t.getFullYear(), t.getMonth() + 1, t.getDate(), t.getHours(), t.getMinutes()]).toEqual([2026, 11, 12, SCREEN_HOUR, 0])
    }
  })
})
