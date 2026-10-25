import { describe, expect, it } from "vitest"
import type { Block } from "@/api/client"
import { known, onRecord } from "./answers"

const block = (key: string, start: string, end: string) => ({ key, item_id: 1, title: "Math HW", start, end }) as Block
const cards = [block("a", "2026-10-24T09:30", "2026-10-24T11:00"), block("b", "2026-10-24T14:15", "2026-10-24T15:15"), block("c", "2026-10-24T17:30", "2026-10-24T19:00")]

describe("a day's answers", () => {
  it("reads what a review recorded back as done, partly or didn't happen", () => {
    expect(onRecord(cards, { a: 0, b: 60, c: 45 })).toEqual({
      a: { status: "not_done", minutes: 0 },
      b: { status: "done", minutes: 60 },
      c: { status: "partial", minutes: 45 },
    })
  })

  it("a reviewed day comes back answered, so it isn't asked again", () => {
    const all = known(cards, { a: 0, b: 0, c: 0 }, {}, false)
    expect(cards.every((b) => all[b.key])).toBe(true)
  })

  it("a block that started after the review is the only one left to answer", () => {
    const all = known(cards, { a: 0, b: 0 }, {}, false)
    expect(cards.filter((b) => !all[b.key]).map((b) => b.key)).toEqual(["c"])
  })

  it("this visit's answers win, and answering again starts from none", () => {
    expect(known(cards, { a: 0 }, { a: { status: "done", minutes: 90 } }, false).a.status).toBe("done")
    expect(known(cards, { a: 0, b: 0, c: 0 }, {}, true)).toEqual({})
  })
})
