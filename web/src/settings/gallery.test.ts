import { describe, expect, it } from "vitest"
import { CATALOG, CATEGORIES, folded, grouped, search } from "./gallery"

const names = (list: { name: string }[]) => list.map((e) => e.name)

describe("the integrations gallery's catalog", () => {
  it("has every entry ready to show: a unique id, a name, one line, a category, an icon and colour", () => {
    expect(new Set(CATALOG.map((e) => e.id)).size).toBe(CATALOG.length)
    for (const e of CATALOG) {
      expect(e.name.length).toBeGreaterThan(1)
      expect(e.line.length).toBeGreaterThan(10)
      expect(e.line.length).toBeLessThan(80) // one line in a box
      expect(CATEGORIES).toContain(e.category)
      expect(e.icon).toMatch(/^[a-z-]+$/)
      expect(e.hue).toMatch(/^#[0-9a-f]{6}$/i)
    }
  })
  it("says, for each one connected by token, where the token is and how to get it", () => {
    for (const e of CATALOG.filter((x) => x.token)) {
      expect(e.token!.page).toMatch(/^https:\/\//)
      expect(e.token!.steps.length).toBeGreaterThanOrEqual(2)
    }
    expect(CATALOG.find((e) => e.id === "todoist")?.token?.page).toContain("todoist.com")
  })
})

describe("searching the gallery", () => {
  it("finds by name, from the start of any word, whatever the case", () => {
    expect(names(search(CATALOG, "todo"))[0]).toBe("Todoist")
    expect(names(search(CATALOG, "GMAIL"))).toEqual(["Gmail"])
    expect(names(search(CATALOG, "upload"))).toContain("Syllabus upload")
  })
  it("finds by the other names people use", () => {
    expect(names(search(CATALOG, "claude"))).toEqual(expect.arrayContaining(["AI", "Ask the AI"]))
    expect(names(search(CATALOG, "canvas"))).toEqual(expect.arrayContaining(["Calendar links", "Syllabus upload"]))
    expect(names(search(CATALOG, "icloud"))).toContain("Calendars on this Mac")
  })
  it("needs every word to match, and puts a name that starts with them first", () => {
    expect(names(search(CATALOG, "google calendar"))[0]).toBe("Google Calendar")
    expect(search(CATALOG, "gmail todoist")).toEqual([])
  })
  it("matches the start of words, not the middle", () => {
    expect(names(search(CATALOG, "ist"))).not.toContain("Todoist")
  })
  it("shows everything for an empty search, nothing for nonsense, and never breaks on punctuation", () => {
    expect(search(CATALOG, "  ")).toHaveLength(CATALOG.length)
    expect(search(CATALOG, "zzqx")).toEqual([])
    expect(search(CATALOG, "(.*")).toHaveLength(CATALOG.length) // punctuation alone is no search, and no pattern
    expect(search(CATALOG, "todo(")).toEqual(search(CATALOG, "todo"))
  })
  it("ignores accents", () => {
    expect(folded("Calendrié")).toBe("calendrie")
  })
})

describe("the gallery's layout", () => {
  it("puts what you've connected first, then each category in order, with none twice and no empty sections", () => {
    const { connected, sections } = grouped(CATALOG, new Set(["todoist", "gmail"]))
    expect(names(connected)).toEqual(["Gmail", "Todoist"])
    const shown = sections.flatMap(([, list]) => list)
    expect(shown.find((e) => e.id === "todoist")).toBeUndefined()
    expect(shown.length + connected.length).toBe(CATALOG.length)
    expect(sections.map(([c]) => c)).toEqual(CATEGORIES.filter((c) => sections.some(([s]) => s === c)))
    expect(sections.every(([, list]) => list.length > 0)).toBe(true)
  })
})
