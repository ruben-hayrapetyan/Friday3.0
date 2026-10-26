import { beforeEach, describe, expect, it } from "vitest"
import type { Schemas } from "@/api/client"
import { type Change, leading, placeholder, trialView, whatIf, within } from "./store"

type Plan = Schemas["PlanOut"]
type Out = Schemas["WhatIfOut"]

const answer = (made: number[][], plan: Partial<Plan> = {}, changed: number[][] = []) =>
  ({ plan: { plan_id: 2, blocks: [], fixed: [], day_hours: {}, sessions: [], ...plan }, changes: made.map((created, i) => ({ said: "", created, changed: changed[i] ?? [] })), verdict: "fits", said: "Fits" }) as unknown as Out

const block = (item_id: number, start: string, end: string) => ({ key: `T${item_id}@${start}`, item_id, title: `T${item_id}`, start, end }) as Plan["blocks"][number]
const event = (id: number, title: string, start: string, end: string) => ({ id, title, start, end, when: "fixed" }) as unknown as Plan["fixed"][number]
const plan = (fixed: Plan["fixed"] = [], blocks: Plan["blocks"] = []) => ({ plan_id: 1, blocks, fixed, day_hours: {}, sessions: [] }) as Plan
const staged = () => whatIf.get().changes

describe("What if", () => {
  beforeEach(() => {
    whatIf.stop()
    whatIf.here(false)
  })

  it("stages only while on, only on the Plan page, and only changes it can try", () => {
    expect(whatIf.stages("add")).toBe(false)
    whatIf.start()
    expect(whatIf.stages("add")).toBe(false) // another page: it saves as usual
    whatIf.here(true)
    expect(whatIf.stages("add")).toBe(true)
    expect(whatIf.stages("pin")).toBe(true)
    expect(whatIf.stages("done")).toBe(false) // what happened, not a plan: it's real
    expect(whatIf.stages("start")).toBe(false)
  })

  it("names an item a staged change made by its placeholder, and knows which change made it", () => {
    whatIf.start()
    whatIf.stage("add", { title: "Coffee", when: "fixed" })
    whatIf.learned(staged(), answer([[501]]))
    whatIf.stage("edit", { id: 501, start: "2026-10-20T14:00" })
    whatIf.stage("pin", { id: 7, start: "2026-10-20T09:00" }) // a real item keeps its id
    expect(staged()[1].input).toEqual({ id: -1, start: "2026-10-20T14:00" })
    expect(staged()[2].input.id).toBe(7)
    expect([whatIf.madeBy(501), whatIf.madeBy(placeholder(0)), whatIf.madeBy(7), whatIf.madeBy(placeholder(9))]).toEqual([0, 0, null, null])
  })

  it("taking a change out moves later placeholders one place earlier", () => {
    whatIf.start()
    whatIf.stage("add", { text: "laundry ~1h" })
    whatIf.stage("add", { title: "Coffee", when: "fixed" })
    whatIf.learned(staged(), answer([[500], [501]]))
    whatIf.stage("edit", { id: 501, title: "Coffee with Sam" })
    expect(staged()[2].input.id).toBe(placeholder(1))
    whatIf.remove(0)
    expect(staged().map((c) => c.input.id ?? null)).toEqual([null, placeholder(0)])
  })

  it("⌘Z takes back the last change tried, and nothing when there is none", () => {
    whatIf.start()
    expect(whatIf.undoLast()).toBe(false)
    whatIf.stage("drop", { id: 4 })
    whatIf.stage("drop", { id: 5 })
    expect(whatIf.undoLast()).toBe(true)
    expect(staged().map((c) => c.input.id)).toEqual([4])
  })

  it("a tried event saved again stays the one change it was", () => {
    whatIf.start()
    whatIf.stage("add", { title: "Coffee", when: "fixed", start: "2026-10-20T14:00", end: "2026-10-20T15:00" })
    whatIf.replace(0, { title: "Coffee with Sam", when: "fixed", start: "2026-10-20T16:00", end: "2026-10-20T17:00" })
    expect(staged()).toHaveLength(1)
    expect(staged()[0].input.title).toBe("Coffee with Sam")
  })

  it("draws a change the moment it's made, before its answer", () => {
    const real = plan([event(9, "Club", "2026-10-21T18:00", "2026-10-21T19:00")], [block(3, "2026-10-20T10:00", "2026-10-20T11:00")])
    const changes: Change[] = [
      { command: "add", input: { title: "Coffee", when: "fixed", start: "2026-10-20T14:00", end: "2026-10-20T15:00" } },
      { command: "pin", input: { id: 3, start: "2026-10-22T10:00", end: "2026-10-22T11:00", from_start: "2026-10-20T10:00" } },
      { command: "drop", input: { id: 9 } },
    ]
    const view = trialView(real, undefined, changes, 0)
    expect(view.fixed.map((f) => [f.id, f.title, f.start])).toEqual([
      [9, "Club", "2026-10-21T18:00"], // deleted, but still drawn (faded) where it was
      [placeholder(0), "Coffee", "2026-10-20T14:00"],
    ])
    expect(view.blocks[0].start).toBe("2026-10-22T10:00") // the block moved at once
    expect(view.tried?.made.has(placeholder(0))).toBe(true)
    expect(view.tried?.gone.has(9)).toBe(true)
    expect(view.tried?.moved.get(3)).toBe("2026-10-20T10:00") // said against your plan
    expect(view.tried?.pending).toBe(true)
  })

  it("an answer replaces what was drawn, and changes made since are drawn on it", () => {
    const real = plan([], [block(3, "2026-10-20T10:00", "2026-10-20T11:00")])
    const first: Change = { command: "add", input: { title: "Coffee", when: "fixed", start: "2026-10-20T14:00", end: "2026-10-20T15:00" } }
    const out = answer([[700]], { fixed: [event(700, "Coffee", "2026-10-20T14:00", "2026-10-20T15:00")], blocks: [block(3, "2026-10-20T16:00", "2026-10-20T17:00")] })
    const second: Change = { command: "add", input: { title: "Gym", when: "fixed", start: "2026-10-21T07:00", end: "2026-10-21T08:00" } }
    const view = trialView(real, out, [first, second], 1)
    expect(view.fixed.map((f) => f.id)).toEqual([700, placeholder(1)])
    expect(view.tried?.made).toEqual(new Set([700, placeholder(1)]))
    expect(view.tried?.moved.get(3)).toBe("2026-10-20T10:00") // the answer moved it
    expect(view.tried?.pending).toBe(true)
  })

  it("what an answer made for a change since put another way is drawn once, where it is now", () => {
    const real = plan()
    const was: Change = { command: "add", input: { title: "Coffee", when: "fixed", start: "2026-10-20T11:00", end: "2026-10-20T12:00" } }
    const now: Change = { command: "add", input: { title: "Coffee", when: "fixed", start: "2026-10-20T15:00", end: "2026-10-20T16:00" } }
    const out = answer([[700]], { fixed: [event(700, "Coffee", "2026-10-20T11:00", "2026-10-20T12:00")] })
    const view = trialView(real, out, [now], leading([was], [now]))
    expect(view.fixed.map((f) => [f.id, f.start])).toEqual([[placeholder(0), "2026-10-20T15:00"]])
  })

  it("an answer stands only for the changes still as it answered them", () => {
    const a: Change = { command: "drop", input: { id: 1 } }
    const b: Change = { command: "drop", input: { id: 2 } }
    expect(leading([a, b], [a, b])).toBe(2)
    expect(leading([a, b], [a])).toBe(1) // the second taken out since
    expect(leading([a, b], [b, a])).toBe(0)
    expect(leading([a], [a, b])).toBe(1) // one tried since
  })

  it("shows the part of the trial calendar in view", () => {
    const p = plan([event(1, "A", "2026-10-20T09:00", "2026-10-20T10:00")], [block(2, "2026-10-19T10:00", "2026-10-19T11:00"), block(3, "2026-10-27T10:00", "2026-10-27T11:00")])
    const seen = within({ ...p, day_hours: { "2026-10-19": 1, "2026-10-27": 1 } }, "2026-10-19T00:00", "2026-10-26T00:00")
    expect(seen.blocks).toHaveLength(1)
    expect(seen.fixed).toHaveLength(1)
    expect(seen.day_hours).toEqual({ "2026-10-19": 1 })
  })
})
