// The to-do drawer's list scrolls rather than squeezing its rows (glass box: todo/Drawer.tsx). 20 Nov: with a long
// list its rows could shrink, which the layout check flags; .fr-scroll-column holds them (theme/friday.css).
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"

const drawer = readFileSync(join(__dirname, "Drawer.tsx"), "utf8")

describe("the to-do drawer's list", () => {
  it("is a scrolling column whose rows keep their height", () => {
    expect(drawer).toMatch(/<div className="fr-scroll-column" style=\{\{ overflowY: "auto"/)
  })
})
