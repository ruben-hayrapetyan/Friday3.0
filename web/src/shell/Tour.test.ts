import { describe, expect, it } from "vitest"
import { CARD, completes, homeOf, QUESTS, standFor } from "./Tour"

describe("the quests", () => {
  it("are a handful, each done by something you do in the app", () => {
    // 31 Oct: "its kindof tedious and boring, make it better"
    expect(QUESTS.length).toBeLessThanOrEqual(6)
    expect(new Set(QUESTS.map((q) => q.id)).size).toBe(QUESTS.length)
    for (const q of QUESTS) {
      expect(Object.keys(q.done).length).toBeGreaterThan(0)
      expect(q.hint.length).toBeLessThanOrEqual(64)
    }
  })

  it("notice what you did: a command, a page, a block clicked, a dialog", () => {
    expect(completes({ command: "add" }, [])).toEqual(["add"])
    expect(completes({ picked: true }, [])).toEqual(["find"])
    expect(completes({ command: "start" }, [])).toEqual(["start"])
    expect(completes({ dialog: "search" }, [])).toEqual(["search"])
    expect(completes({ page: "/inbox" }, [])).toEqual(["inbox"])
    expect(completes({ command: "rule_add" }, [])).toEqual(["rule"])
  })

  it("don't count anything else, or a quest twice", () => {
    expect(completes({ command: "edit" }, [])).toEqual([])
    expect(completes({ page: "/" }, [])).toEqual([])
    expect(completes({ dialog: "ask" }, [])).toEqual([])
    expect(completes({ command: "add" }, ["add"])).toEqual([])
  })
})

describe("where the guide stands", () => {
  const win = 1440

  it("by the card, left of it, in the bottom-right corner", () => {
    expect(homeOf(win)).toBeLessThan(win - CARD - 16)
    expect(homeOf(win)).toBeGreaterThan(win - CARD - 140)
  })

  it("below what they show you, never under the card", () => {
    expect(standFor({ left: 100, width: 200 }, win)).toBe(200)
    expect(standFor({ left: 0, width: 20 }, win)).toBeGreaterThanOrEqual(60)
    expect(standFor({ left: 1350, width: 60 }, win)).toBe(homeOf(win))
  })
})
