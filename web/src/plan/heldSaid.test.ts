import { describe, expect, it } from "vitest"
import { heldSaid } from "./BlockPopover"

// 23 Nov, a test user's screenshot: a class under "Work through it" said "Time for Final Presentations: Planned here
// first" while the plan had it the next afternoon and called it late. The panel says what the plan did.
describe("an event's held task, as the plan has it", () => {
  const today = "2026-11-23"
  it("its time here, when the plan put it here", () => {
    expect(heldSaid({ here: ["2026-11-30T09:05", "2026-11-30T10:00"] }, true, today)).toBe("Planned here, 9:05am–10am; any work can have the rest.")
    expect(heldSaid({ here: ["2026-11-30T09:05", "2026-11-30T10:00"] }, false, today)).toBe("Planned here, 9:05am–10am; other work keeps off the rest.")
  })
  it("where it is instead, when the plan put it elsewhere", () => {
    expect(heldSaid({ elsewhere: "2026-12-01T15:00" }, true, today)).toBe("Not planned here: Friday has it Tue 1 Dec 3pm.")
    expect(heldSaid({ elsewhere: null }, true, today)).toBe("Not planned here, and not planned anywhere yet.")
  })
  it("never 'Planned here first' when the plan says otherwise", () => {
    expect(heldSaid({ elsewhere: "2026-12-01T15:00" }, true, today)).not.toMatch(/Planned here/)
  })
  it("before the plan has answered, the rule, not a placement (24 Nov, the agreement check)", () => {
    expect(heldSaid({}, true, today)).toBe("Friday tries it here first; any work can have the rest.")
    expect(heldSaid({}, false, today)).toBe("Friday tries it here first; other work keeps off it.")
  })
})
