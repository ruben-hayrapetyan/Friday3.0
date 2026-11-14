import { describe, expect, it } from "vitest"
import type { Schemas } from "@/api/client"
import { type Bit, minutes, ORDER, shift, sittings, sleepHours, underBar, weekOf, EDGE } from "./setupWeek"

type Answers = Schemas["SetupInput"]

const ANSWERS: Answers = {
  wake: "07:30",
  bedtime: "23:30",
  weekend_wake: "07:30",
  weekend_bedtime: "23:30",
  normal_hours: 5,
  most_hours: 8,
  focus_hours: 1.5,
  evening_free: 2,
  evening_from: "18:00",
  weekend_free: 4,
  finish_early_days: 1,
  brief: true,
  calendars: [],
}

const of = (bits: Bit[], kind: Bit["kind"], day?: number) => bits.filter((b) => b.kind === kind && (day === undefined || b.day === day))
const overlap = (x: Bit, y: Bit) => x.day === y.day && x.start < y.end && y.start < x.end
const hours = (bits: Bit[]) => bits.reduce((sum, b) => sum + b.end - b.start, 0) / 60

describe("the week beside setup's questions", () => {
  it("sleeps from bedtime to waking, past midnight too", () => {
    const { bits } = weekOf({ ...ANSWERS, bedtime: "00:30", weekend_bedtime: "00:30" }, "day")
    const monday = of(bits, "sleep", 0)
    expect(monday.map((b) => [b.start, b.end])).toEqual([
      [6 * 60, minutes("07:30")],
      [24 * 60 + 30, 26 * 60],
    ])
    expect(sleepHours({ ...ANSWERS, bedtime: "00:30", weekend_bedtime: "01:00", weekend_wake: "09:00" })).toEqual({ weekday: 7, weekend: 8 })
  })

  it("lays a normal day's work in sittings no longer than your focus, off classes, sleep and free time", () => {
    const { bits, workHours } = weekOf(ANSWERS, "focus")
    for (let day = 0; day < 5; day++) expect(hours(of(bits, "work", day))).toBe(5)
    const work = of(bits, "work")
    expect(work.every((b) => b.end - b.start <= 90 && b.end - b.start >= 30)).toBe(true) // no slivers
    const kept = [...of(bits, "class"), ...of(bits, "sleep"), ...of(bits, "free")]
    expect(work.filter((w) => kept.some((k) => overlap(w, k)))).toEqual([])
    expect(workHours).toBe(5 * 5 + 2 * 2.5) // a weekend day, half a normal one
  })

  it("follows the focus answer: shorter sittings, more of them", () => {
    const long = of(weekOf({ ...ANSWERS, focus_hours: 3 }, "focus").bits, "work", 0)
    const short = of(weekOf({ ...ANSWERS, focus_hours: 0.75 }, "focus").bits, "work", 0)
    expect(short.length).toBeGreaterThan(long.length)
    expect(Math.max(...short.map((b) => b.end - b.start))).toBe(45)
  })

  it("keeps weekday evenings from when they start, and weekend time at the day's end", () => {
    const { bits } = weekOf(ANSWERS, "free")
    expect(of(bits, "free", 1).map((b) => [b.start, b.end])).toEqual([[18 * 60, 20 * 60]])
    expect(of(bits, "free", 5).map((b) => [b.start, b.end])).toEqual([[minutes("23:30") - 240, minutes("23:30")]])
    const all = weekOf({ ...ANSWERS, evening_free: 5, weekend_free: 13 }, "free").bits
    expect(of(all, "free", 2)[0].end).toBe(minutes("23:30")) // all of it: to bedtime
    expect(of(all, "work", 6)).toEqual([]) // a weekend all yours has no work
    expect(of(weekOf({ ...ANSWERS, evening_free: 0, weekend_free: 0 }, "free").bits, "free")).toEqual([])
  })

  it("shows a heavy day only on the question about it", () => {
    expect(of(weekOf(ANSWERS, "load").bits, "heavy", 3).length).toBeGreaterThan(0)
    expect(hours(of(weekOf(ANSWERS, "load").bits, "heavy", 3))).toBeLessThanOrEqual(3)
    expect(of(weekOf(ANSWERS, "focus").bits, "heavy")).toEqual([])
    expect(of(weekOf({ ...ANSWERS, most_hours: 5 }, "load").bits, "heavy")).toEqual([])
  })

  it("finishes the example essay as early as you said, from that question on", () => {
    for (const early of [0, 1, 2, 3]) {
      const essay = of(weekOf({ ...ANSWERS, finish_early_days: early }, "early").bits, "essay")
      expect(essay).toHaveLength(2)
      expect(Math.max(...essay.map((b) => b.day))).toBe(4 - early)
      if (early === 0) expect(essay.every((b) => b.day < 4 || b.end <= 17 * 60)).toBe(true) // before 5 PM Friday
    }
    expect(of(weekOf(ANSWERS, "early").bits, "due")).toHaveLength(1)
    expect(of(weekOf(ANSWERS, "free").bits, "due")).toEqual([]) // not before its question
  })

  it("marks each morning's brief only when you want one", () => {
    expect(of(weekOf(ANSWERS, "brief").bits, "brief")).toHaveLength(7)
    expect(of(weekOf({ ...ANSWERS, brief: false }, "brief").bits, "brief")).toEqual([])
  })

  it("moves Wednesday's work out of the way when something comes up, in How Friday works", () => {
    const before = of(weekOf(ANSWERS, "how", 0).bits, "work", 2)
    const after = weekOf(ANSWERS, "how", 1).bits
    const event = of(after, "event", 2)
    expect(event).toHaveLength(1)
    expect(of(after, "work", 2).filter((w) => overlap(w, event[0]))).toEqual([])
    const moved = of(after, "work", 2).find((w) => w.id === "work-2-2")
    expect(moved && moved.start).toBeGreaterThanOrEqual(event[0].end) // the sitting it covered slides past it
    expect(hours(of(after, "work", 2))).toBeGreaterThan(hours(before) * 0.8) // what no longer fits goes to another day
  })

  it("keeps each bit's id from one answer to the next, so the week moves rather than flickers", () => {
    const ids = (a: Answers) => new Set(weekOf(a, "day").bits.map((b) => b.id))
    const before = ids(ANSWERS)
    const after = ids({ ...ANSWERS, wake: "08:30" })
    expect([...before].filter((id) => id.startsWith("sleep") || id.startsWith("class")).every((id) => after.has(id))).toBe(true)
    expect(new Set(weekOf(ANSWERS, "ready").bits.map((b) => b.id)).size).toBe(weekOf(ANSWERS, "ready").bits.length)
  })

  it("never leaves a sliver: no sitting under half an hour, even the last of a day's work", () => {
    for (const focus of [0.75, 1, 1.5, 2, 3, 4])
      for (const normal of [1, 2.5, 4, 5.25, 8]) {
        const work = of(weekOf({ ...ANSWERS, focus_hours: focus, normal_hours: normal }, "focus").bits, "work")
        expect(work.filter((b) => b.end - b.start < 30)).toEqual([])
      }
    const placed = sittings(9 * 60, 12 * 60, [[9 * 60 + 40, 10 * 60 + 30]], 120, 90)
    expect(placed[0][0]).toBeGreaterThanOrEqual(10 * 60 + 30) // the 25 minutes before the class are left
    expect(placed.reduce((s, [a, b]) => s + b - a, 0)).toBeLessThanOrEqual(120)
  })

  it("draws every screen in order, and moves times round midnight", () => {
    expect(ORDER[0]).toBe("welcome")
    expect(ORDER.at(-1)).toBe("ready")
    expect(shift("23:30", 60)).toBe("00:30")
    expect(shift("00:10", -15)).toBe("23:55")
  })
})

