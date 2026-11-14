import { describe, expect, it } from "vitest"
import type { Block, Item } from "@/api/client"
import { addHint, fillFor, grouped, plural, progress } from "./groups"

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

  it("groups by kind in personal's order, the empty buckets kept for their add lines, the rest last", () => {
    const items = [item(1, { preset: "Project" }), item(2, { preset: "Assignment" }), item(3, {}), item(4, { preset: "Reading" })]
    const groups = grouped(items, [], "2026-10-19", "Kind", "Title", ["Reading", "Assignment", "Errand", "Other"])
    expect(groups.map((g) => [g.name, g.items.map((i) => i.id)])).toEqual([
      ["Reading", [4]],
      ["Assignment", [2]],
      ["Errand", []],
      ["Project", [1]],
      ["Other", [3]],
    ])
  })

  it("says what each add line fills in", () => {
    expect([fillFor("Kind", "Reading"), fillFor("Kind", "Other"), fillFor("Tag", "cs"), fillFor("When", "Today")]).toEqual([{ preset: "Reading" }, {}, { area: "cs" }, null])
    expect(["Reading", "Assignment", "Errand", "Exam prep", "Other"].map((n) => addHint("Kind", n))).toEqual([
      "Add a reading…",
      "Add an assignment…",
      "Add an errand…",
      "Add exam prep…",
      "Add anything else…",
    ])
    expect(["Reading", "Exam prep", "Other", "Homework"].map(plural)).toEqual(["Readings", "Exam prep", "Other", "Homework"])
  })

  it("reads progress as done of total", () => {
    expect(progress(item(1, { done_min: 120, remaining_min: 240 }))).toEqual({ pct: 33, text: "2h of 6h" })
    expect(progress(item(2, { amount: "open" })).text).toBe("Fills free time")
  })
})

describe("a project in the to-do list", () => {
  // 13 Nov: no blocks of its own, it went by its due, after the work its steps had planned sooner
  it("goes where its steps are planned, though they're in another list", () => {
    const project = item(10, { title: "CDJ Article", due: "2026-11-23T17:00" })
    const step = item(11, { parent_id: 10, long_term: true })
    const blocks = [{ item_id: 11, start: "2026-11-14T12:15", end: "2026-11-14T13:15", key: "", title: "" }] as Block[]
    const [today] = grouped([project], blocks, "2026-11-14", "When", "Next up", [], [project, step]).filter((g) => g.items.length)
    expect([today.name, today.items.map((i) => i.id)]).toEqual(["Today", [10]])
    // without the steps to look at, it went by its due: next week, "Later"
    expect(grouped([project], blocks, "2026-11-14", "When", "Next up").find((g) => g.items.length)?.name).toBe("Later")
  })
})
