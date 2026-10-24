import { describe, expect, it } from "vitest"
import { rangeText, readTimeRange } from "./timeRange"

const class930 = { start: "2026-10-20T09:30", end: "2026-10-20T10:30" }
const at2pm = { start: "2026-10-20T14:00", end: "2026-10-20T15:30" }
const read = (text: string, was = class930) => {
  const span = readTimeRange(text, was)
  return span && `${span.start.slice(11)}–${span.end.slice(11)}${span.end.slice(0, 10) === was.start.slice(0, 10) ? "" : " +1"}`
}

describe("rangeText", () => {
  it("writes the span on a 12-hour clock", () => {
    expect(rangeText(class930)).toBe("9:30am–10:30am")
    expect(rangeText(at2pm)).toBe("2pm–3:30pm")
  })
})

describe("readTimeRange", () => {
  it("reads back what it wrote", () => {
    expect(read("9:30am–10:30am")).toBe("09:30–10:30")
    expect(read(rangeText(at2pm), at2pm)).toBe("14:00–15:30")
  })

  it("reads ranges with am and pm, dashes and words", () => {
    expect(read("2pm-3pm")).toBe("14:00–15:00")
    expect(read("9:15am to 10am")).toBe("09:15–10:00")
    expect(read("2 pm - 3 pm")).toBe("14:00–15:00")
    expect(read("1:30p — 2:45p")).toBe("13:30–14:45")
    expect(read("9 a.m. until 11 a.m.")).toBe("09:00–11:00")
    expect(read("noon-1")).toBe("12:00–13:00")
  })

  it("gives a bare time the half nearest the time it had", () => {
    expect(read("10–11:30")).toBe("10:00–11:30")
    expect(read("3-4", at2pm)).toBe("15:00–16:00")
    expect(read("12-1")).toBe("12:00–13:00")
    expect(read("9-5")).toBe("09:00–17:00")
  })

  it("lets one half carry to the other time", () => {
    expect(read("11-1pm")).toBe("11:00–13:00")
    expect(read("2-3pm")).toBe("14:00–15:00")
    expect(read("11am-1")).toBe("11:00–13:00")
    expect(read("11-1am")).toBe("23:00–01:00 +1")
  })

  it("runs past midnight into the next day", () => {
    expect(read("10pm-1am")).toBe("22:00–01:00 +1")
  })

  it("reads the 24-hour clock and squeezed times", () => {
    expect(read("14:00-15:30")).toBe("14:00–15:30")
    expect(read("930-1045")).toBe("09:30–10:45")
    expect(read("0:30-1:00")).toBe("00:30–01:00")
  })

  it("keeps the length for a lone start", () => {
    expect(read("3pm")).toBe("15:00–16:00")
    expect(read("11", at2pm)).toBe("11:00–12:30")
    expect(read("1:45", at2pm)).toBe("13:45–15:15")
  })

  it("refuses what it can't read", () => {
    for (const text of ["", "soon", "25:00", "13pm", "9:75", "9-", "-9", "1-2-3", "3pm-3pm"]) expect(read(text)).toBeNull()
  })
})
