import { describe, expect, it } from "vitest"
import { dayCard } from "./YourDay"

describe("the Inbox's link to Your day (what was Review)", () => {
  it("says the day with something to answer, and how many", () => {
    expect(dayCard({ yesterday: 3, today: 0 }).title).toBe("Yesterday: 3 to answer")
    expect(dayCard({ yesterday: 0, today: 2 }).title).toBe("Today: 2 to answer")
    expect(dayCard({ yesterday: 1, today: 2 }).title).toBe("Yesterday and today: 3 to answer")
  })
  it("stays there with nothing to answer, to change an answer", () => {
    expect(dayCard({ yesterday: 0, today: 0 })).toEqual({ title: "Your day: all answered", note: "Change an answer, or say how today went" })
  })
})
