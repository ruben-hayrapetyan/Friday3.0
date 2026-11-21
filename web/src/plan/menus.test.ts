// The Plan page's header and menu against the CS 2112 UI lecture (3 Nov): "rule of 7: avoid long menus, arrays of
// buttons". The header showed eleven controls; What if, a mode, now opens from the Plan menu and shows in the header
// only while it's on. Read from the source, as there's no DOM here.
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"

const page = readFileSync(join(__dirname, "PlanPage.tsx"), "utf8")
const whatIf = readFileSync(join(__dirname, "..", "whatif", "WhatIfPanel.tsx"), "utf8")
const between = (text: string, from: string, to: string) => text.slice(text.indexOf(from), text.indexOf(to, text.indexOf(from)))
const menu = between(page, "function PlanMenu", "\n}\n")
const header = between(page, "function Header", "\n}\n")
const rows = [...menu.matchAll(/<MenuRow[^>]*label=\{?[`"]([^`"]+)[`"]/g)].map((m) => m[1])

describe("the Plan menu (glass box)", () => {
  it("has seven rows at most", () => {
    expect(rows.length).toBeGreaterThan(0)
    expect(rows.length).toBeLessThanOrEqual(7)
  })
  it("What if opens from it, and What changed is in it", () => {
    expect(rows).toContain("What if")
    expect(rows).toContain("What changed")
  })
})

describe("the header (black box)", () => {
  it("What if isn't a button there while it's off: the bar returns nothing", () => {
    expect(between(whatIf, "export function WhatIfBar", "return (")).toMatch(/if \(!w\.on\) return null/)
  })
  it("shows ten controls while What if is off, one fewer than before", () => {
    // what's drawn: buttons, menus, the view switch and the lateness note; the What if bar draws nothing while off
    const controls = header.match(/<(button|IconButton|Seg|ShowMenu|PlanMenu|BreaksButton|Attention)\b/g) ?? []
    expect(controls.length).toBe(10)
  })
})

describe("replanning (3 Nov)", () => {
  const dot = between(page, "function Replanning", "\n}\n")
  it("says the word beside the dot unless the window is narrow", () => {
    expect(dot).toMatch(/tight \? <span className="sr-only">Replanning…<\/span> : <span[^>]*>Replanning…<\/span>/)
  })
  it("every place that shows it says whether there's room", () => {
    const uses = page.match(/<Replanning\b[^>]*\/>/g) ?? []
    expect(uses.length).toBeGreaterThan(0)
    for (const u of uses) expect(u).toMatch(/tight=\{(layout\.tight|false)\}/)
  })
  // 20 Nov, the user's screenshot: with What if on and a lateness note, "Replanning…" lay over Day and 3 days. The note's
  // words give way first, then the word (web/scripts/overflow-check.mjs's "replanning" states hold it on, at each width)
  it("gives way in a full row instead of running over what's beside it", () => {
    expect(dot).toMatch(/flex: "0 1 auto", minWidth: 7, overflow: "hidden"/)
    expect(between(page, 'data-tour="attention"', "</button>")).toContain('flex: "0 100 auto"')
  })
  // 20 Nov, 320px: on a phone the bar ran 77px off the screen, Discard and Keep with it
  it("puts What if's bar on its own line under a phone's header", () => {
    expect(header).toContain("const below = layout.tight && trying")
    expect(header).toContain("{!below && <WhatIfBar")
    expect(header).toMatch(/\{below && \(\s*<div[^>]*>\s*<WhatIfBar tight \/>/)
    const shell = readFileSync(join(__dirname, "..", "shell", "Shell.tsx"), "utf8")
    expect(shell).toContain('gridTemplateRows: "minmax(60px, auto) minmax(0,1fr)"') // the header row grows for it
  })
  // 20 Nov: on phones the To-do button ran past the edge beside the lateness note (380 and 390px: the Breaks button
  // came in at 380; the row needs 384 with it, measured). The layout check's "late work" states hold the note on
  it("keeps a phone's row inside the screen with the lateness note showing", () => {
    const breaksAt = Number(page.match(/const BREAKS_BUTTON_MIN = (\d+)/)?.[1])
    expect(breaksAt).toBeGreaterThanOrEqual(392)
    expect(header).toContain('className="fr-plan-head"')
    const css = readFileSync(join(__dirname, "..", "theme", "friday.css"), "utf8")
    expect(css).toMatch(/\[data-tight\] \.fr-plan-head \.btn-icon \{\s*width: 32px;/)
  })
  it("leaves the view buttons to the Plan menu while What if's bar needs their room", () => {
    expect(header).toMatch(/const folded = layout\.tight \|\| \(trying && layout\.main < WHAT_IF_ROOM\)/)
    expect(header).toContain("{!folded && (")
    expect(header).toContain("<PlanMenu views={folded ?")
  })
})
