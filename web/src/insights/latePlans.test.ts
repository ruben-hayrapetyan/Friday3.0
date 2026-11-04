// Insights' "Late on paper, on time in practice" (3 Nov).
import { describe, expect, it } from "vitest"
import { headline, WAYS, ways } from "./latePlans"

describe("glass box", () => {
  it("names each way and counts it, the most used first", () => {
    expect(ways({ faster: 4, events: 7, mornings: 3, daytime: 1 })).toEqual([
      { way: "events", said: WAYS.events, n: 7 },
      { way: "faster", said: WAYS.faster, n: 4 },
      { way: "mornings", said: WAYS.mornings, n: 3 },
      { way: "daytime", said: WAYS.daytime, n: 1 },
    ])
  })
  it("ties keep a fixed order, and none-times are left out", () => {
    expect(ways({ nights: 2, faster: 2, untold: 0 }).map((w) => w.way)).toEqual(["faster", "nights"])
  })
  it("a way Friday doesn't know yet is still shown, by its name", () => {
    expect(ways({ weekends: 1 })).toEqual([{ way: "weekends", said: "weekends", n: 1 }])
  })
  it("the headline says the share", () => {
    expect(headline(8, 6)).toBe("8 of 14 things your plans showed late you finished on time (57%).")
    expect(headline(0, 0)).toBe("No work your plans showed late has come due yet.")
  })
})

describe("black box", () => {
  it("never loses or invents a count", () => {
    const counts = { faster: 3, nights: 1, mornings: 0, events: 5, daytime: 2, untold: 1 }
    const out = ways(counts)
    expect(out.reduce((s, w) => s + w.n, 0)).toBe(Object.values(counts).reduce((a, b) => a + b, 0))
    for (let i = 1; i < out.length; i++) expect(out[i - 1].n).toBeGreaterThanOrEqual(out[i].n)
  })
  it("a share is between 0 and 100 whatever the counts", () => {
    for (const [a, b] of [[0, 5], [5, 0], [1, 2], [99, 1]]) {
      const pct = Number(headline(a, b).match(/\((\d+)%\)/)?.[1])
      expect(pct).toBeGreaterThanOrEqual(0)
      expect(pct).toBeLessThanOrEqual(100)
    }
  })
})
