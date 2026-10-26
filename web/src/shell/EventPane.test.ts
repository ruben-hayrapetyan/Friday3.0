import { describe, expect, it } from "vitest"
import { hasWords } from "./EventPane"

describe("an event named in a rule", () => {
  it("matches the rule's words as words, in any case", () => {
    expect(hasWords("Gym with Sam", "gym")).toBe(true)
    expect(hasWords("Climbing Club (Wed)", "climbing club")).toBe(true)
    expect(hasWords("Open lab", "pe")).toBe(false)
    expect(hasWords("Gymnastics", "gym")).toBe(false)
    expect(hasWords("C++ review", "c++")).toBe(true)
  })
})
