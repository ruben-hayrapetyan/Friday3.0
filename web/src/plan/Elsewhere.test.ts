import { describe, expect, it } from "vitest"
import { movedEnd, nowhere } from "./Elsewhere"

const answer = (more: object) => ({ key: "T1@2026-10-19T09:00", to_start: null, wall: null, difference: {}, total: 0, ...more })

describe("Try elsewhere's answer", () => {
  it("says a block under way, or being timed, as Friday words it, not that nowhere else is better", () => {
    const note = "It's under way, so there's nothing of it left to move. Not doing it now? Drag it to a later time."
    expect(nowhere(answer({ note }))).toBe(note)
  })

  it("says what keeps it where it is, or that nowhere else is better", () => {
    expect(nowhere(answer({ wall: "Lunch goes between 11:30am and 2:30pm, around CHEM 2090 Lecture" }))).toBe(
      "Nowhere else it can go (Lunch goes between 11:30am and 2:30pm, around CHEM 2090 Lecture).",
    )
    expect(nowhere(answer({}))).toBe("Nowhere else is better.")
  })

  it("moves what's left of a block under way, as long as Friday says, else the block's length", () => {
    expect(movedEnd(answer({ to_start: "2026-10-19T09:45", to_end: "2026-10-19T10:15" }), 45)).toBe("2026-10-19T10:15")
    expect(movedEnd(answer({ to_start: "2026-10-19T09:45" }), 45)).toBe("2026-10-19T10:30")
  })
})
