import { describe, expect, it } from "vitest"
import { inOrder } from "./order"

// 23 Nov: "organize rules based on either importance or alphabetically"; your choice: strongest first, A–Z within
// each strength. Rules switched off come last: they don't count while off.
const r = (sentence: string, strength: string, enabled = true) => ({ sentence, strength, enabled })

describe("the Rules page's order", () => {
  it("is strongest first, then A–Z, switched-off rules last", () => {
    const rules = [
      r("No work after 10pm the night before Climbing Club", "Prefer"),
      r("At least 7 h of sleep a night", "Always"),
      r("Gym between 7am and 8:30pm on weekdays", "Strongly"),
      r("Lunch and dinner are never skipped for work", "Always"),
      r("exam prep as close to the exam as possible", "Strongly"),
      r("Keep Fri, Sat 8pm–11:59pm lighter", "Always", false),
    ]
    expect(inOrder(rules).map((x) => x.sentence)).toEqual([
      "At least 7 h of sleep a night",
      "Lunch and dinner are never skipped for work",
      "exam prep as close to the exam as possible", // A–Z ignores capitals
      "Gym between 7am and 8:30pm on weekdays",
      "No work after 10pm the night before Climbing Club",
      "Keep Fri, Sat 8pm–11:59pm lighter",
    ])
  })
})
