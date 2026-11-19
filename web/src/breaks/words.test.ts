// Breaks' words and switches (glass box): what a break says it pauses, and how a calendar or a repeat is switched.
import { describe, expect, it } from "vitest"
import { contrast, mix } from "@/theme/contrast"
import { BREAK, PAPER } from "@/theme/look"
import { allCalendars, EVERYTHING, flipCalendar, flipSeries, inView, listed, modeWords, pauses, pauseWords, rangeWords } from "./words"

describe("a break in words", () => {
  it("says its days and how much work", () => {
    expect(rangeWords("2026-12-21", "2026-12-27")).toBe("Mon, Dec 21 – Sun, Dec 27")
    expect(rangeWords("2026-12-21", "2026-12-21")).toBe("Mon, Dec 21")
    // 19 Nov: a Light day is time a day, not a number of things ("shouldn't depend on the number of events")
    expect(modeWords("light", 120)).toBe("Light, about 2h of work a day")
    expect(modeWords("light", 90)).toBe("Light, about 1h 30m of work a day")
    expect(modeWords("off", 120)).toBe("Off: nothing to do")
  })
  it("says what it pauses as a value, however many calendars", () => {
    expect(pauseWords(EVERYTHING)).toBe("Every repeating event")
    expect(pauseWords({ ...EVERYTHING, calendars: ["Family"] })).toBe("Every repeating event except Family")
    expect(pauseWords({ ...EVERYTHING, calendars: ["Family", "Trips", "Kids"], tags: ["Work"] })).toBe("Every repeating event except 3 calendars; tasks tagged Work wait")
    const twenty = { calendars: Array.from({ length: 20 }, (_, n) => ({ name: `Cal ${n}`, repeats: 1 })), tags: [], series: [] }
    expect(pauseWords({ ...EVERYTHING, repeating: "only", calendars: ["Cal 1", "Cal 2"] }, twenty)).toBe("Repeating events on 2 of 20 calendars")
    expect(listed(["Work", "Home", "Gym", "Book club"])).toBe("Work, Home and 2 more")
    expect(listed(["Work", "Home"])).toBe("Work and Home")
  })
})

describe("switching what pauses", () => {
  it("a calendar's repeats follow it; a repeat switched goes against it, and back", () => {
    const keepFamily = flipCalendar(EVERYTHING, "Family")
    expect(pauses(keepFamily, 1, "Family")).toBe(false)
    expect(pauses(keepFamily, 2, "Work")).toBe(true)
    const keepStandup = flipSeries(keepFamily, 2, "Work")
    expect(pauses(keepStandup, 2, "Work")).toBe(false)
    expect(pauses(flipSeries(keepStandup, 2, "Work"), 2, "Work")).toBe(true)
  })
  it("pause all and keep all clear the exceptions", () => {
    const some = flipSeries(flipCalendar(EVERYTHING, "Family"), 4, "Work")
    expect(pauses(allCalendars(some, true), 4, "Work")).toBe(true)
    expect(pauses(allCalendars(some, false), 1, "Family")).toBe(false)
  })
})

describe("on the calendar", () => {
  const week = ["2026-12-19", "2026-12-20", "2026-12-21", "2026-12-22", "2026-12-23", "2026-12-24", "2026-12-25"]
  it("a break's band covers its days in the week shown, clipped at the edges", () => {
    expect(inView("2026-12-21", "2026-12-27", week)).toEqual({ from: 2, to: 6, clippedStart: false, clippedEnd: true })
    expect(inView("2026-12-10", "2026-12-20", week)).toEqual({ from: 0, to: 1, clippedStart: true, clippedEnd: false })
    expect(inView("2027-01-01", "2027-01-02", week)).toBeNull()
  })
  it("its color reads as text on the page and on cards, light and dark", () => {
    for (const [look, ink] of [["light", BREAK.light], ["dark", BREAK.dark]] as const) {
      const [bg, surface] = PAPER[look]
      expect(contrast(ink, bg)).toBeGreaterThanOrEqual(4.5)
      expect(contrast(ink, surface)).toBeGreaterThanOrEqual(4.5)
      expect(mix(ink, bg, 50).length).toBe(3)
    }
  })
})

describe("what's due during a break", () => {
  it("is work, not meals, routines, habits or events (found in the demo: 19 things, Breakfast, Lunch, Dinner…)", async () => {
    const { dueInside } = await import("./BreakDialog")
    const items = [
      { title: "Lunch", due: "2026-11-19T14:30", preset: "Routine", when: "window" },
      { title: "Run", due: "2026-11-19T20:00", preset: "Habit", when: "window" },
      { title: "Lab report", due: "2026-11-20T17:00", preset: "Assignment", when: "window" },
      { title: "Essay", due: "2026-11-25T17:00", preset: "Assignment", when: "window" },
    ]
    expect(dueInside(items, "2026-11-18", "2026-11-22").map((i) => i.title)).toEqual(["Lab report"])
  })
})

describe("a break day in the month (found in the review, 18 Nov: it drew planned times and paused classes)", () => {
  it("keeps events that stay and drops planned work and paused events", async () => {
    const { keptOnBreakDay } = await import("./words")
    expect(keptOnBreakDay(true, { event: true, left_out: "paused" })).toBe(false)
    expect(keptOnBreakDay(true, { event: true, left_out: null })).toBe(true)
    expect(keptOnBreakDay(true, { event: false })).toBe(false)
    expect(keptOnBreakDay(false, { event: false })).toBe(true)
  })
})

describe("when a task is planned, said on a break (found in the review: rows said \"Wed 2pm\" on a day with no times)", () => {
  it("names the day's list, not a time; any other day as before", async () => {
    const { plannedWords } = await import("./words")
    const ranges = [{ start: "2026-11-18", end: "2026-11-22" }]
    const when = (at: string) => `at ${at.slice(11)}`
    expect(plannedWords("2026-11-18T14:00", "2026-11-18", ranges, when)).toBe("today's list")
    expect(plannedWords("2026-11-20T09:00", "2026-11-18", ranges, when)).toBe("Fri's list")
    expect(plannedWords("2026-11-23T09:00", "2026-11-18", ranges, when)).toBe("at 09:00")
  })
})
