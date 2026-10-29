import { describe, expect, it } from "vitest"
import { type Answers, hoursLabel, hoursWords, readDays, readHours, screensFor, shift, stepsFor, summaryOf } from "./Setup"

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
    expect(stepsFor(ANSWERS)).toEqual(["day", "load", "focus", "free", "early", "brief", "ai", "bring"])
    expect(stepsFor({ ...ANSWERS, calendars: [{ name: "Home", shown: true, busy: true }] })).toContain("calendars")
  })

  it("ends by bringing things in: Google, feeds, a syllabus and Gmail, after every question", () => {
    const steps = stepsFor({ ...ANSWERS, calendars: [{ name: "Home", shown: true, busy: true }] })
    expect(steps).toHaveLength(9)
    expect(steps.at(-1)).toBe("bring")
    expect(steps.at(-2)).toBe("ai") // the AI is chosen before what it reads: syllabi and mail (28 Oct)
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

  it("introduces Friday first and reads your answers back last (29 Oct)", () => {
    expect(screensFor(ANSWERS)).toEqual(["welcome", "how", ...stepsFor(ANSWERS), "ready"])
  })

  it("reads your answers back as sentences, each answer a way back to its question", () => {
    const parts = summaryOf(ANSWERS)
    const text = parts.map((p) => (typeof p === "string" ? p : p.text)).join("")
    expect(text).toContain("You're up at 7:30am and in bed by 11:30pm, or 9am and 12:30am at weekends.")
    expect(text).toContain("Friday plans 8 hours of work on a normal day and up to 10 hours on a heavy one, in sittings of up to 3 hours.")
    expect(text).toContain("2 hours of each weekday evening is yours from 6pm, and 4 hours of each weekend day.")
    expect(text).toContain("Work is done a day early")
    expect(text).toContain("Each morning opens with your brief.")
    const steps = new Set(parts.flatMap((p) => (typeof p === "string" ? [] : [p.step])))
    expect([...steps].sort()).toEqual(["brief", "day", "early", "focus", "free", "load"])
  })

  it("says none and all of it plainly", () => {
    const text = (a: Answers) => summaryOf(a).map((p) => (typeof p === "string" ? p : p.text)).join("")
    expect(text({ ...ANSWERS, evening_free: 0, weekend_free: 0, brief: false, finish_early_days: 0, most_hours: 8 })).toContain(
      "Weekday evenings are open for work, and weekends are open for work. Work is done on the day it's due",
    )
    expect(text({ ...ANSWERS, evening_free: 5, weekend_free: 13 })).toContain("Weekday evenings are yours from 6pm, and weekends are yours.")
    expect(text({ ...ANSWERS, most_hours: 8 })).not.toContain("heavy")
    expect([hoursWords(1), hoursWords(1.5), hoursWords(0.75)]).toEqual(["an hour", "1.5 hours", "45 minutes"])
  })
})
