import { describe, expect, it } from "vitest"
import { givesTimeToWork, layers, sideBySide } from "./layers"

const event = (title: string, more: { gives_way_to?: string | null; left_out?: string | null } = {}) => ({ title, gives_way_to: null, left_out: null, ...more })

describe("layers of a day column", () => {
  it("one you're not going to goes behind, apart from the events you go to", () => {
    const salsa = event("Salsa", { left_out: "skipped" })
    const lecture = event("Lecture")
    expect(layers([salsa, lecture])).toEqual({ notGoing: [salsa], going: [lecture], proposed: [] })
  })
  it("Friday's own Skip? stays in view, even if it's also left out", () => {
    const gym = event("Gym", { gives_way_to: "Essay", left_out: "skipped" })
    expect(layers([gym])).toEqual({ notGoing: [], going: [], proposed: [gym] })
  })
  it("left out for other reasons (free, filtered) is still drawn with the events", () => {
    const free = event("Office hours", { left_out: "free" })
    expect(layers([free]).going).toEqual([free])
  })
  it("every event lands in exactly one layer, order kept", () => {
    const all = [event("a"), event("b", { left_out: "skipped" }), event("c", { gives_way_to: "x" }), event("d")]
    const { notGoing, going, proposed } = layers(all)
    expect([...notGoing, ...going, ...proposed].sort((x, y) => x.title.localeCompare(y.title))).toEqual(all)
    expect(going.map((e) => e.title)).toEqual(["a", "d"])
  })
})

describe("a dashed event and the work over it", () => {
  const axis = { startMin: 6 * 60, endMin: 24 * 60 }
  const at = (title: string, from: string, to: string, more: { left_out?: string | null; holds?: { id: number; title: string } | null } = {}) =>
    ({ title, start: `2026-11-16T${from}`, end: `2026-11-16T${to}`, left_out: null, holds: null, gives_way_to: null, ...more })
  const block = (key: string, from: string, to: string) => ({ key, start: `2026-11-16T${from}`, end: `2026-11-16T${to}` })
  const overlaps = (a: { column: number }, b: { column: number }) => a.column !== b.column

  it("share the column side by side, as two overlapping events do", () => {
    const office = at("Office hours", "14:00", "15:00", { left_out: "calendar" }) // a "Just show it" calendar's
    const essay = block("T1", "14:00", "15:30")
    const { events, blocks } = sideBySide([office], [essay], "2026-11-16", axis, givesTimeToWork)
    expect(events).toHaveLength(1)
    expect(blocks).toHaveLength(1)
    expect(overlaps(events[0], blocks[0])).toBe(true)
    expect([events[0].columns, blocks[0].columns]).toEqual([2, 2])
  })

  it("leave the events that hold their time, and the work apart from them, as they were", () => {
    const lecture = at("Lecture", "10:00", "11:00")
    const holder = at("Study hall", "16:00", "17:00", { holds: { id: 2, title: "Reading" } })
    const reading = block("T2", "16:00", "17:00")
    const later = block("T3", "19:00", "20:00")
    const { events, blocks } = sideBySide([lecture, holder], [reading, later], "2026-11-16", axis, givesTimeToWork)
    expect(events.map((p) => [p.item.title, p.column, p.columns])).toEqual([["Lecture", 0, 1], ["Study hall", 0, 1]])
    expect(blocks.map((p) => [p.item.key, p.column, p.columns])).toEqual([["T2", 0, 1], ["T3", 0, 1]]) // drawn inside the hold
  })

  it("takes an event it overlaps along, so the two are never drawn one over the other", () => {
    const free = at("Club fair", "12:00", "14:00", { left_out: "free" })
    const meeting = at("Advisor", "13:00", "13:30")
    const work = block("T4", "13:30", "14:30")
    const { events, blocks } = sideBySide([free, meeting], [work], "2026-11-16", axis, givesTimeToWork)
    const columns = new Map([...events.map((p) => [p.item.title, p.column] as const), ...blocks.map((p) => [p.item.key, p.column] as const)])
    expect(columns.get("Club fair")).not.toBe(columns.get("Advisor"))
    expect(columns.get("Club fair")).not.toBe(columns.get("T4"))
  })

  it("one you're not going to, or one holding a task's time, isn't put beside the work", () => {
    expect(givesTimeToWork({ left_out: "skipped", holds: null, gives_way_to: null })).toBe(false)
    expect(givesTimeToWork({ left_out: "calendar", holds: { id: 1, title: "x" }, gives_way_to: null })).toBe(false)
    expect(givesTimeToWork({ left_out: "through", holds: null, gives_way_to: null })).toBe(true)
    expect(givesTimeToWork({ left_out: null, holds: null, gives_way_to: null })).toBe(false)
  })
})
