// 24 Nov, the agreement check: with a calendar you hid, the Now bar said "Free until" the next visible thing's time
// beside the shorter length to the hidden meeting. The time and the length now come from one fact.
import { describe, expect, it } from "vitest"
import { freeLine } from "./Dock"

describe("the Now bar's free time", () => {
  const dentist = { start: "2026-10-19T11:00", title: "Dentist" }
  it("ends where its length does, a hidden meeting unnamed", () => {
    expect(freeLine({ free_until: "2026-10-19T09:30", next: dentist })).toEqual({ until: "2026-10-19T09:30", next: "busy" })
  })
  it("ends at what's next when nothing hidden comes first", () => {
    expect(freeLine({ free_until: "2026-10-19T11:00", next: dentist })).toEqual({ until: "2026-10-19T11:00", next: "Dentist" })
    expect(freeLine({ next: dentist })).toEqual({ until: "2026-10-19T11:00", next: "Dentist" })
    expect(freeLine({ next: null })).toEqual({ until: null, next: null })
  })
})
