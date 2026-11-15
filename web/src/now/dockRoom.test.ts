import { describe, expect, it } from "vitest"
import { covered, dockRoom } from "./dockRoom"

describe("the room a page leaves for the Now bar", () => {
  it("is the page's own room, or the bar's height and a little more while it's taller", () => {
    expect(dockRoom(80)).toBe("max(80px, calc(var(--fr-dock, 0px) + 24px))")
  })
  it("counts from the bar's top to the window's foot, and nothing once the bar is gone", () => {
    expect(covered(700, 900)).toBe(200)
    expect(covered(null, 900)).toBe(0)
    expect(covered(950, 900)).toBe(0)
  })
})

describe("every page's scrolling column under the Now bar", () => {
  // 15 Nov: each had a fixed foot (40–150px) the bar outgrew with its sleep and meal rows up
  const pages = ["inbox/InboxPage.tsx", "inbox/Pane.tsx", "todo/TodoPage.tsx", "todo/TodoDetail.tsx", "projects/ProjectsPage.tsx", "projects/ProjectDetail.tsx", "insights/InsightsPage.tsx", "insights/WeeklyReview.tsx", "body/BodyPage.tsx", "rules/RulesPage.tsx", "lab/rules/shared.tsx", "plan/Grid.tsx", "plan/DayAside.tsx", "plan/MonthView.tsx"]
  const sources = import.meta.glob("../**/*.tsx", { query: "?raw", import: "default", eager: true }) as Record<string, string>
  it.each(pages)("%s leaves the bar's room at its foot", (page) => {
    const source = sources[`../${page}`]
    expect(source).toBeDefined()
    expect(source).toContain("dockRoom(")
    expect(source).not.toMatch(/padding: "\d+px \d+px (1\d\d|[4-9]0)px"|paddingBottom: (1\d\d|[4-9]0)\b/)
  })
})
