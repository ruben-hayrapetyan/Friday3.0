import { describe, expect, it } from "vitest"
import { everyN, readRelative, repeatLabel, stepLength } from "./Pickers"

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

describe("plain days are read at once, as the server reads them", () => {
  // Wednesday 28 Oct 2026, 11am. The server's readings of that morning: a day is its next one, today included.
  const now = "2026-10-28T11:00"
  const at = (text: string) => readRelative(text, now)
  it("today, tomorrow and their short forms", () => {
    expect([at("today"), at("Today "), at("tonight"), at("eod")]).toEqual(Array(4).fill("2026-10-28T23:59"))
    expect([at("tomorrow"), at("tmrw"), at("tmr"), at("tom")]).toEqual(Array(4).fill("2026-10-29T23:59"))
  })
  it("a weekday is its next one, today's own included", () => {
    expect(at("wed")).toBe("2026-10-28T23:59")
    expect(at("wednesday")).toBe("2026-10-28T23:59")
    expect(at("thu")).toBe("2026-10-29T23:59")
    expect(at("thurs")).toBe("2026-10-29T23:59")
    expect(at("fri")).toBe("2026-10-30T23:59")
    expect(at("this fri")).toBe("2026-10-30T23:59")
    expect(at("sat")).toBe("2026-10-31T23:59")
    expect(at("sun")).toBe("2026-11-01T23:59")
    expect(at("mon")).toBe("2026-11-02T23:59")
    expect(at("Tuesday")).toBe("2026-11-03T23:59")
  })
  it("leaves the rest to the server", () => {
    for (const text of ["next fri", "fri 5pm", "today 5pm", "oct 30", "friday-ish", "monk"]) expect(at(text)).toBeNull()
  })
})
