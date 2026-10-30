import { describe, expect, it } from "vitest"
import { hazeColor, hourOf, lightAt, moonAt, skyColor, sunAt, timeStep } from "./sky"
import { clockTime, GAP, minutesOf, placeZ, ROUTE, sideOf, STOPS } from "./stops"

const ANSWERS = {
  wake: "07:30",
  bedtime: "23:30",
  weekend_wake: "09:00",
  weekend_bedtime: "00:30",
  normal_hours: 8,
  most_hours: 10,
  focus_hours: 3,
  evening_free: 2,
  evening_from: "18:00",
  weekend_free: 4,
  finish_early_days: 1,
  brief: true,
  calendars: [],
}

const STORY = ["hello", "wake", "work", "heavy", "focus", "deadline", "evening", "bed", "weekend", "brief", "ai", "bring", "calendars", "build", "reveal", "start"]

describe("the walk's sky", () => {
  it("rises in the east, is highest in the south at midday, sets in the west, and is down at night", () => {
    const morning = sunAt(7 * 60)
    const noon = sunAt(12 * 60 + 45)
    const evening = sunAt(18 * 60 + 45)
    expect(morning.dir[0]).toBeGreaterThan(0) // east is +x
    expect(evening.dir[0]).toBeLessThan(0)
    expect(noon.dir[2]).toBeGreaterThan(0.5) // south, behind you walking north
    expect(noon.elevation).toBeGreaterThan(morning.elevation)
    expect(noon.elevation).toBeGreaterThan(evening.elevation)
    expect(sunAt(23 * 60).elevation).toBeLessThan(0)
    expect(sunAt(3 * 60).elevation).toBeLessThan(0)
  })

  it("has the moon up at night and down at noon", () => {
    expect(moonAt(23 * 60).elevation).toBeGreaterThan(0.3)
    expect(moonAt(12 * 60).elevation).toBeLessThan(0)
  })

  it("lights the day and lamps the night", () => {
    const day = lightAt(13 * 60)
    const night = lightAt(23 * 60 + 30)
    expect(day.day).toBe(1)
    expect(night.day).toBe(0)
    expect(day.sunLevel).toBeGreaterThan(2)
    expect(night.sunLevel).toBe(0)
    expect(night.lamps).toBe(1)
    expect(day.lamps).toBe(0)
    expect(night.exposure).toBeGreaterThan(day.exposure) // the eye opens up in the dark
    expect(lightAt(19 * 60).sunColor).not.toBe(day.sunColor) // golden at sunset
  })

  it("draws a blue sky at noon, brightest by the sun, and a haze that matches it", () => {
    const l = lightAt(12 * 60)
    const up = skyColor([0, 1, 0], l.sun, l.air)
    expect(up[2]).toBeGreaterThan(up[0]) // blue overhead
    const toward = skyColor(l.sun.map((v) => v * 0.98 + (v === l.sun[1] ? 0.02 : 0)) as [number, number, number], l.sun, l.air)
    expect(toward[0] + toward[1] + toward[2]).toBeGreaterThan(up[0] + up[1] + up[2])
    const haze = hazeColor(l)
    for (const c of haze) expect(Number.isFinite(c) && c >= 0).toBe(true)
  })

  it("lets time go on through the day, or back when going back", () => {
    expect(timeStep(23 * 60, 13 * 60, false)).toBe(14 * 60) // bed on Monday to Saturday afternoon: forward round midnight
    expect(timeStep(13 * 60, 7 * 60, true)).toBe(-6 * 60)
    expect(timeStep(7 * 60, 7 * 60, false)).toBe(0)
    expect(hourOf(-30)).toBe(23.5)
    expect(hourOf(1440 + 90)).toBe(1.5)
  })
})

describe("the walk's route", () => {
  it("has a place for every question setup asks", () => {
    for (const id of STORY) expect(STOPS[id], id).toBeDefined()
  })

  it("goes up the street in order, a place on each side in turn, from the start to the end", () => {
    expect(ROUTE[0][0]).toBe("start")
    expect(ROUTE.at(-1)?.[0]).toBe("end")
    const zs = ROUTE.map(([p]) => placeZ(p))
    for (let i = 1; i < zs.length; i++) expect(zs[i - 1] - zs[i]).toBe(GAP)
    // the order you walk it is the order of the questions
    const order = STORY.map((id) => ROUTE.findIndex(([p]) => p === STOPS[id].place))
    expect([...order].sort((a, b) => a - b)).toEqual(order)
    expect(sideOf("dorm")).toBe(1) // facing east: the sun comes up in its window
    expect(sideOf("home")).toBe(-1) // facing west: it sets in this one
  })

  it("is there at the times your answers say", () => {
    expect(STOPS.wake.at(ANSWERS)).toBe(7 * 60 + 30)
    expect(STOPS.bed.at(ANSWERS)).toBe(23 * 60 + 30)
    expect(STOPS.brief.at(ANSWERS)).toBe(8 * 60) // just after getting up
    expect(STOPS.evening.at(ANSWERS)).toBe(minutesOf("18:00"))
  })

  it("says times as a clock shows them", () => {
    expect(clockTime(7 * 60 + 30)).toBe("7:30 AM")
    expect(clockTime(0)).toBe("12:00 AM")
    expect(clockTime(12 * 60 + 5)).toBe("12:05 PM")
    expect(clockTime(1440 + 23 * 60)).toBe("11:00 PM")
  })
})
