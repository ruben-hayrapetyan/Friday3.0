import { describe, expect, it } from "vitest"
import { dayOf, daysIn, movedRule, onDays, repeatChoices, sayRepeat, splitCount, withCount } from "./repeats"

const FRIDAY = "2026-10-30T18:15"

describe("how an event repeats", () => {
  it("offers the choices with the event's own day", () => {
    expect(dayOf(FRIDAY)).toBe(4)
    expect(repeatChoices(FRIDAY).map((c) => c.label)).toEqual([
      "Doesn't repeat",
      "Every day",
      "Every week on Friday",
      "Every other Friday",
      "Every weekday (Mon–Fri)",
      "Every month on the 30th",
    ])
    expect(repeatChoices("2026-11-01T10:00").at(-1)?.label).toBe("Every month on the 1st")
    expect(repeatChoices("2026-11-22T10:00").at(-1)?.label).toBe("Every month on the 22nd")
    expect(repeatChoices("2026-11-12T10:00").at(-1)?.label).toBe("Every month on the 12th")
  })

  it("says a rule in words, with how many times", () => {
    expect(sayRepeat(null, FRIDAY)).toBe("Doesn't repeat")
    expect(sayRepeat("rrule:FREQ=WEEKLY;BYDAY=FR;COUNT=10", FRIDAY)).toBe("Every week on Friday, 10 times")
    expect(sayRepeat("rrule:FREQ=WEEKLY;BYDAY=TU,TH", FRIDAY)).toBe("Every Tue, Thu")
    expect(sayRepeat("rrule:FREQ=WEEKLY", FRIDAY)).toBe("Every week on Friday") // as the old list made them
  })

  it("builds and reads chosen days and an end", () => {
    expect(onDays([3, 1])).toBe("rrule:FREQ=WEEKLY;BYDAY=TU,TH")
    expect(daysIn("rrule:FREQ=WEEKLY;BYDAY=TU,TH;COUNT=5")).toEqual([1, 3])
    expect(daysIn("rrule:FREQ=DAILY")).toBeNull()
    expect(withCount("rrule:FREQ=DAILY", 5)).toBe("rrule:FREQ=DAILY;COUNT=5")
    expect(withCount("rrule:FREQ=DAILY", null)).toBe("rrule:FREQ=DAILY")
    expect(splitCount("rrule:FREQ=DAILY;COUNT=5")).toEqual({ base: "rrule:FREQ=DAILY", count: 5 })
  })

  it("moves a weekly rule with the event's day, and leaves others", () => {
    expect(movedRule("rrule:FREQ=WEEKLY;BYDAY=FR", FRIDAY, "2026-10-31T18:15")).toBe("rrule:FREQ=WEEKLY;BYDAY=SA")
    expect(movedRule("rrule:FREQ=WEEKLY;INTERVAL=2;BYDAY=FR;COUNT=4", FRIDAY, "2026-11-02T18:15")).toBe("rrule:FREQ=WEEKLY;INTERVAL=2;BYDAY=MO;COUNT=4")
    expect(movedRule("rrule:FREQ=WEEKLY;BYDAY=TU,TH", FRIDAY, "2026-10-31T18:15")).toBe("rrule:FREQ=WEEKLY;BYDAY=TU,TH")
    expect(movedRule(null, FRIDAY, "2026-10-31T18:15")).toBeNull()
  })
})
