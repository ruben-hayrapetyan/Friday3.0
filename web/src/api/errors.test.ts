import { describe, expect, it } from "vitest"
import { ApiError, errorWords, fieldWords, messageFrom } from "./client"

describe("errors said so you can act on them (8 Nov)", () => {
  it("leaves the field's key off the server's words", () => {
    expect(messageFrom(400, { field: "end", message: "end: that's later than now" })).toBe("That's later than now")
    expect(messageFrom(400, { field: "parent_id", message: "Lab is at a set time, so it can't hold other items" })).toBe("Lab is at a set time, so it can't hold other items")
    expect(messageFrom(400, { field: "value", message: "value: planner.debounce_s: Input should be a valid number" })).toBe("Input should be a valid number")
  })

  it("names a failed check's field in words", () => {
    const body = { detail: [{ loc: ["body", "duration_min"], msg: "Input should be greater than 0" }, { loc: ["body", "start"], msg: "Value error, not a time" }] }
    expect(messageFrom(422, body)).toBe("Duration: Input should be greater than 0; Start: not a time")
    expect(fieldWords("buffer_before_min")).toBe("Buffer before")
  })

  it("says what a bare failure means and what to do", () => {
    expect(messageFrom(500, null)).toMatch(/inside Friday. Try again.*Diagnose/)
    expect(messageFrom(400, { field: "title", message: "lab_report: can't move there" })).toBe("Lab_report: can't move there")
    expect(messageFrom(404, null)).toMatch(/deleted/)
    expect(messageFrom(500, { message: "Planning failed" })).toBe("Planning failed") // the server's words come first
  })

  it("says a server that didn't answer is starting or restarting, not 'Load failed'", () => {
    expect(errorWords(new TypeError("Load failed"))).toMatch(/didn't answer.*restarting.*quit Friday/)
    expect(errorWords(new ApiError("Lab can't move there", 400))).toBe("Lab can't move there")
    expect(errorWords(new DOMException("aborted", "AbortError"))).toBe("Stopped.")
    expect(errorWords(new TypeError("x is undefined"))).toBe("x is undefined") // a mistake in the page, not the server
  })
})
