// The Now bar's "Another dinner" (glass box): offered from the meals query's `again`, and never while you're eating.
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"

const breaks = readFileSync(join(__dirname, "breaks.ts"), "utf8")
const dock = readFileSync(join(__dirname, "Dock.tsx"), "utf8")

describe("another of the meal you last had", () => {
  it("is offered only with tracking on, not eating, and a meal had today", () => {
    expect(breaks).toMatch(/again: meals\?\.on && !meals\.eating && meals\.again \?/)
  })
  it("comes first in the Now bar's free-time links, so Nap and Snack keep their places", () => {
    expect(dock.indexOf("breaks.again &&")).toBeGreaterThan(-1)
    expect(dock.indexOf("breaks.again &&")).toBeLessThan(dock.indexOf("breaks.nap &&"))
  })
})
