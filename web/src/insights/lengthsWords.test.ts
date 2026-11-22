import { describe, expect, it } from "vitest"
import { soFarWords, switchWords } from "./lengthsWords"

describe("what Insights says before lengths are learned", () => {
  it("counts what the learner counts, and says why the rest don't", () => {
    expect(soFarWords({ have: 3, need: 5, aside: 11 })).toBe("3 of 5 finished things timed. Use Start on a task to time it. 11 timed on a break or at another pace don't count.")
    expect(switchWords({ have: 3, need: 5, aside: 1 })).toBe("Friday needs 2 more timed things before it can. 1 timed on a break or at another pace doesn't count.")
    expect(switchWords({ have: 4, need: 5 })).toBe("Friday needs 1 more timed thing before it can.")
  })

  it("says it's learning once there are enough, not to time more", () => {
    expect(soFarWords({ have: 14, need: 5, aside: 0 })).toBe("14 finished things timed: Friday is learning from them now.")
    expect(switchWords({ have: 14, need: 5 })).toBe("Friday is learning from what you timed now.")
  })
})
