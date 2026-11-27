import { describe, expect, it } from "vitest"
import { likelyTask, likeness, ranked, openAt, wholeDay } from "./holds"

const tasks = [
  { id: 55, title: "CS A4 Design Doc" },
  { id: 56, title: "CS A4 Complete" },
  { id: 70, title: "Chem Regrade Request" },
  { id: 71, title: "Math 1920 HW9" },
  { id: 72, title: "Psych reading" },
]

describe("which task an event's time is for", () => {
  it("A4dd is the A4 design doc: A4, and dd for design doc (27 Oct)", () => {
    expect(likelyTask("A4dd", tasks)?.id).toBe(55)
    expect(likeness("A4dd", "CS A4 Design Doc")).toBeGreaterThan(likeness("A4dd", "CS A4 Complete"))
  })

  it("plain words and course numbers find theirs", () => {
    expect(likelyTask("Work on Math 1920 HW9", tasks)?.id).toBe(71)
    expect(likelyTask("chem regrade", tasks)?.id).toBe(70)
  })

  it("asks about none when nothing fits, or two fit as well", () => {
    expect(likelyTask("Dinner with Sam", tasks)).toBeNull()
    expect(likelyTask("A4", tasks)).toBeNull() // both A4 tasks, equally
    expect(likelyTask("A4dd", [])).toBeNull()
  })

  it("offers every task, the likeliest first", () => {
    expect(ranked("A4dd", tasks).map((t) => t.id).slice(0, 2)).toEqual([55, 56])
    expect(ranked("A4dd", tasks)).toHaveLength(tasks.length)
  })
})

// 27 Nov, a user's notes ("Friday Notes-3"): a birthday, all day, asked "Is this time for TC/HS Detection?", a task due
// before it at that.
describe("a whole day isn't a task's time", () => {
  it("is midnight to midnight, one day or several; never a timed event, one at midnight included", () => {
    expect(wholeDay({ start: "2026-11-24T00:00", end: "2026-11-25T00:00" })).toBe(true)
    expect(wholeDay({ start: "2026-11-24T00:00", end: "2026-11-27T00:00" })).toBe(true) // a trip, several days
    expect(wholeDay({ start: "2026-11-24T09:00", end: "2026-11-24T10:00" })).toBe(false)
    expect(wholeDay({ start: "2026-11-24T00:00", end: "2026-11-24T01:00" })).toBe(false) // starts at midnight, an hour
    expect(wholeDay({ start: "2026-11-24T00:00", end: "2026-11-24T00:00" })).toBe(false) // no length
    expect(wholeDay({ start: null, end: null })).toBe(false)
  })
  it("offers only tasks still to do when it starts: no due, or due at it or later", () => {
    const tasks = [
      { id: 1, due: null },
      { id: 2, due: "2026-11-20T23:59" }, // due before: its time would only make it late
      { id: 3, due: "2026-11-24T09:00" }, // due as it starts
      { id: 4, due: "2026-12-01T17:00" },
    ]
    expect(openAt(tasks, "2026-11-24T09:00").map((t) => t.id)).toEqual([1, 3, 4])
    expect(openAt(tasks, null).map((t) => t.id)).toEqual([1, 2, 3, 4]) // no start: none left out
  })
})
