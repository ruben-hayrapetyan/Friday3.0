import { describe, expect, it } from "vitest"
import { BADGE, CARD_W, corner, HELP, mark } from "./HelpOverlay"
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

describe("the ?'s numbers", () => {
  const rect = (left: number, top: number, width: number, height: number) => ({ left, top, width, height, right: left + width, bottom: top + height, x: left, y: top, toJSON: () => ({}) }) as DOMRect

  it("number the page's own controls in reading order, the big areas last, and leave the sidebar's pages to the tour", () => {
    // 12 Nov: "everything is super cluttered and it doesn't look good": numbers and one list, not a label on everything
    const marks = mark(
      [
        { key: "calendar", rect: rect(250, 60, 1000, 700) },
        { key: "search", rect: rect(1100, 12, 30, 30) },
        { key: "views", rect: rect(900, 14, 160, 26) },
        { key: "nav-todo", rect: rect(10, 100, 180, 30) },
        { key: "settings", rect: rect(10, 10, 30, 30) },
        { key: "now", rect: rect(500, 740, 600, 60) },
      ],
      1300,
      820,
    )
    expect(marks.map((m) => [m.n, m.key])).toEqual([
      [1, "views"],
      [2, "search"],
      [3, "now"],
      [4, "calendar"],
    ])
    expect(marks.find((m) => m.key === "calendar")?.big).toBe(true)
    expect(marks.find((m) => m.key === "views")?.big).toBe(false)
  })

  it("count a wide box as a control, not an area: it's numbered in its place and lit", () => {
    const marks = mark(
      [
        { key: "now", rect: rect(500, 740, 600, 60) },
        { key: "rule-new", rect: rect(250, 150, 800, 180) },
      ],
      1300,
      820,
    )
    expect(marks.map((m) => [m.key, m.big])).toEqual([
      ["rule-new", false],
      ["now", false],
    ])
  })

  it("keep each number on screen", () => {
    const [m] = mark([{ key: "search", rect: rect(1290, 0, 30, 30) }], 1300, 820)
    expect(m.badge.left + BADGE).toBeLessThanOrEqual(1300)
    expect(m.badge.top).toBeGreaterThanOrEqual(0)
  })

  it("put the list in the bottom corner that hides fewer of them", () => {
    const low = (left: number) => mark([{ key: "drawer-add", rect: rect(left, 760, 200, 30) }], 1300, 820)
    expect(corner(low(20), 1300, 820)).toBe("right")
    expect(corner(low(1300 - CARD_W), 1300, 820)).toBe("left")
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
