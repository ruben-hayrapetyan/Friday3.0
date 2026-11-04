import { describe, expect, it } from "vitest"
import { layers } from "./layers"

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
