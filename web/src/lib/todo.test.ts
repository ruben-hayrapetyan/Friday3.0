import { describe, expect, it } from "vitest"
import type { Block, Item } from "@/api/client"
import { nextOccurrences, nextBlocks, sections } from "./todo"

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
