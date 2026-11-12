import { describe, expect, it } from "vitest"
import { HELP, place } from "./HelpOverlay"
import { CARD, homeOf, STOPS, standFor } from "./Tour"

describe("the tour", () => {
  it("is one stop per page, each saying what it's for, short enough to read at a glance", () => {
    // 12 Nov: "walk through each of the tabs and explain what it is for ... a tour not a list of tasks"
    expect(STOPS.map((s) => s.id)).toEqual(["plan", "todo", "projects", "inbox", "insights", "rules", "settings", "end"])
    for (const s of STOPS) expect(s.body.length).toBeLessThanOrEqual(160)
  })

  it("tells a new user what they got wrong first: work is a to-do, meals come from setup, rules in your words", () => {
    const said = STOPS.map((s) => `${s.body} ${s.tip ?? ""}`).join(" ")
    expect(said).toMatch(/Work is a to-do, not an event/)
    expect(said).toMatch(/no need to make Breakfast, Lunch or Dinner events/)
    expect(said).toMatch(/no work after 10pm/)
  })

  it("points at things the help labels too", () => {
    for (const s of STOPS) expect(HELP[s.target] ?? s.target).toBeTruthy()
  })
})

describe("the ?'s labels", () => {
  const rect = (left: number, top: number, width: number, height: number) => ({ left, top, width, height, right: left + width, bottom: top + height, x: left, y: top, toJSON: () => ({}) }) as DOMRect

  it("sit beside their control, on the side with room, and clear of each other", () => {
    const labels = place(
      [
        { key: "search", rect: rect(900, 10, 30, 30) },
        { key: "views", rect: rect(900, 14, 200, 24) },
        { key: "nav-todo", rect: rect(10, 100, 180, 30) },
      ],
      1200,
      800,
    )
    const by = Object.fromEntries(labels.map((l) => [l.key, l]))
    expect(by["nav-todo"].side).toBe("right")
    expect(by.views.side).toBe("left") // no room to its right
    expect(by.search.at.left).toBeGreaterThan(930)
    const [a, b] = [by.search, by.views]
    const overlap = a.at.left < b.at.left + 230 && a.at.left + 230 > b.at.left && a.at.top < b.at.top + 44 && a.at.top + 44 > b.at.top
    expect(overlap).toBe(false)
  })

  it("go inside a big area, not off the edge", () => {
    const [cal] = place([{ key: "calendar", rect: rect(250, 80, 1000, 700) }], 1300, 820)
    expect(cal.side).toBe("inside")
    expect(cal.at.top + 44).toBeLessThanOrEqual(820)
  })
})

describe("where the guide stands", () => {
  const win = 1440

  it("by the card, left of it, in the bottom-right corner", () => {
    expect(homeOf(win)).toBeLessThan(win - CARD - 16)
    expect(homeOf(win)).toBeGreaterThan(win - CARD - 140)
  })

  it("below what they show you, never under the card", () => {
    expect(standFor({ left: 100, width: 200 }, win)).toBe(200)
    expect(standFor({ left: 0, width: 20 }, win)).toBeGreaterThanOrEqual(60)
    expect(standFor({ left: 1350, width: 60 }, win)).toBe(homeOf(win))
  })
})
