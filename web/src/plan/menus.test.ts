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
    const controls = header.match(/<(button|IconButton|Seg|ShowMenu|PlanMenu|DecisionsButton|Attention)\b/g) ?? []
    expect(controls.length).toBe(10)
  })
})

describe("replanning (3 Nov)", () => {
  const dot = between(page, "function Replanning", "\n}\n")
  it("says the word beside the dot unless the window is narrow", () => {
    expect(dot).toMatch(/tight \? <span className="sr-only">Replanning…<\/span> : "Replanning…"/)
  })
  it("every place that shows it says whether there's room", () => {
    const uses = page.match(/<Replanning\b[^>]*\/>/g) ?? []
    expect(uses.length).toBeGreaterThan(0)
    for (const u of uses) expect(u).toContain("tight={layout.tight}")
  })
})