// The day bars' "Up 6am" and "Bed 2am" under the walk's days (13 Nov: a client's early wake and late bed put them
// half outside the box): centered on their time, they lean inward near the bar's ends, so they never leave it.
describe("a time under the day bar", () => {
  it("is centered on its time away from the ends", () => {
    expect(underBar(50)).toEqual({ left: "50%", translate: "-50% 0" })
    expect(underBar(EDGE)).toEqual({ left: `${EDGE}%`, translate: "-50% 0" })
    expect(underBar(100 - EDGE)).toEqual({ left: `${100 - EDGE}%`, translate: "-50% 0" })
  })

  it("starts at the left edge at the bar's start and ends at the right edge at its end", () => {
    expect(underBar(0)).toEqual({ left: "0%", translate: "0% 0" })
    expect(underBar(100)).toEqual({ left: "100%", translate: "-100% 0" })
  })

  it("leans in smoothly between, never past the ends", () => {
    const share = (pct: number) => -Number.parseFloat(underBar(pct).translate) / 100 // how much of the label is left of its time
    for (let pct = 0; pct <= 100; pct += 0.5) {
      const s = share(pct)
      expect(s).toBeGreaterThanOrEqual(0)
      expect(s).toBeLessThanOrEqual(1)
      // a label as wide as EDGE*2% of the bar: its left side is at or after 0 and its right side at or before 100
      expect(pct - s * EDGE * 2).toBeGreaterThanOrEqual(-1e-9)
      expect(pct + (1 - s) * EDGE * 2).toBeLessThanOrEqual(100 + 1e-9)
    }
    expect(share(3)).toBeLessThan(share(6))
  })

  it("keeps a time outside the bar's span at its end", () => {
    expect(underBar(-5)).toEqual(underBar(0))
    expect(underBar(130)).toEqual(underBar(100))
  })
})
