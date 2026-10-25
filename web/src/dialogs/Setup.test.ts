import { describe, expect, it } from "vitest"
import { type Answers, hoursLabel, readDays, readHours, shift, stepsFor } from "./Setup"

const ANSWERS: Answers = {
  wake: "07:30",
  bedtime: "23:30",
  weekend_wake: "09:00",
  weekend_bedtime: "00:30",
  normal_hours: 8,
  most_hours: 10,
  focus_hours: 3,
  evening_free: 2,
  evening_from: "18:00",
  weekend_free: 4,
  finish_early_days: 1,
  brief: true,
  calendars: [],
}

describe("setup", () => {
  it("asks about calendars only when there are some", () => {
    expect(stepsFor(ANSWERS)).toEqual(["day", "load", "focus", "free", "early", "brief", "bring"])
    expect(stepsFor({ ...ANSWERS, calendars: [{ name: "Home", shown: true, busy: true }] })).toContain("calendars")
  })

  it("ends by bringing things in: Google, feeds, a syllabus and Gmail, after every question", () => {
    const steps = stepsFor({ ...ANSWERS, calendars: [{ name: "Home", shown: true, busy: true }] })
    expect(steps).toHaveLength(8)
    expect(steps.at(-1)).toBe("bring")
  })

  it("reads any amount you type: a bare number is hours", () => {
    expect(["6", "6.5", "6h", "6 hours", "1h30", "90 min", "an hour and a half", "10", "45m"].map(readHours)).toEqual([6, 6.5, 6, 6, 1.5, 1.5, 1.5, 10, 0.75])
    expect(readHours("7h20")).toBe(7.25) // to the quarter hour
    expect(readHours("lots")).toBeNull()
    expect(readHours("")).toBeNull()
    expect([hoursLabel(6), hoursLabel(6.5), hoursLabel(0.75)]).toEqual(["6h", "6.5h", "45m"])
  })

  it("reads days typed", () => {
    expect(["5", "5 days", "a day", "1 day"].map(readDays)).toEqual([5, 5, 1, 1])
    expect(readDays("soon")).toBeNull()
  })

  it("moves a time on, round midnight", () => {
    expect(shift("07:30", 90)).toBe("09:00")
    expect(shift("23:30", 60)).toBe("00:30")
    expect(shift("00:30", -60)).toBe("23:30")
  })
})
