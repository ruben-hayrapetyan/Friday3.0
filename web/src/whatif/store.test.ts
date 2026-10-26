import { beforeEach, describe, expect, it } from "vitest"
import type { Schemas } from "@/api/client"
import { whatIf, within } from "./store"

const tried = (made: number[][], changed: number[][] = []) =>
  ({ changes: made.map((created, i) => ({ said: "", created, changed: changed[i] ?? [] })) }) as unknown as Schemas["WhatIfOut"]

describe("What if", () => {
  beforeEach(() => {
    whatIf.stop()
    whatIf.here(false)
  })

  it("stages only while on, and only on the Plan page, and only changes it can try", () => {
    expect(whatIf.stages("add")).toBe(false)
    whatIf.start()
    expect(whatIf.stages("add")).toBe(false) // another page: it saves as usual
    whatIf.here(true)
    expect(whatIf.stages("add")).toBe(true)
    expect(whatIf.stages("pin")).toBe(true)
    expect(whatIf.stages("done")).toBe(false) // what happened, not a plan: it's real
    expect(whatIf.stages("start")).toBe(false)
  })

  it("names an item a staged change made by its placeholder", () => {
    whatIf.start()
    whatIf.stage("add", { title: "Coffee", when: "fixed" })
    whatIf.learned(tried([[501]]))
    whatIf.stage("edit", { id: 501, start: "2026-10-20T14:00" })
    whatIf.stage("pin", { id: 7, start: "2026-10-20T09:00" }) // a real item keeps its id
    const [, moved, pinned] = whatIf.get().changes
    expect(moved.input).toEqual({ id: -1, start: "2026-10-20T14:00" })
    expect(pinned.input.id).toBe(7)
    expect(whatIf.get().marked.has(501)).toBe(true)
  })

  it("taking a change out moves later placeholders one place earlier", () => {
    whatIf.start()
    whatIf.stage("add", { text: "laundry ~1h" })
    whatIf.stage("add", { title: "Coffee", when: "fixed" })
    whatIf.learned(tried([[500], [501]]))
    whatIf.stage("edit", { id: 501, title: "Coffee with Sam" })
    expect(whatIf.get().changes[2].input.id).toBe(-1001)
    whatIf.remove(0)
    expect(whatIf.get().changes.map((c) => c.input.id ?? null)).toEqual([null, -1])
    whatIf.stop()
    expect(whatIf.get().changes).toEqual([])
  })

  it("shows the part of the trial calendar in view", () => {
    const plan = {
      plan_id: 1,
      blocks: [{ start: "2026-10-19T10:00", end: "2026-10-19T11:00" }, { start: "2026-10-27T10:00", end: "2026-10-27T11:00" }],
      fixed: [{ start: "2026-10-20T09:00", end: "2026-10-20T10:00" }],
      day_hours: { "2026-10-19": 1, "2026-10-27": 1 },
      sessions: [],
    } as unknown as Schemas["PlanOut"]
    const seen = within(plan, "2026-10-19T00:00", "2026-10-26T00:00")
    expect(seen.blocks).toHaveLength(1)
    expect(seen.fixed).toHaveLength(1)
    expect(seen.day_hours).toEqual({ "2026-10-19": 1 })
  })
})
