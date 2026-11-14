// Your clock (lib/clock.ts, settings `clock`): every helper that writes a time follows it, 12-hour unless you chose 24.
import { afterEach, describe, expect, it } from "vitest"
import { clockFace } from "@/dialogs/walk/stops"
import { typedTime } from "./ampm"
import { clockSetting, setClock } from "./clock"
import { clock, clockSpan, sittings, when } from "./format"
import { clockTime, hhmm, hourMarks, shortHour } from "./time"
import { rangeText, readTime, readTimeRange } from "./timeRange"

afterEach(() => setClock("12h"))

describe("the clock in effect", () => {
  it("is the 12-hour one until your settings say otherwise, and only the two clocks are taken", () => {
    expect(clockSetting()).toBe("12h")
    setClock("24h")
    expect(clockSetting()).toBe("24h")
    for (const junk of [undefined, null, "25h", 24, {}]) setClock(junk) // settings not loaded yet, or not a clock
    expect(clockSetting()).toBe("24h")
  })
})

describe("a time on the 24-hour clock", () => {
  it("has its leading zero, and midnight is 00:00", () => {
    expect(["14:05", "09:30", "00:00", "23:59", "2026-10-20T07:00"].map(hhmm)).toEqual(["14:05", "09:30", "00:00", "23:59", "07:00"])
  })

  it("is what every time shown reads once you choose it", () => {
    expect(clockTime("14:30")).toBe("2:30pm")
    setClock("24h")
    expect(clockTime("14:30")).toBe("14:30")
    expect(clock("2026-10-20T09:05")).toBe("09:05")
    expect(when("2026-10-22T17:00", "2026-10-20")).toBe("Thu 17:00")
    expect(hourMarks({ startMin: 23 * 60, endMin: 25 * 60 + 30 }).map((m) => m.label)).toEqual(["23:00", "00:00", "01:00"])
    expect(rangeText({ start: "2026-10-20T09:30", end: "2026-10-20T10:30" })).toBe("09:30–10:30")
  })

  it("keeps an hour on a narrow axis short", () => {
    expect([shortHour(8), shortHour(12), shortHour(23)]).toEqual(["8a", "12p", "11p"])
    setClock("24h")
    expect([shortHour(8), shortHour(12), shortHour(24)]).toEqual(["08", "12", "00"])
  })
})

describe("a span", () => {
  it("says its half once on the 12-hour clock", () => {
    expect(clockSpan("14:45", "15:30")).toBe("2:45–3:30pm")
    expect(clockSpan("11:00", "13:00")).toBe("11am–1pm")
  })

  // Built from the 12-hour span, which drops the end's last two letters when both share them: on the 24-hour clock
  // 14:45 and 15:45 share "45", and the sitting read "14:–15:45".
  it("keeps both of its 24-hour times whole, even when they end alike", () => {
    setClock("24h")
    expect(clockSpan("14:45", "15:45")).toBe("14:45–15:45")
    const rows = [
      { source: "timer", minutes: 60, start: "2026-10-25T14:45" },
      { source: "timer", minutes: 5, start: "2026-10-25T09:00" },
    ]
    expect(sittings(rows, "2026-10-25")).toBe("09:00–09:05, 14:45–15:45")
  })
})

describe("a time you type on the 24-hour clock", () => {
  it("is the time it says, with no half to guess", () => {
    setClock("24h")
    expect(readTime("9")).toEqual({ minute: 9 * 60, half: "am" })
    expect(readTime("12")).toEqual({ minute: 12 * 60, half: "pm" })
    expect(readTime("12:30")).toEqual({ minute: 12 * 60 + 30, half: "pm" })
    expect(typedTime("9", "21:00", { hours: ["15:00", "03:00"] })).toEqual({ time: "09:00", guessed: false })
    expect(typedTime("11pm", "")).toEqual({ time: "23:00", guessed: false }) // an am or pm typed still counts
    expect(readTimeRange("3–4", { start: "2026-10-20T14:00", end: "2026-10-20T15:00" })).toEqual({ start: "2026-10-20T03:00", end: "2026-10-20T04:00" })
  })

  it("is read for the half it means on the 12-hour clock, as before", () => {
    expect(typedTime("9", "21:00", { hours: ["15:00", "03:00"] })).toEqual({ time: "21:00", guessed: true })
    expect(readTimeRange("3–4", { start: "2026-10-20T14:00", end: "2026-10-20T15:00" })).toEqual({ start: "2026-10-20T15:00", end: "2026-10-20T16:00" })
  })
})

describe("the walk's clocks", () => {
  it("show the time as a clock does, on yours", () => {
    expect(clockFace(7 * 60 + 30)).toBe("7:30 AM")
    setClock("24h")
    expect(clockFace(7 * 60 + 30)).toBe("07:30")
    expect(clockFace(1440 + 23 * 60)).toBe("23:00")
  })
})
