// What the to-do pickers and lists say in words: a repeat, a due date, a relative time typed, the Due list's work, the
// head's summary and an add line's hint by tag.
import { describe, expect, it } from "vitest"
import type { Block, Item } from "@/api/client"
import { addHint, fillFor, grouped, progress, summary } from "./groups"
import { dueSummary, readRelative, repeatLabel, repeatSummary } from "./Pickers"
import { isDueWork } from "./TodoPage"

const item = (id: number, over: Partial<Item>): Item =>
  ({
    id, title: `t${id}`, preset: null, area: null, tags: [], parent_id: null, when: "window", start: null, end: null,
    release: null, due: null, amount: "fixed", duration_min: 60, firmness: "hard", importance: 3, energy: null,
    shape: "split", certainty: "sure", status: "todo", series_id: null, done_min: 0, remaining_min: 60, ...over,
  }) as Item // prettier-ignore

describe("a repeat in words", () => {
  const r = (every: string | null, perWindow: number | null = null) => ({ every, perWindow })
  it("says once, every day, week or weekday, with how many times when it ends", () => {
    expect(repeatSummary(r(null))).toBe("Once.")
    expect(repeatSummary(r("day"))).toBe("Every day.")
    expect(repeatSummary(r("week"))).toBe("Every week.")
    expect(repeatSummary(r("weekdays"))).toBe("Every weekday.")
    expect(repeatSummary(r("rrule:FREQ=DAILY;COUNT=5"))).toBe("Every day, 5 times.")
    expect(repeatSummary(r("rrule:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;COUNT=10"))).toBe("Every weekday, 10 times.")
  })

  it("names the days, or says Friday picks them", () => {
    expect(repeatSummary(r("mon,thu"))).toBe("Every Mon, Thu.")
    expect(repeatSummary(r("rrule:FREQ=WEEKLY;BYDAY=TU,SA;COUNT=20"))).toBe("Every Tue, Sat, 20 times.")
    expect(repeatSummary(r("week", 3))).toBe("3 times a week. Friday picks the days.")
    expect(repeatSummary(r("rrule:FREQ=WEEKLY;COUNT=5", 2))).toBe("2 times a week, 5 times. Friday picks the days.")
  })

  it("falls back to every so often, or just that it repeats", () => {
    expect(repeatSummary(r("rrule:FREQ=YEARLY"))).toBe("Every year.")
    expect(repeatSummary(r("rrule:FREQ=MONTHLY;INTERVAL=3;COUNT=4"))).toBe("Every 3 months, 4 times.")
    expect(repeatSummary(r("rrule:FREQ=HOURLY"))).toBe("Repeats.")
  })

  it("is short on a chip", () => {
    expect(repeatLabel(r(null))).toBe("Once")
    expect(repeatLabel(r("week", 4))).toBe("4× a week")
    expect(repeatLabel(r("day"))).toBe("Every day")
    expect(repeatLabel(r("mon,wed,fri"))).toBe("Every Mon, Wed, Fri")
  })
})

describe("a due date in words", () => {
  it("says the day, the time and how far off, or that there's none", () => {
    expect(dueSummary(null, "2026-11-11")).toBe("No due date. Friday fits it in where it costs least.")
    expect(dueSummary("2026-11-11T17:00", "2026-11-11")).toBe("Due Wed 11 Nov, 5pm (today)")
    expect(dueSummary("2026-11-12T23:59", "2026-11-11")).toBe("Due Thu 12 Nov, 11:59pm (tomorrow)")
    expect(dueSummary("2026-12-01T09:30", "2026-11-11")).toBe("Due Tue 1 Dec, 9:30am (in 20 days)")
  })
})

describe("a relative time typed", () => {
  const now = "2026-11-11T10:20"
  it("reads minutes and hours from now, and days and weeks at the end of the day", () => {
    expect(readRelative("in 30 min", now)).toBe("2026-11-11T10:50")
    expect(readRelative("in 2 hours", now)).toBe("2026-11-11T12:20")
    expect(readRelative("in an hour", now)).toBe("2026-11-11T11:20")
    expect(readRelative("in 1.5h", now)).toBe("2026-11-11T11:50")
    expect(readRelative("in 3 days", now)).toBe("2026-11-14T23:59")
    expect(readRelative("in a week", now)).toBe("2026-11-18T23:59")
    expect(readRelative("in 2 wks", now)).toBe("2026-11-25T23:59")
    expect(readRelative("in a while", now)).toBeNull()
  })
})

describe("the Due list", () => {
  it("holds work with a due date, not meals, habits or open-ended work", () => {
    expect(isDueWork(item(1, { due: "2026-11-12T23:59" }))).toBe(true)
    expect(isDueWork(item(2, {}))).toBe(false)
    expect(isDueWork(item(3, { due: "2026-11-12T09:00", preset: "Routine" }))).toBe(false)
    expect(isDueWork(item(4, { due: "2026-11-12T09:00", preset: "Habit" }))).toBe(false)
    expect(isDueWork(item(5, { due: "2026-11-12T09:00", amount: "open" }))).toBe(false)
  })
})

describe("the list's words and order", () => {
  it("sums what's open and how long is left", () => {
    expect(summary([item(1, { remaining_min: 90 }), item(2, { remaining_min: 30 }), item(3, { status: "done", remaining_min: 0 })])).toBe("2 open, 2h left")
  })

  it("hints a tag's add line by its name, and the done section takes no adds", () => {
    expect(addHint("Tag", "MATH 1910")).toBe("Add to MATH 1910…")
    expect(addHint("Tag", "No tag")).toBe("Add anything else…")
    expect(fillFor("Kind", "Done")).toBeNull()
    expect(fillFor("Tag", "No tag")).toEqual({})
  })

  it("says when a task has no length yet, or only what's to do", () => {
    expect(progress(item(1, { remaining_min: 0, done_min: 0 })).text).toBe("No length yet")
    expect(progress(item(2, { remaining_min: 90 }))).toEqual({ pct: 0, text: "1h 30m to do" })
  })

  it("sorts longest first, and next up by when it's planned, else its due", () => {
    const items = [item(1, { remaining_min: 30, due: "2026-11-20T12:00" }), item(2, { remaining_min: 120 }), item(3, { remaining_min: 60, due: "2026-11-13T12:00" })]
    const blocks = [{ key: "b2", item_id: 2, start: "2026-11-12T09:00", end: "2026-11-12T11:00" } as Block]
    expect(grouped(items, [], "2026-11-11", "Tag", "Length")[0].items.map((i) => i.id)).toEqual([2, 3, 1])
    expect(grouped(items, blocks, "2026-11-11", "Tag", "Next up")[0].items.map((i) => i.id)).toEqual([2, 3, 1])
  })
})

describe("the day typed before Friday's day starts", () => {
  it("is the day the Today button means", () => {
    // 00:30 on the 12th, Friday's day still the 11th (it starts at 4am)
    expect(readRelative("today", "2026-11-12T00:30", "2026-11-11")).toBe("2026-11-11T23:59")
    expect(readRelative("tomorrow", "2026-11-12T00:30", "2026-11-11")).toBe("2026-11-12T23:59")
    expect(readRelative("in 3 days", "2026-11-12T00:30", "2026-11-11")).toBe("2026-11-14T23:59")
    expect(readRelative("in 2 hours", "2026-11-12T00:30", "2026-11-11")).toBe("2026-11-12T02:30")
  })
})
