// ⌘K finds open tasks only (3 Nov).
import { describe, expect, it } from "vitest"
import { openMatches } from "./tasks"

const t = (id: number, title: string, status = "todo") => ({ id, title, status })

describe("glass box", () => {
  it("leaves out done, deleted and skipped tasks", () => {
    const items = [t(1, "Chem chapter 9", "done"), t(2, "Chem chapter 10"), t(3, "Chem lab", "dropped"), t(4, "Chem quiz", "skipped")]
    expect(openMatches(items, "chem").map((i) => i.id)).toEqual([2])
  })
  it("a title starting with what you typed comes first, the rest in their order", () => {
    const items = [t(1, "Read chem notes"), t(2, "Chem chapter 10"), t(3, "Old chem quiz prep"), t(4, "Chemistry lab")]
    expect(openMatches(items, "chem").map((i) => i.id)).toEqual([2, 4, 1, 3])
  })
  it("nothing typed: the open ones, as listed", () => {
    expect(openMatches([t(1, "A", "done"), t(2, "B"), t(3, "C")], " ").map((i) => i.id)).toEqual([2, 3])
  })
  it("eight at most", () => {
    expect(openMatches(Array.from({ length: 20 }, (_, n) => t(n, `Task ${n}`)), "task")).toHaveLength(8)
  })
})

describe("black box", () => {
  it("done tasks never take an open one's place", () => {
    const items = [...Array.from({ length: 10 }, (_, n) => t(n, `Reading ${n}`, "done")), t(99, "Reading 99")]
    expect(openMatches(items, "reading").map((i) => i.id)).toEqual([99])
  })
  it("whatever is typed, every hit is open and matches, each once", () => {
    const items = [t(1, "Essay draft"), t(2, "essay outline", "done"), t(3, "Draft email"), t(4, "Essay", "dropped")]
    for (const typed of ["", "e", "essay", "DRAFT", "zzz"]) {
      const hits = openMatches(items, typed)
      for (const h of hits) {
        expect(h.status).toBe("todo")
        expect(h.title.toLowerCase()).toContain(typed.trim().toLowerCase())
      }
      expect(new Set(hits.map((h) => h.id)).size).toBe(hits.length)
    }
  })
})
