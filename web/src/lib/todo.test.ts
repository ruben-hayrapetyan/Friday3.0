import { describe, expect, it } from "vitest"
import type { Block, Item } from "@/api/client"
import { nextBlocks, nextOccurrences, projectOf, sections } from "./todo"

const item = (id: number, extra: Partial<Item> = {}): Item =>
  ({ id, title: `T${id}`, amount: "fixed", due: null, waiting_on: [], ...extra }) as Item
const block = (item_id: number, start: string): Block => ({ item_id, start, end: start, key: "", title: "" }) as Block

describe("to-do sections", () => {
  it("follow the next planned block, then the due, then Someday", () => {
    const out = sections(
      [
        item(1),
        item(2, { due: "2026-10-23T17:00" }),
        item(7, { due: "2026-10-30T17:00" }),
        item(3, { due: "2026-11-30T17:00" }),
        item(4),
        item(5, { amount: "open" }),
        item(6, { waiting_on: [1] }),
      ],
      [block(1, "2026-10-21T10:00"), block(1, "2026-10-19T10:00"), block(3, "2026-10-19T15:00")],
      "2026-10-19",
    )
    const ids = Object.fromEntries(Object.entries(out).map(([k, v]) => [k, v.map((r) => r.item.id)]))
    expect(ids).toEqual({
      Today: [1, 3],
      "This week": [2],
      Later: [7],
      Someday: [4],
      Ongoing: [5],
      "Waiting on": [6],
    })
  })
})

describe("repeating items", () => {
  it("show their next occurrence with a count of the rest", () => {
    const gym = [item(8, { series_id: 1, release: "2026-10-23T04:00" }), item(6, { series_id: 1, release: "2026-10-19T04:00" })]
    const rows = nextOccurrences([item(1), ...gym], nextBlocks([]))
    expect(rows.map((r) => [r.item.id, r.more])).toEqual([[1, 0], [6, 1]])
  })
})

describe("a project's next block", () => {
  // 13 Nov: a project has no blocks of its own (the planner plans its steps), so its row read "not planned" while its
  // steps were planned days before its due
  const project = item(10, { title: "CDJ Article", due: "2026-11-16T17:00" })
  const outline = item(11, { parent_id: 10 })
  const draft = item(12, { parent_id: 10 })
  const chart = item(13, { parent_id: 12 }) // a step inside a step
  const steps = [block(12, "2026-11-14T15:00"), block(11, "2026-11-14T12:15"), block(13, "2026-11-15T09:00")]

  it("is the soonest of its steps', nested ones included", () => {
    const next = nextBlocks(steps, [project, outline, draft, chart])
    expect(next.get(10)?.start).toBe("2026-11-14T12:15")
    expect(next.get(12)?.start).toBe("2026-11-14T15:00") // a step keeps its own, not its sub-step's later one
    expect(next.get(11)?.item_id).toBe(11)
  })

  it("is nothing when its steps aren't planned, or without the items to say whose steps they are", () => {
    expect(nextBlocks([], [project, outline]).get(10)).toBeUndefined()
    expect(nextBlocks(steps).get(10)).toBeUndefined()
  })

  it("puts the project in the section its steps are planned in", () => {
    const out = sections([project, outline], steps.slice(1, 2), "2026-11-14")
    expect(out.Today.map((r) => r.item.id)).toEqual([10, 11])
  })
})

describe("the project an item is a step of", () => {
  it("is its parent among the items, or nothing", () => {
    const items = [item(10), item(11, { parent_id: 10 }), item(12, { parent_id: 99 })]
    expect(projectOf(items[1], items)?.id).toBe(10)
    expect(projectOf(items[0], items)).toBeUndefined()
    expect(projectOf(items[2], items)).toBeUndefined() // a project not in the list (done)
  })
})
