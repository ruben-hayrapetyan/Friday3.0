import { describe, expect, it } from "vitest"
import { likelyTask, likeness, ranked } from "./holds"

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
