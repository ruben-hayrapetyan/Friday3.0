import { describe, expect, it } from "vitest"
import { DAY_HOURS, EXAM_HOURS, type Expect, inHours, MEAL_HOURS, otherHalf, SLEEP_HOURS, typedTime } from "./ampm"

const at = (text: string, was = "", expect: Expect = {}) => typedTime(text, was, expect)?.time ?? null

// A 12-hour box kept the am or pm it showed: lunch's 12:30pm, retyped as 11, came in as 23:30. A time typed without
// am or pm is read as the half of the day it means.
describe("a typed time is read as the half of the day it means", () => {
  it("lunch retyped as 11 is 11am, not 11pm (27 Oct)", () => {
    expect(at("11:30", "12:30", { hours: MEAL_HOURS.lunch })).toBe("11:30")
    expect(at("11", "12:30", { hours: MEAL_HOURS.lunch })).toBe("11:00")
  })

  it("each meal takes the half it happens in", () => {
    expect(at("8", "08:30", { hours: MEAL_HOURS.breakfast })).toBe("08:00")
    expect(at("7:15", "19:00", { hours: MEAL_HOURS.dinner })).toBe("19:15")
    expect(at("1:30", "12:30", { hours: MEAL_HOURS.lunch })).toBe("13:30")
    expect(at("12:15", "12:30", { hours: MEAL_HOURS.lunch })).toBe("12:15")
  })

  it("an unusual time that's still the right half of the day stays", () => {
    expect(at("11", "19:00", { hours: MEAL_HOURS.dinner })).toBe("23:00") // a late dinner
    expect(at("4:30", "12:30", { hours: MEAL_HOURS.lunch })).toBe("16:30") // a late lunch
    expect(at("11:45", "08:30", { hours: MEAL_HOURS.breakfast })).toBe("11:45") // a late breakfast
  })

  it("the night's times take theirs", () => {
    expect(at("11:30", "00:30", { hours: SLEEP_HOURS.bed })).toBe("23:30")
    expect(at("7", "07:30", { hours: SLEEP_HOURS.up })).toBe("07:00")
    expect(at("10:38", "07:00", { hours: SLEEP_HOURS.up })).toBe("10:38")
    expect(at("10:15", "22:18", { hours: SLEEP_HOURS.done })).toBe("22:15")
  })

  it("an am or pm you type is kept, even where it doesn't fit", () => {
    expect(at("11:30pm", "11:30", { hours: MEAL_HOURS.lunch })).toBe("23:30")
    expect(at("7am", "19:00", { hours: MEAL_HOURS.dinner })).toBe("07:00")
    expect(at("11:30 p", "12:30", { hours: MEAL_HOURS.lunch })).toBe("23:30")
    expect(at("9:15 a.m.", "", {})).toBe("09:15")
    expect(typedTime("11:30pm", "", {})?.guessed).toBe(false)
    expect(typedTime("11:30", "", {})?.guessed).toBe(true)
  })

  it("a time on the 24-hour clock, or with a leading zero, is that time", () => {
    expect(at("23:30", "12:30", { hours: MEAL_HOURS.lunch })).toBe("23:30")
    expect(at("0:15")).toBe("00:15")
    expect(at("07:30", "19:00", { hours: MEAL_HOURS.dinner })).toBe("07:30")
    expect(typedTime("14:30", "")?.guessed).toBe(false)
  })

  it("reads the ways a time is typed", () => {
    expect(at("1130", "12:00")).toBe("11:30")
    expect(at("930", "08:00")).toBe("09:30")
    expect(at("11.30", "12:00")).toBe("11:30")
    expect(at("noon")).toBe("12:00")
    expect(at("midnight")).toBe("00:00")
    expect(at("12", "")).toBe("12:00") // noon, not midnight
    expect(at("6pm")).toBe("18:00")
  })

  it("an end comes after its start, within 12 hours", () => {
    expect(at("1", "12:50", { after: "12:30" })).toBe("13:00")
    expect(at("2", "14:30", { after: "13:00" })).toBe("14:00")
    expect(at("12:30", "23:50", { after: "23:15" })).toBe("00:30")
    expect(at("5", "10:00", { after: "09:00" })).toBe("17:00")
    expect(at("5", "", { after: "09:00" })).toBe("17:00") // an empty end box too
  })

  it("with nothing else to go on, the half nearest what the box had", () => {
    expect(at("11", "13:00")).toBe("11:00") // a 1pm event retyped as 11
    expect(at("3", "14:00")).toBe("15:00")
    expect(at("8", "09:00", { near: "08:00" })).toBe("08:00")
    expect(at("8", "21:00")).toBe("20:00")
  })

  it("an empty box fills in the half a time is usually meant in (28 Oct)", () => {
    expect(at("7")).toBe("07:00")
    expect(at("11:30")).toBe("11:30")
    expect(at("12:30")).toBe("12:30")
    expect(at("1")).toBe("13:00")
    expect(at("6:45")).toBe("18:45")
    expect(at("6", "12:00")).toBe("18:00") // six hours either way: the usual half
  })

  it("an exam starts in the day, not the small hours", () => {
    expect(at("7:30", "18:00", { hours: EXAM_HOURS })).toBe("19:30")
    expect(at("2", "19:30", { hours: EXAM_HOURS })).toBe("14:00")
  })

  it("a due typed over its 11:59pm is in the day", () => {
    expect(at("5", "23:59", { hours: DAY_HOURS })).toBe("17:00")
    expect(at("11:59", "23:59", { hours: DAY_HOURS })).toBe("23:59")
    expect(at("12:30", "23:59", { hours: DAY_HOURS })).toBe("12:30")
    expect(at("9", "23:59", { hours: DAY_HOURS })).toBe("21:00") // both fit: nearer what it was
  })

  it("can't read what isn't a time", () => {
    for (const text of ["", "abc", "25:00", "11:75", "13pm", "1:2"]) expect(at(text, "12:30")).toBeNull()
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

  it("every time, typed without a half for any meal or night, comes back in that thing's hours when one half is", () => {
    for (const hours of [...Object.values(MEAL_HOURS), ...Object.values(SLEEP_HOURS)]) {
      for (let h = 1; h <= 12; h++) {
        for (const m of ["00", "15", "30", "45"]) {
          for (const was of ["", "06:00", "18:00"]) {
            const got = at(`${h}:${m}`, was, { hours })
            const am = `${String(h % 12).padStart(2, "0")}:${m}`
            expect(got === am || got === otherHalf(am)).toBe(true)
            if (inHours(am, hours) !== inHours(otherHalf(am), hours)) expect(inHours(got as string, hours)).toBe(true)
          }
        }
      }
    }
  })
})
