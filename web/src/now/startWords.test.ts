// 24 Nov, a user: starting a task from To-do while timing another stopped that one with no word of it, where the
// plan's block offered Switch or Alongside. One rule for every start.
import { describe, expect, it } from "vitest"
import { otherTimed, startWords } from "./startWords"

describe("a start while something else is timed", () => {
  it("is a Switch that says what stops, with Alongside beside it", () => {
    expect(startWords("Essay A", false)).toEqual({ label: "Switch", hint: "Times this instead: Essay A stops", alongside: true })
    expect(startWords("Essay A", true, "Start now")).toEqual({ label: "Switch", hint: "Times this instead: Essay A stops", alongside: true })
  })
  it("is the page's own Start, or Resume, when nothing else is", () => {
    expect(startWords(null, false, "Start now")).toEqual({ label: "Start now", hint: "Times it now", alongside: false })
    expect(startWords(null, true)).toEqual({ label: "Resume", hint: "Times it now", alongside: false })
  })
  it("finds what else is timed, the timer's or one alongside", () => {
    const status = { timer: { item_id: 1, title: "Essay A" }, alongside: [{ item_id: 2, title: "Laundry" }] }
    expect(otherTimed(status, 3)).toBe("Essay A")
    expect(otherTimed({ timer: null, alongside: [{ item_id: 2, title: "Laundry" }] }, 3)).toBe("Laundry")
    expect(otherTimed(status, 1)).toBeNull() // this one is timed
    expect(otherTimed({ timer: null, alongside: [] }, 3)).toBeNull()
  })
})
