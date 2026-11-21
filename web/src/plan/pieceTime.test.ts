// A short piece's time, on its one line after the title (glass box: plan/Pieces.tsx's Inline). 20 Nov, 320px, the 3-day
// view: it couldn't shrink, and the piece's box cut it mid-letter, "9:30an". It gives way after the title, with an
// ellipsis, like the title does.
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"

const pieces = readFileSync(join(__dirname, "Pieces.tsx"), "utf8")
const inline = pieces.slice(pieces.indexOf("function Inline("), pieces.indexOf("\n}\n", pieces.indexOf("function Inline(")))

describe("a short piece's time", () => {
  it("shrinks with an ellipsis in a narrow column instead of being cut", () => {
    expect(inline).toContain('flex: "0 1 auto"')
    expect(inline).toContain("minWidth: 0")
    expect(inline).toContain('textOverflow: "ellipsis"')
    expect(inline).not.toContain('flex: "none"')
  })
})
