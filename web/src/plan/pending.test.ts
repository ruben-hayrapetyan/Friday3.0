import { beforeEach, describe, expect, it } from "vitest"
import type { Schemas } from "@/api/client"
import { pending } from "./pending"

type Plan = Schemas["PlanOut"]
const plan = (generation: number, start = "2026-10-20T10:00") =>
  ({ plan_id: 1, generation, blocks: [{ key: `T3@${start}`, item_id: 3, title: "Essay", start, end: "2026-10-20T11:00" }], fixed: [], day_hours: {}, sessions: [] }) as unknown as Plan
const moveTo = (start: string) => (p: Plan) => ({ ...p, blocks: p.blocks.map((b) => ({ ...b, start })) })

describe("a change shown until the plan has it", () => {
  beforeEach(() => pending.clear())

  it("is drawn at once, over every plan that hasn't seen it, and goes once one has", () => {
    const ids = pending.collect(() => pending.add(moveTo("2026-10-21T15:00")))
    expect(pending.apply(plan(4)).blocks[0].start).toBe("2026-10-21T15:00") // on its way
    pending.settle(ids, 5)
    expect(pending.apply(plan(4)).blocks[0].start).toBe("2026-10-21T15:00") // the refresh before its placement
    expect(pending.apply(plan(5, "2026-10-21T15:00")).blocks[0].start).toBe("2026-10-21T15:00") // the plan has it
    pending.forget(5)
    expect(pending.apply(plan(4)).blocks[0].start).toBe("2026-10-20T10:00")
  })

  it("is taken back when the change fails", () => {
    const ids = pending.collect(() => pending.add(moveTo("2026-10-21T15:00")))
    pending.drop(ids)
    expect(pending.apply(plan(4)).blocks[0].start).toBe("2026-10-20T10:00")
  })

  it("lays changes over each other in the order made", () => {
    pending.settle(pending.collect(() => pending.add(moveTo("2026-10-21T15:00"))), 5)
    pending.settle(pending.collect(() => pending.add(moveTo("2026-10-22T09:00"))), 6)
    expect(pending.apply(plan(4)).blocks[0].start).toBe("2026-10-22T09:00")
    pending.forget(5)
    expect(pending.apply(plan(5)).blocks[0].start).toBe("2026-10-22T09:00") // the later one still on its way
  })

  it("collects only what its change adds", () => {
    pending.add(moveTo("2026-10-21T15:00"))
    expect(pending.collect(() => undefined)).toEqual([])
  })
})
