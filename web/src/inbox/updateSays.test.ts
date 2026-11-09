import { describe, expect, it } from "vitest"
import { updateSays } from "./updateSays"

const today = "2026-11-09"
const yours = { title: "Chem 2090 Problem Set 11", due: "2026-11-11T23:59", duration_min: 150 }

describe("what Update it says it changes", () => {
  it("names the new due date and that your name stays", () => {
    const said = updateSays({ title: "PS11", due: "2026-11-16T23:59" }, yours, today)
    expect(said).toMatch(/^Accepting makes it due /)
    expect(said).toContain("“Chem 2090 Problem Set 11” keeps its name")
    expect(said).not.toContain("PS11")
  })

  it("names a new length", () => {
    expect(updateSays({ duration_min: 240 }, yours, today)).toContain("4h long")
  })

  it("says when nothing changes", () => {
    expect(updateSays({ title: "PS11", due: "2026-11-11T23:59", duration_min: 150 }, yours, today)).toBe(
      "Nothing about it changes; “Chem 2090 Problem Set 11” keeps its name.",
    )
  })
})
