import { describe, expect, it } from "vitest"
import { type Answers, shift, stepsFor, timeOptions } from "./Setup"

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
    expect(stepsFor(ANSWERS)).toEqual(["day", "load", "focus", "free", "early", "brief"])
    expect(stepsFor({ ...ANSWERS, calendars: [{ name: "Home", shown: true, busy: true }] })).toContain("calendars")
  })

  it("offers half hours on a 12-hour clock, past midnight too, and keeps a time you'd set", () => {
    const night = timeOptions(22, 25, "23:30")
    expect(night.map((o) => o.value)).toEqual(["22:00", "22:30", "23:00", "23:30", "00:00", "00:30", "01:00"])
    expect(night.map((o) => o.label).slice(3, 5)).toEqual(["11:30pm", "12am"])
    expect(timeOptions(5, 6, "07:15")[0]).toEqual({ value: "07:15", label: "7:15am" })
  })

  it("moves a time on, round midnight", () => {
    expect(shift("07:30", 90)).toBe("09:00")
    expect(shift("23:30", 60)).toBe("00:30")
    expect(shift("00:30", -60)).toBe("23:30")
  })
})
