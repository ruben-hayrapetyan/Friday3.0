// Glass box: the Projects page's popup (projects-v2/Rows.tsx Popup), where a project, an exam and an ongoing project
// open (17 Nov: "i think everything should be a center popup rather than a sidebar or its own page"). Where its top
// sits, Escape leaving it for an open dropdown first, and that it stands above the Now bar and the page's own layers.
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"
import { menuOpenIn, POPUP, popupTop } from "./Rows"

const sources = import.meta.glob(["/src/**/*.tsx"], { query: "?raw", import: "default", eager: true }) as Record<string, string>
const stylesheet = readFileSync(join(__dirname, "../theme/friday.css"), "utf8") // vitest hands CSS imports over empty
const zOf = (css: string, cls: string) => Number(new RegExp(`\\.${cls} \\{[^}]*z-index: (\\d+)`).exec(css)?.[1])

describe("the Projects page's popup", () => {
  it("sits where one its usual height would sit centered, never nearer the top than its margin", () => {
    expect(popupTop(860, 24)).toBe("max(24px, calc((100vh - 860px) / 2))")
  })

  it("is wide enough for a project's steps and timeline, narrower for an exam or an ongoing project", () => {
    expect(POPUP.project.width).toBeGreaterThanOrEqual(960)
    expect(POPUP.panel.width).toBeLessThan(POPUP.project.width)
    expect(POPUP.panel.width).toBeGreaterThanOrEqual(480) // never narrower than the side panel it replaced
  })

  it("leaves Escape to a dropdown open in it (a length, a date, a menu), and takes it otherwise", () => {
    const asked: string[] = []
    const box = (open: boolean) => ({ querySelector: (s: string) => (asked.push(s), open ? {} : null) }) as unknown as HTMLElement
    expect(menuOpenIn(box(true))).toBe(true)
    expect(menuOpenIn(box(false))).toBe(false)
    expect(menuOpenIn(null)).toBe(false)
    expect(asked[0]).toBe(".fr-menu [aria-expanded='true']") // a dropdown's button, open; not a setting row's
  })

  it("stands above the Now bar and the page's own layers, so nothing covers its buttons", () => {
    const css = stylesheet
    const scrim = zOf(css, "fr-scrim")
    const dock = Number(/zIndex: (\d+)/.exec(sources["/src/now/Dock.tsx"])?.[1])
    expect(scrim).toBeGreaterThan(dock)
    for (const file of ["/src/projects-v2/ProjectsV2Page.tsx", "/src/projects-v2/Deadlines.tsx", "/src/projects-v2/Ongoing.tsx", "/src/projects/ProjectDetail.tsx", "/src/projects/Timeline.tsx"])
      for (const [, z] of sources[file].matchAll(/zIndex: (\d+)/g)) expect(Number(z)).toBeLessThan(scrim)
    // its dropdowns over it, and the toasts with Undo over those
    expect(zOf(css, "fr-menu-list")).toBeGreaterThan(scrim)
    expect(Number(/zIndex: (\d+)/.exec(sources["/src/components/Toasts.tsx"])?.[1])).toBeGreaterThan(scrim)
  })

  it("is drawn over the whole window, outside the page's panel, and nothing on the page is a side panel any more", () => {
    const page = sources["/src/projects-v2/ProjectsV2Page.tsx"]
    expect(page.indexOf("<Popup")).toBeGreaterThan(page.indexOf("<Finished")) // after the shelves' panel has closed
    for (const file of ["/src/projects-v2/ProjectsV2Page.tsx", "/src/projects-v2/Rows.tsx"]) {
      expect(sources[file]).not.toContain("SidePanel")
      expect(sources[file]).not.toContain("<aside")
    }
  })

  it("has no page back-link in a project: its close is the popup's", () => {
    const detail = sources["/src/projects/ProjectDetail.tsx"]
    expect(detail).not.toContain("onBack")
    expect(detail).not.toContain("arrow-left")
  })
})
