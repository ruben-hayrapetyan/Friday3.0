import { describe, expect, it } from "vitest"
import { type Answers, badgesOf, byAccount, hoursLabel, hoursWords, readDays, readHours, screenScale, shift, storyFor, withCalendars } from "./Setup"

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
  it("lives through a week: hello, the day from the alarm to bed, the next morning, packing up, the week (29 Oct)", () => {
    expect(storyFor(ANSWERS)).toEqual(["title", "hello", "hello2", "wake", "classes", "work", "heavy", "focus", "deadline", "evening", "weekend", "bed", "brief", "ai", "bring", "week"])
  })

  it("asks about calendars only when there are some, after bringing them in", () => {
    const story = storyFor({ ...ANSWERS, calendars: [{ name: "Home", shown: true, busy: true }] })
    expect(story.slice(-4)).toEqual(["ai", "bring", "calendars", "week"]) // the AI before what it reads; calendars once connected
    expect(storyFor(ANSWERS)).not.toContain("calendars")
  })

  it("adds the calendars connected while setup is open, keeping what you chose for the others", () => {
    const chosen = { ...ANSWERS, calendars: [{ name: "Home", shown: false, busy: false }] }
    const listed = [{ name: "Home", shown: true, busy: true }, { name: "Classes", shown: true, busy: true }]
    expect(withCalendars(chosen, listed).calendars).toEqual([{ name: "Home", shown: false, busy: false }, { name: "Classes", shown: true, busy: true }])
    expect(withCalendars(chosen, [{ name: "Home", shown: true, busy: true }])).toBe(chosen) // nothing new: the same draft
    expect(withCalendars(ANSWERS, null)).toBe(ANSWERS)
    expect(storyFor(withCalendars(ANSWERS, listed))).toContain("calendars") // connected in Bring things in: asked next
  })

  it("groups the Mac's calendars by account", () => {
    const cal = (name: string, account: string | null, on = true) => ({ id: name, name, account, on }) as never
    const groups = byAccount([cal("Birthdays", "Other", false), cal("Home", "iCloud"), cal("Personal", "me@gmail.com"), cal("Work", "iCloud"), cal("Local", null), cal("Scratch", "")])
    expect(groups.map(([a, list]) => [a, list.map((c: { name: string }) => c.name)])).toEqual([
      ["iCloud", ["Home", "Work"]],
      ["me@gmail.com", ["Personal"]],
      ["On this Mac", ["Local", "Scratch"]],
      ["Other", ["Birthdays"]], // only calendars left off: last
    ])
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

  it("ends on your week, each answer a badge that goes back to where it was asked (no fill-in-the-blank)", () => {
    const badges = badgesOf(ANSWERS)
    expect(badges.map((b) => [b.label, b.value])).toEqual([
      ["Up", "7:30am"],
      ["Bed", "11:30pm"],
      ["Work", "8h, up to 10h"],
      ["Focus", "3h"],
      ["Done", "a day early"],
      ["Evenings free", "2h from 6pm"],
      ["Weekends free", "4h a day"],
      ["Morning brief", "yes"],
    ])
    expect(new Set(badges.map((b) => b.step))).toEqual(new Set(["wake", "bed", "work", "focus", "deadline", "evening", "weekend", "brief"]))
    const plain = badgesOf({ ...ANSWERS, evening_free: 0, weekend_free: 13, most_hours: 8, finish_early_days: 0, brief: false }).map((b) => b.value)
    expect(plain).toEqual(["7:30am", "11:30pm", "8h", "3h", "on the day", "none", "all day", "no"])
    expect([hoursWords(1), hoursWords(1.5), hoursWords(0.75)]).toEqual(["an hour", "1.5 hours", "45 minutes"])
  })

  it("draws the screen at whole pixels when there's room, so the art stays sharp", () => {
    expect(screenScale(1100, 700)).toBe(4) // 1024 × 576
    expect(screenScale(800, 900)).toBe(3)
    expect(screenScale(400, 300)).toBeCloseTo(400 / 256) // a small window: as big as fits
    expect(screenScale(100, 50)).toBe(1)
  })
})
