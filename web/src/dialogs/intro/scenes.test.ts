import { describe, expect, it } from "vitest"
import type { Schemas } from "@/api/client"
import { friday, textWidth, words, WALK } from "./art"
import { skyAt } from "./draw"
import { finishAt, focusCycle, freeSpan, lapse, minutesOf, SIGNS } from "./scenes"

const A: Schemas["SetupInput"] = {
  wake: "07:30",
  bedtime: "23:30",
  weekend_wake: "09:00",
  weekend_bedtime: "00:30",
  normal_hours: 6,
  most_hours: 10,
  focus_hours: 1.5,
  evening_free: 2,
  evening_from: "18:00",
  weekend_free: 4,
  finish_early_days: 1,
  brief: true,
  calendars: [],
}

describe("Friday's sprite", () => {
  it("is 16 across every row, whatever its face and legs", () => {
    for (const face of ["open", "blink", "happy", "yawn", "look"] as const)
      for (const legs of [...WALK, "none"] as const) {
        const art = friday(face, legs)
        expect(art).toHaveLength(17)
        expect(new Set(art.map((r) => r.length))).toEqual(new Set([16]))
      }
  })

  it("writes the world's signs in a 3 × 5 font, 4 pixels a letter", () => {
    const sign = words("MON")
    expect(sign).toHaveLength(5)
    expect(sign[0]).toHaveLength(textWidth("MON"))
    expect(textWidth("5PM")).toBe(11)
  })
})

describe("the week Friday lives through", () => {
  it("finishes the essay at the sign of the day you'd be done", () => {
    expect([0, 1, 2, 3, 9].map(finishAt)).toEqual([SIGNS[4], SIGNS[3], SIGNS[2], SIGNS[1], SIGNS[0]])
  })

  it("keeps the part of an evening, or of a weekend day, you said is yours", () => {
    expect(freeSpan(A, false)).toEqual([18 * 60, 20 * 60])
    expect(freeSpan({ ...A, evening_free: 5 }, false)).toEqual([18 * 60, 23 * 60 + 30]) // all of it: to bed
    expect(freeSpan({ ...A, evening_free: 0 }, false)).toBeNull()
    expect(freeSpan(A, true)).toEqual([24 * 60 + 30 - 4 * 60, 24 * 60 + 30]) // the last four hours before a 12:30am bed
    expect(freeSpan({ ...A, weekend_free: 13 }, true)).toEqual([9 * 60, 24 * 60 + 30])
  })

  it("plays a day in fast forward and holds at its end; with reduced motion, just its end", () => {
    expect(lapse(0, 600, 1200, false)).toBe(600)
    expect(lapse(4000, 600, 1200, false)).toBe(900)
    expect(lapse(8500, 600, 1200, false)).toBe(1200)
    expect(lapse(0, 600, 1200, true)).toBe(1200)
  })

  it("works a sitting as long as your focus, then takes a break, and the clock keeps up", () => {
    const sitting = 1.5 * 1300
    expect(focusCycle(1.5, sitting / 2)).toMatchObject({ working: true, share: 0.5, minutes: 45 })
    expect(focusCycle(1.5, sitting + 10).working).toBe(false)
    expect(focusCycle(1.5, sitting + 1500 + 1).minutes).toBeGreaterThanOrEqual(105) // 1.5h and a quarter-hour break
  })

  it("paints the sky by the hour: night, dawn, day, dusk", () => {
    expect(skyAt(minutesOf("02:00"))[0]).toBe(skyAt(minutesOf("23:00"))[0])
    expect(skyAt(minutesOf("06:00"))).not.toEqual(skyAt(minutesOf("12:00")))
    expect(skyAt(minutesOf("19:30"))).not.toEqual(skyAt(minutesOf("12:00")))
  })
})
