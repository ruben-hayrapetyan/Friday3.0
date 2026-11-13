import { describe, expect, it } from "vitest"
import { toMin } from "@/lib/time"
import { nextHour, placeAfter, readHost, shiftMonth, switchView } from "./host"

describe("a request from the Mac app", () => {
  it("is read when Friday knows it", () => {
    expect(readHost({ action: "newEvent" })).toEqual({ action: "newEvent" })
    expect(readHost({ action: "view", argument: "month" })).toEqual({ action: "view", argument: "month" })
    expect(readHost({ action: "go", argument: "/settings" })).toEqual({ action: "go", argument: "/settings" })
    expect(readHost({ action: "go", argument: "/settings/calendars" })).toEqual({ action: "go", argument: "/settings/calendars" })
    expect(readHost({ action: "go", argument: "/" })).toEqual({ action: "go", argument: "/" })
    expect(readHost({ action: "drawer", argument: "open" })).toEqual({ action: "drawer", argument: "open" })
    expect(readHost({ action: "tour" })).toEqual({ action: "tour" })
  })

  it("is ignored otherwise", () => {
    expect(readHost(null)).toBeNull()
    expect(readHost("newEvent")).toBeNull()
    expect(readHost({ action: "delete_everything" })).toBeNull()
    expect(readHost({ action: "view", argument: "3day" })).toBeNull()
    expect(readHost({ action: "view" })).toBeNull()
    expect(readHost({ action: "go", argument: "https://example.com" })).toBeNull()
    expect(readHost({ action: "go", argument: "//example.com" })).toBeNull()
    expect(readHost({ action: "go", argument: "/todoish" })).toBeNull()
    expect(readHost({ action: "go" })).toBeNull()
    expect(readHost({ action: "search", argument: 3 })).toBeNull()
  })
})

describe("moving the calendar from the menus", () => {
  const today = "2026-10-23"
  it("steps by the view: a day, three days, a week or a month", () => {
    expect(placeAfter({ action: "next" }, { view: 1, first: null }, today)).toEqual({ view: 1, first: "2026-10-24" })
    expect(placeAfter({ action: "next" }, { view: 3, first: null }, today)).toEqual({ view: 3, first: "2026-10-26" })
    expect(placeAfter({ action: "view", argument: "three" }, { view: 7, first: null }, today)).toEqual({ view: 3, first: null })
    expect(placeAfter({ action: "previous" }, { view: 7, first: "2026-10-19" }, today)).toEqual({ view: 7, first: "2026-10-12" })
    expect(placeAfter({ action: "next" }, { view: "month", first: null }, today)).toEqual({ view: "month", first: "2026-11-01" })
    expect(placeAfter({ action: "next" }, { view: "month", first: "2026-12-01" }, today)).toEqual({ view: "month", first: "2027-01-01" })
    expect(placeAfter({ action: "previous" }, { view: 1, first: "2026-03-01" }, today)).toEqual({ view: 1, first: "2026-02-28" })
  })

  it("steps the centre, so the day you were on stays in the middle (4 Nov)", () => {
    expect(placeAfter({ action: "next" }, { view: 7, first: "2026-11-04" }, today)).toEqual({ view: 7, first: "2026-11-11" })
    expect(placeAfter({ action: "previous" }, { view: 3, first: "2026-11-04" }, today)).toEqual({ view: 3, first: "2026-11-01" })
    expect(placeAfter({ action: "previous" }, { view: 7, first: null }, today)).toEqual({ view: 7, first: "2026-10-16" })
  })

  it("comes out of this month to the days around today, and out of another month to its first day", () => {
    expect(placeAfter({ action: "view", argument: "week" }, { view: "month", first: "2026-10-01" }, today)).toEqual({ view: 7, first: null })
    expect(placeAfter({ action: "view", argument: "day" }, { view: "month", first: "2026-12-01" }, today)).toEqual({ view: 1, first: "2026-12-01" })
  })

  it("comes back to today, keeping the view", () => {
    expect(placeAfter({ action: "today" }, { view: 7, first: "2026-12-07" }, today)).toEqual({ view: 7, first: null })
  })

  it("changes the view; a month starts on the 1st", () => {
    expect(placeAfter({ action: "view", argument: "month" }, { view: 7, first: "2026-11-16" }, today)).toEqual({ view: "month", first: "2026-11-01" })
    expect(placeAfter({ action: "view", argument: "day" }, { view: 7, first: null }, today)).toEqual({ view: 1, first: null })
    expect(placeAfter({ action: "view", argument: "week" }, { view: 1, first: "2026-11-02" }, today)).toEqual({ view: 7, first: "2026-11-02" })
  })

  it("is left alone by anything else", () => {
    expect(placeAfter({ action: "search" }, { view: 7, first: null }, today)).toBeNull()
  })

  it("months shift across years both ways", () => {
    expect(shiftMonth("2026-01-01", -1)).toBe("2025-12-01")
    expect(shiftMonth("2026-01-31", 13)).toBe("2027-02-01")
  })
})

describe("a new event from the menu", () => {
  it("starts on the next whole hour", () => {
    expect(nextHour(toMin("2026-10-23T14:20"))).toBe("2026-10-23T15:00")
    expect(nextHour(toMin("2026-10-23T14:00"))).toBe("2026-10-23T15:00")
    expect(nextHour(toMin("2026-10-23T23:30"))).toBe("2026-10-24T00:00")
  })
})

describe("changing the view (switchView), as the View buttons, the keys and the menus all do", () => {
  // the audit, 12 Nov: the View buttons jumped back to today; the keys and the menus kept the day you were on
  const today = "2026-11-12"
  it("keeps the day you're looking at", () => {
    expect(switchView({ view: 7, first: "2026-11-26" }, 1, today)).toEqual({ view: 1, first: "2026-11-26" })
    expect(switchView({ view: 1, first: "2026-11-26" }, 3, today)).toEqual({ view: 3, first: "2026-11-26" })
    expect(switchView({ view: 3, first: "2026-12-30" }, 7, today)).toEqual({ view: 7, first: "2026-12-30" })
  })

  it("stays on today while it's on today", () => {
    expect(switchView({ view: 7, first: null }, 1, today)).toEqual({ view: 1, first: null })
  })

  it("goes to the month the day is in", () => {
    expect(switchView({ view: 7, first: "2026-12-30" }, "month", today)).toEqual({ view: "month", first: "2026-12-01" })
    expect(switchView({ view: 1, first: null }, "month", today)).toEqual({ view: "month", first: "2026-11-01" })
  })

  it("comes out of this month around today, and out of another from its first day", () => {
    expect(switchView({ view: "month", first: "2026-11-01" }, 7, today)).toEqual({ view: 7, first: null })
    expect(switchView({ view: "month", first: null }, 3, today)).toEqual({ view: 3, first: null })
    expect(switchView({ view: "month", first: "2027-01-01" }, 1, today)).toEqual({ view: 1, first: "2027-01-01" })
  })

  it("is what the menus' view does", () => {
    const place = { view: 7 as const, first: "2026-11-26" }
    expect(placeAfter({ action: "view", argument: "day" }, place, today)).toEqual(switchView(place, 1, today))
    expect(placeAfter({ action: "view", argument: "month" }, place, today)).toEqual(switchView(place, "month", today))
  })
})
