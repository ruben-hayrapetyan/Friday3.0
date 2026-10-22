import { describe, expect, it } from "vitest"
import type { Item } from "@/api/client"
import { grouped, progress } from "./groups"

const item = (id: number, over: Partial<Item>): Item =>
  ({
    id, title: `t${id}`, preset: null, area: null, tags: [], parent_id: null, when: "window", start: null, end: null,
    release: null, due: null, amount: "fixed", duration_min: 60, firmness: "hard", importance: 3, energy: null,
    shape: "split", certainty: "sure", status: "todo", series_id: null, done_min: 0, remaining_min: 60, ...over,
  }) as Item // prettier-ignore

describe("to-do groups", () => {
  it("groups by tag with untagged together and done last, sorted by due", () => {
    const items = [
      item(1, { area: "cs", due: "2026-10-22T17:00" }),
      item(2, { area: "cs", due: "2026-10-20T17:00" }),
      item(3, {}),
      item(4, { area: "cs", status: "done" }),
    ]
    const groups = grouped(items, [], "2026-10-19", "Tag", "Due date")
    expect(groups.map((g) => [g.name, g.items.map((i) => i.id)])).toEqual([
      ["cs", [2, 1]],
      ["No tag", [3]],
      ["Done", [4]],
    ])
  })

  it("reads progress as done of total", () => {
    expect(progress(item(1, { done_min: 120, remaining_min: 240 }))).toEqual({ pct: 33, text: "2h of 6h" })
    expect(progress(item(2, { amount: "open" })).text).toBe("Fills free time")
  })
})
