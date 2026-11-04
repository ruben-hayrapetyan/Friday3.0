import { describe, expect, it } from "vitest"
import { bars, folded, isOnDay, isWholeDay } from "./wholeDay"

const WEEK = ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-07", "2026-11-08"]
const ev = (title: string, start: string, end: string) => ({ title, start: `${start}T00:00`, end: `${end}T00:00` })
const shape = (out: ReturnType<typeof bars<ReturnType<typeof ev>>>) => out.map((b) => [b.event.title, b.from, b.to, b.row])

// black box: how the week's whole-day events are drawn

describe("whole-day bars", () => {
  it("a one-day event is a bar over its day", () => {
    expect(shape(bars([ev("Birthday", "2026-11-05", "2026-11-06")], WEEK))).toEqual([["Birthday", 3, 3, 0]])
  })

  it("an event over several days is one bar across them", () => {
    expect(shape(bars([ev("Fall break", "2026-11-04", "2026-11-07")], WEEK))).toEqual([["Fall break", 2, 4, 0]])
  })

  it("events on the same days take rows; ones that don't overlap share a row", () => {
    const out = bars([ev("Break", "2026-11-03", "2026-11-06"), ev("Birthday", "2026-11-04", "2026-11-05"), ev("Holiday", "2026-11-07", "2026-11-08")], WEEK)
    expect(shape(out)).toEqual([
      ["Break", 1, 3, 0],
      ["Birthday", 2, 2, 1],
      ["Holiday", 5, 5, 0],
    ])
  })

  it("an event running past the week's edges is cut at them, and says so", () => {
    const [bar] = bars([ev("Trip", "2026-10-30", "2026-11-12")], WEEK)
    expect([bar.from, bar.to, bar.clippedStart, bar.clippedEnd]).toEqual([0, 6, true, true])
  })

  it("events outside the days shown aren't drawn", () => {
    expect(bars([ev("Before", "2026-10-30", "2026-11-02"), ev("After", "2026-11-09", "2026-11-10")], WEEK)).toEqual([])
  })

  it("one day shown: its own events only", () => {
    expect(shape(bars([ev("Birthday", "2026-11-05", "2026-11-06"), ev("Other", "2026-11-06", "2026-11-07")], ["2026-11-05"]))).toEqual([["Birthday", 0, 0, 0]])
  })
})

// glass box: the packing and the whole-day test

describe("bars' packing", () => {
  it("longer events first on the same start, so they sit on top", () => {
    const out = bars([ev("Short", "2026-11-03", "2026-11-04"), ev("Long", "2026-11-03", "2026-11-06")], WEEK)
    expect(shape(out)).toEqual([
      ["Long", 1, 3, 0],
      ["Short", 1, 1, 1],
    ])
  })

  it("no two bars in a row overlap, whatever the events", () => {
    const events = Array.from({ length: 40 }, (_, n) => ev(`E${n}`, `2026-11-0${1 + (n % 7)}`, `2026-11-${String(2 + (n % 7) + (n % 3)).padStart(2, "0")}`))
    const out = bars(events, WEEK)
    for (const a of out)
      for (const b of out) if (a !== b && a.row === b.row) expect(a.to < b.from || b.to < a.from).toBe(true)
    expect(out.every((b) => b.from >= 0 && b.to <= 6 && b.from <= b.to)).toBe(true)
  })

  it("whole days run midnight to a later midnight", () => {
    expect(isWholeDay({ start: "2026-11-05T00:00", end: "2026-11-06T00:00" })).toBe(true)
    expect(isWholeDay({ start: "2026-11-05T00:00", end: "2026-11-05T00:00" })).toBe(false)
    expect(isWholeDay({ start: "2026-11-05T09:00", end: "2026-11-06T00:00" })).toBe(false)
    expect(isWholeDay({ start: null, end: null })).toBe(false)
  })
})

describe("a pile of whole-day events", () => {
  const pile = Array.from({ length: 6 }, (_, n) => ev(`E${n}`, "2026-11-04", "2026-11-05"))

  it("keeps to three rows: two of bars, then a count on each day with more", () => {
    const { shown, more } = folded(bars(pile, WEEK), WEEK.length)
    expect(shown.map((b) => b.row)).toEqual([0, 1])
    expect(more).toEqual([0, 0, 4, 0, 0, 0, 0])
  })

  it("a long event folded away counts on every day it covers", () => {
    const placed = bars([...pile, ev("Trip", "2026-11-03", "2026-11-07")], WEEK)
    const { more } = folded(placed, WEEK.length)
    expect(more[1] + more[2] + more[3] + more[4]).toBeGreaterThan(0)
    expect(more[0]).toBe(0)
  })

  it("three rows or fewer are shown whole", () => {
    const three = pile.slice(0, 3)
    const { shown, more } = folded(bars(three, WEEK), WEEK.length)
    expect(shown).toHaveLength(3)
    expect(more.every((n) => n === 0)).toBe(true)
  })

  it("nothing is lost: what's shown and what's counted are every event on every day", () => {
    const many = Array.from({ length: 30 }, (_, n) => ev(`M${n}`, `2026-11-0${2 + (n % 6)}`, `2026-11-0${3 + (n % 6) + (n % 2)}`))
    const placed = bars(many, WEEK)
    const { shown, more } = folded(placed, WEEK.length)
    for (let c = 0; c < WEEK.length; c++) {
      const covering = placed.filter((b) => b.from <= c && c <= b.to).length
      const visible = shown.filter((b) => b.from <= c && c <= b.to).length
      expect(visible + more[c]).toBe(covering)
    }
  })
})

describe("which days an event is on (the month view)", () => {
  it("a whole-day event is on every day it covers, not the day it ends", () => {
    const trip = ev("Trip", "2026-11-02", "2026-11-05")
    expect(["2026-11-01", "2026-11-02", "2026-11-04", "2026-11-05"].map((d) => isOnDay(trip, d))).toEqual([false, true, true, false])
  })

  it("a timed event is on the day it starts", () => {
    const late = { start: "2026-11-02T23:00", end: "2026-11-03T01:00" }
    expect([isOnDay(late, "2026-11-02"), isOnDay(late, "2026-11-03")]).toEqual([true, false])
  })
})
