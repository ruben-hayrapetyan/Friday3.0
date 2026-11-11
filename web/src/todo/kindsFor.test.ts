import { describe, expect, it } from "vitest"
import { kindsFor, SCHOOL_KINDS } from "./AddBox"

// C97: out of school, Friday never offers a student's kinds; in school (or not yet asked) every kind is offered.
const ALL = ["Task", "Work task", "Assignment", "Reading", "Exam prep", "Class", "Exam", "Errand", "Meeting", "Lab"]

describe("the kinds Friday offers", () => {
  it("are all of yours in school, and before Setup has asked", () => {
    expect(kindsFor(ALL, true)).toEqual(ALL)
    expect(kindsFor(ALL, undefined)).toEqual(ALL)
  })
  it("leave the school ones out otherwise, keeping your own and the rest in order", () => {
    expect(kindsFor(ALL, false)).toEqual(["Task", "Work task", "Errand", "Meeting", "Lab"])
    expect(kindsFor(ALL, false).some((k) => SCHOOL_KINDS.includes(k))).toBe(false)
  })
})
