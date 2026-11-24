// 23 Nov, the agreement check (web/scripts/agreement-check.mjs): a project whose steps had time said "Nothing planned.
// Friday will find time once it has a due date or an estimate." though it had both.
import { describe, expect, it } from "vitest"
import { nothingPlanned, sessionWords } from "./TodoDetail"

describe("an item's planned sessions", () => {
  it("names a project's sessions by their step", () => {
    expect(sessionWords({ item_id: 7, title: "Build the arm" }, 3)).toBe("Build the arm · Friday decides")
    expect(sessionWords({ item_id: 7, title: "Build the arm", pinned: "locked" }, 3)).toBe("Build the arm · won’t move")
    expect(sessionWords({ item_id: 3, title: "Robotics demo" }, 3)).toBe("Planned · Friday decides")
  })
  it("says why nothing is planned in the plan's words", () => {
    expect(nothingPlanned("Waits for “Design the arm”, which has no room before its due", { due: "2026-10-23T17:00", duration_min: 60 }))
      .toBe("Nothing planned: waits for “Design the arm”, which has no room before its due.")
    expect(nothingPlanned(null, { due: "2026-10-23T17:00", duration_min: 600 })).toBe("Nothing planned yet.")
    expect(nothingPlanned(null, {})).toBe("Nothing planned. Friday will find time once it has a due date or an estimate.")
  })
})
