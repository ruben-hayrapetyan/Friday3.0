import { beforeEach, describe, expect, it } from "vitest"
import { answer, answersNow, forgetTaken, unanswer } from "./answers"
import type { Schemas } from "@/api/client"

const s = (id: number) => ({ id }) as Schemas["SuggestionOut"]

// 22 Nov: accepted quickly, then the Inbox left and opened again: they were waiting again, and accepting them a
// second time said there was no such suggestion waiting. What you answered outlives the page until Friday has it.
describe("suggestions answered in the Inbox", () => {
  beforeEach(() => forgetTaken(new Set(), true))

  it("stay answered after the Inbox closes, while Friday saves them", () => {
    answer([{ s: s(1), accepted: true, commandId: null }])
    answer([{ s: s(2), accepted: false, commandId: 7 }])
    forgetTaken(new Set([1, 2])) // opened again: the server's list still has both
    expect(answersNow().map((r) => r.s.id)).toEqual([1, 2])
  })

  it("are let go on the next visit once the server's list no longer has them, unless still being saved", () => {
    answer([{ s: s(1), accepted: true, commandId: null }])
    answer([{ s: s(2), accepted: true, commandId: 8 }])
    forgetTaken(new Set())
    expect(answersNow().map((r) => r.s.id)).toEqual([1])
  })

  it("a refused one goes back to waiting", () => {
    answer([{ s: s(3), accepted: true, commandId: null }])
    unanswer(3)
    expect(answersNow()).toEqual([])
  })
})
