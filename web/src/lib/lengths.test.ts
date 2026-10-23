import { describe, expect, it } from "vitest"
import { lengthLabel, parseLength } from "./lengths"

describe("lengths read the way people say them", () => {
  it("reads numbers, units, words, ranges and fillers as personal did", () => {
    const cases: [string, number][] = [
      ["90", 90], ["2", 120], ["1.5", 90], ["1h30", 90], ["1h 30", 90], ["1:30", 90], ["90 min", 90],
      ["2 hours", 120], ["2hrs", 120], ["45m", 45], ["an hour", 60], ["an hour and a half", 90],
      ["hour and a half", 90], ["two and a half hours", 150], ["half an hour", 30], ["half hour", 30],
      ["quarter of an hour", 15], ["three quarters of an hour", 45], ["forty-five minutes", 45],
      ["forty five min", 45], ["a couple of hours", 120], ["couple hours", 120], ["a few hours", 180],
      ["2-3 hours", 150], ["2 to 3 hours", 150], ["30-45 min", 37.5], ["2 hours to 3 hours", 150],
      ["about 2 hours", 120], ["2ish hours", 120], ["2 hours or so", 120], ["maybe 3h?", 180],
      ["it took me 40 minutes", 40], ["1 hour 15 minutes", 75], ["2–3 hours", 150],
    ] // prettier-ignore
    for (const [text, minutes] of cases) expect([text, parseLength(text)]).toEqual([text, minutes])
  })

  it("won't guess at what it can't read", () => {
    for (const text of ["", "soon", "0", "tomorrow", "take a while", "2 days"]) expect([text, parseLength(text)]).toEqual([text, null])
  })

  it("labels a length in hours and minutes", () => {
    expect([lengthLabel(135), lengthLabel(45), lengthLabel(120)]).toEqual(["2h 15m", "45m", "2h"])
  })
})
