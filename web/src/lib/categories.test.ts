// Merging one category into another, from Settings → Calendars (3 Nov: `category_merge` had no button).
import { describe, expect, it } from "vitest"
import { mergeTargets } from "./categories"

const saved = (...names: string[]) => ({ categories: names.map((name) => ({ name })) })

describe("glass box", () => {
  it("offers the others, in your order", () => {
    expect(mergeTargets(saved("Class", "Social", "Meals"), "Social")).toEqual(["Class", "Meals"])
  })
  it("never itself, a blank or one twice", () => {
    expect(mergeTargets(saved("Class", "", "Class", "Social"), "Social")).toEqual(["Class"])
  })
  it("a category not saved yet has nothing to merge into", () => {
    expect(mergeTargets(saved("Class", "Social"), "New category")).toEqual([])
  })
})

describe("black box", () => {
  it("with one category there's nothing to merge", () => {
    expect(mergeTargets(saved("Class"), "Class")).toEqual([])
  })
  it("whatever the list, the choices are saved categories other than this one", () => {
    const lists = [["A", "B"], ["A", "A", "B", "C"], ["Only"], ["x", " y ", "z"]]
    for (const names of lists) {
      for (const name of names) {
        const out = mergeTargets(saved(...names), name)
        expect(out).not.toContain(name.trim())
        for (const n of out) expect(names.map((m) => m.trim())).toContain(n)
        expect(new Set(out).size).toBe(out.length)
      }
    }
  })
})
