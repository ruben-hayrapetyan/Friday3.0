import { describe, expect, it } from "vitest"
import { EXAM_HOURS, inHours, MEAL_HOURS, meant, otherHalf, readAs, SLEEP_HOURS } from "./ampm"

// Typing an hour into a 12-hour box keeps the am or pm it showed: lunch's 12:30pm, retyped as 11, comes in as 23:30.
describe("a typed time is read as the half of the day it means", () => {
  it("lunch retyped as 11 is 11am, not 11pm (27 Oct)", () => {
    expect(meant("23:30", "12:30", { hours: MEAL_HOURS.lunch })).toBe("11:30")
  })

  it("each meal takes the half it happens in", () => {
    expect(meant("20:00", "08:30", { hours: MEAL_HOURS.breakfast })).toBe("08:00") // breakfast at 8pm
    expect(meant("07:15", "19:00", { hours: MEAL_HOURS.dinner })).toBe("19:15") // dinner at 7am
    expect(meant("01:30", "12:30", { hours: MEAL_HOURS.lunch })).toBe("13:30") // lunch at 1:30am
    expect(meant("00:15", "12:30", { hours: MEAL_HOURS.lunch })).toBe("12:15") // lunch at 12:15am
  })

  it("an unusual time that's still the right half of the day stays", () => {
    expect(meant("23:00", "19:00", { hours: MEAL_HOURS.dinner })).toBe("23:00") // a late dinner
    expect(meant("01:00", "19:00", { hours: MEAL_HOURS.dinner })).toBe("01:00") // a very late one
    expect(meant("16:30", "12:30", { hours: MEAL_HOURS.lunch })).toBe("16:30") // a late lunch
    expect(meant("11:45", "08:30", { hours: MEAL_HOURS.breakfast })).toBe("11:45") // a late breakfast
  })

  it("the night's times take theirs", () => {
    expect(meant("11:30", "00:30", { hours: SLEEP_HOURS.bed })).toBe("23:30") // bed at 12:30am retyped as 11:30
    expect(meant("14:20", "00:30", { hours: SLEEP_HOURS.bed })).toBe("02:20") // bed at 2:20pm
    expect(meant("19:00", "07:30", { hours: SLEEP_HOURS.up })).toBe("07:00") // up at 7pm
    expect(meant("22:38", "07:00", { hours: SLEEP_HOURS.up })).toBe("10:38") // up at 10:38pm
    expect(meant("10:15", "22:18", { hours: SLEEP_HOURS.done })).toBe("22:15") // done with work at 10:15am
    expect(meant("13:00", "08:00", { hours: SLEEP_HOURS.up })).toBe("13:00") // a very late morning stays
  })

  it("turning am into pm yourself is kept, even where it doesn't fit", () => {
    expect(meant("23:30", "11:30", { hours: MEAL_HOURS.lunch })).toBe("23:30")
    expect(meant("07:00", "19:00", { hours: MEAL_HOURS.dinner })).toBe("07:00")
    // So after Friday made 11pm into 11am, pressing P again gives 11pm.
    const made = meant("23:30", "12:30", { hours: MEAL_HOURS.lunch })
    expect(meant("23:30", made, { hours: MEAL_HOURS.lunch })).toBe("23:30")
  })

  it("an end comes after its start, within 12 hours", () => {
    expect(meant("01:00", "12:50", { after: "12:30" })).toBe("13:00") // lunch 12:30 to 1am
    expect(meant("02:00", "14:30", { after: "13:00" })).toBe("14:00") // an event 1pm to 2am
    expect(meant("00:30", "23:50", { after: "23:15" })).toBe("00:30") // past midnight, as typed
    expect(meant("12:30", "12:50", { after: "12:30" })).toBe("12:30") // the start itself while typing
    expect(meant("17:00", "10:00", { after: "09:00" })).toBe("17:00") // "between 9am and 5pm"
    expect(meant("05:00", "10:00", { after: "09:00" })).toBe("17:00")
  })

  it("with nothing else to go on, the half nearest what the box had", () => {
    expect(meant("23:00", "13:00")).toBe("11:00") // a 1pm event retyped as 11
    expect(meant("15:00", "14:00")).toBe("15:00")
    expect(meant("03:00", "14:00")).toBe("15:00")
    expect(meant("20:00", "09:00", { near: "08:00" })).toBe("08:00")
  })

  it("both halves fitting, or neither, goes to the nearer one; a tie keeps what was typed", () => {
    expect(meant("19:00", "08:00", { hours: ["00:00", "23:59"] })).toBe("07:00")
    expect(meant("03:00", "12:00", { hours: ["13:00", "14:00"] })).toBe("15:00")
    expect(meant("18:00", "12:00")).toBe("18:00") // six hours either way
  })

  it("an exam starts in the day, not the small hours", () => {
    expect(meant("19:30", "18:00", { hours: EXAM_HOURS })).toBe("19:30") // both fit: the nearer
    expect(meant("02:00", "19:30", { hours: EXAM_HOURS })).toBe("14:00")
  })

  it("leaves alone what isn't a time, an empty box and a box with nothing before", () => {
    expect(meant("", "12:30", { hours: MEAL_HOURS.lunch })).toBe("")
    expect(meant("11:30", "", {})).toBe("11:30")
    expect(meant("23:30", "", { hours: MEAL_HOURS.lunch })).toBe("11:30") // a first time typed still fits lunch
    expect(meant("25:00", "12:00")).toBe("25:00")
  })
})

describe("the parts", () => {
  it("the other half of the day", () => {
    expect([otherHalf("11:30"), otherHalf("23:30"), otherHalf("12:15"), otherHalf("00:00")]).toEqual(["23:30", "11:30", "00:15", "12:00"])
  })

  it("hours that run past midnight", () => {
    expect(inHours("01:00", ["15:00", "03:00"])).toBe(true)
    expect(inHours("04:00", ["15:00", "03:00"])).toBe(false)
    expect(inHours("10:00", ["10:00", "17:00"])).toBe(true)
    expect(inHours("17:01", ["10:00", "17:00"])).toBe(false)
  })

  it("every time, typed for any meal or night, comes back in that thing's hours or as typed by your own hand", () => {
    const every = Array.from({ length: 96 }, (_, n) => `${String(Math.floor(n / 4)).padStart(2, "0")}:${String((n % 4) * 15).padStart(2, "0")}`)
    for (const hours of [...Object.values(MEAL_HOURS), ...Object.values(SLEEP_HOURS)]) {
      for (const typed of every) {
        const was = "06:00" // never the other half of a typed time on the quarter hour unless it's 18:00
        const got = meant(typed, was, { hours })
        expect(got === typed || got === otherHalf(typed)).toBe(true)
        if (typed !== otherHalf(was) && (inHours(typed, hours) || inHours(otherHalf(typed), hours))) expect(inHours(got, hours)).toBe(true)
      }
    }
  })

  it("says what it did, in 12-hour time", () => {
    expect(readAs("23:30", "11:30")).toEqual({ made: "11:30am", keep: "11:30pm" })
    expect(readAs("11:30", "11:30")).toBeNull()
  })
})
