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

describe("the boxes for services connected by their calendar link (C96)", () => {
  const links = CATALOG.filter((e) => e.link)
  it("are the eight you chose, each with its own help page and steps, saying what Friday does with it", () => {
    expect(links.map((e) => e.id).sort()).toEqual(["7shifts", "blackboard", "brightspace", "deputy", "moodle", "schoology", "sling", "wheniwork"])
    for (const e of links) {
      expect(e.link!.help).toMatch(/^https:\/\//)
      expect(e.link!.steps.length).toBeGreaterThanOrEqual(3)
      expect(e.link!.reads.length).toBeGreaterThan(20)
    }
  })
  it("puts school systems under School and shift apps under Work schedules", () => {
    expect(CATALOG.filter((e) => e.category === "Work schedules").map((e) => e.id).sort()).toEqual(["7shifts", "deputy", "homebase", "sling", "wheniwork"])
    expect(["blackboard", "moodle", "brightspace", "schoology"].every((id) => CATALOG.find((e) => e.id === id)?.category === "School")).toBe(true)
  })
  it("says how Homebase reaches Friday, as it gives no link", () => {
    const homebase = CATALOG.find((e) => e.id === "homebase")!
    expect(homebase.link).toBeUndefined()
    expect(homebase.viaMac!.steps.join(" ")).toContain("Calendars on this Mac")
  })
  it("are found by the names people use", () => {
    expect(names(search(CATALOG, "d2l"))).toEqual(["Brightspace"])
    expect(names(search(CATALOG, "shifts"))).toEqual(expect.arrayContaining(["When I Work", "Deputy", "7shifts", "Sling", "Homebase"]))
    expect(names(search(CATALOG, "roster"))).toEqual(["Deputy"])
  })
})

describe("the boxes for mail by app password (C99)", () => {
  const mail = CATALOG.filter((e) => e.mail)
  it("are iCloud, Yahoo, Fastmail and other IMAP, under Mail, each with its steps", () => {
    expect(mail.map((e) => e.mail!.provider).sort()).toEqual(["fastmail", "icloud", "other", "yahoo"])
    expect(mail.every((e) => e.category === "Mail" && e.mail!.steps.length >= 3)).toBe(true)
    expect(mail.filter((e) => e.mail!.help).every((e) => e.mail!.help!.startsWith("https://"))).toBe(true)
  })
  it("leave Outlook out: Microsoft refuses app passwords for its mail", () => {
    expect(names(search(CATALOG, "outlook")).some((n) => /Outlook/.test(n))).toBe(false)
  })
  it("are found by the names people use", () => {
    expect(names(search(CATALOG, "me.com"))).toEqual(["iCloud Mail"])
    expect(names(search(CATALOG, "imap"))).toContain("Other mail (IMAP)")
  })
})
