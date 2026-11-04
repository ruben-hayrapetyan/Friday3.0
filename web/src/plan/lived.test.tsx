import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import type { Schemas } from "@/api/client"
import { toMin } from "@/lib/time"
import { mealSpans, sleepSpans } from "./lived"
import { LivedRail, railTone } from "./LivedRail"
import { PX } from "./Pieces"

const night = (over: Partial<Schemas["SleepNightOut"]>): Schemas["SleepNightOut"] => ({ date: "2026-11-03", planned_min: 450, ready_timed: false, done_timed: false, ...over })
const sleep = (over: Partial<Schemas["SleepOut"]>): Schemas["SleepOut"] => ({ on: true, nights: [], naps: [], ...over }) as Schemas["SleepOut"]
const meal = (over: Partial<Schemas["MealOut"]>): Schemas["MealOut"] => ({ id: 1, kind: "lunch", date: "2026-11-04", skipped: false, ...over }) as Schemas["MealOut"]
const meals = (over: Partial<Schemas["MealsOut"]>): Schemas["MealsOut"] => ({ on: true, days: [], ...over }) as Schemas["MealsOut"]
const now = toMin("2026-11-04T13:00")

// Glass box: how the taps become spans.
describe("what you tapped becomes spans", () => {
  it("a night is asleep from bed to up, then the routine from up to ready", () => {
    const spans = sleepSpans(sleep({ nights: [night({ bed: "2026-11-04T02:47", up: "2026-11-04T09:17", ready: "2026-11-04T09:41" })] }), now)
    expect(spans.map((s) => [s.kind, s.start, s.end])).toEqual([
      ["sleep", "2026-11-04T02:47", "2026-11-04T09:17"],
      ["routine", "2026-11-04T09:17", "2026-11-04T09:41"],
    ])
    expect(spans[0].label).toBe("Asleep 2:47am–9:17am · 6h 30m")
  })

  it("leaves out a half-recorded night, a backwards one, and everything while tracking is off", () => {
    expect(sleepSpans(sleep({ nights: [night({ bed: "2026-11-04T01:00" })] }), now)).toEqual([])
    expect(sleepSpans(sleep({ nights: [night({ bed: "2026-11-04T09:00", up: "2026-11-04T08:00" })] }), now)).toEqual([])
    expect(sleepSpans(sleep({ on: false, nights: [night({ bed: "2026-11-04T01:00", up: "2026-11-04T08:00" })] }), now)).toEqual([])
    expect(sleepSpans(undefined, now)).toEqual([])
  })

  it("a nap still going runs to now, once", () => {
    const napping = { id: 5, date: "2026-11-04", start: "2026-11-04T12:30" }
    const spans = sleepSpans(sleep({ naps: [napping], napping }), now)
    expect(spans).toHaveLength(1)
    expect(spans[0]).toMatchObject({ kind: "sleep", end: "2026-11-04T13:00", label: "Nap 12:30pm–now · 30m" })
  })

  it("meals eaten, not skipped ones; the one you're eating runs to now", () => {
    const eating = meal({ id: 3, start: "2026-11-04T12:40" })
    const spans = mealSpans(meals({ eating, days: [{ date: "2026-11-04", meals: [meal({ id: 1, kind: "breakfast", skipped: true }), meal({ id: 2, start: "2026-11-04T11:20", end: "2026-11-04T11:40" }), eating] }] }), now)
    expect(spans.map((s) => s.label)).toEqual(["Lunch 11:20am–11:40am · 20m", "Lunch 12:40pm–now · 20m"])
    expect(mealSpans(meals({ on: false }), now)).toEqual([])
  })
})

// Black box: what the calendar draws.
describe("the rail down a day's column", () => {
  const axis = { startMin: 8 * 60, endMin: 27 * 60 }
  const lived = [...sleepSpans(sleep({ nights: [night({ bed: "2026-11-04T02:47", up: "2026-11-04T09:17", ready: "2026-11-04T09:41" })] }), now), ...mealSpans(meals({ days: [{ date: "2026-11-04", meals: [meal({ start: "2026-11-04T11:20", end: "2026-11-04T11:40" })] }] }), now)]

  it("shows on its day what happened inside the hours shown, each named on hover", () => {
    const html = renderToStaticMarkup(<LivedRail lived={lived} date="2026-11-04" axis={axis} light />)
    expect(html.match(/data-lived="/g)).toHaveLength(3)
    expect(html).toContain('title="Asleep 2:47am–9:17am · 6h 30m"')
    expect(html).toContain('title="Morning routine 9:17am–9:41am · 24m"')
    expect(html).toContain('aria-label="Lunch 11:20am–11:40am · 20m"')
    // The sleep starts at the top of the hours shown (8am), cut there, and runs to 9:17.
    expect(html).toContain(`top:0;height:${77 * PX}px`)
  })

  it("a night past midnight is drawn in the evening's column too, when its hours reach that far", () => {
    const html = renderToStaticMarkup(<LivedRail lived={lived} date="2026-11-03" axis={axis} light />)
    expect(html.match(/data-lived="/g)).toHaveLength(1)
    expect(html).toContain('data-lived="sleep"')
  })

  it("is a thin, faint line that keeps clear of the blocks' 3px gap", () => {
    const html = renderToStaticMarkup(<LivedRail lived={lived} date="2026-11-04" axis={axis} light={false} />)
    expect(html).toContain("width:2px")
    expect(html).not.toMatch(/z-index/)
    for (const kind of ["sleep", "routine", "meal"] as const) expect(railTone(kind, true)).toMatch(/color-mix\(.* (30|40|60)%, transparent\)/)
  })

  it("draws nothing on a day nothing was recorded", () => {
    expect(renderToStaticMarkup(<LivedRail lived={lived} date="2026-10-20" axis={axis} light />)).toBe("")
  })
})
