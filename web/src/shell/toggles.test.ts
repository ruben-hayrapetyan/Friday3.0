import { describe, expect, it } from "vitest"
import { closes, isOpen, type Opened, wasInFront } from "./toggles"

const nothing: Opened = { dialog: null, pop: null, newEvent: false }

describe("the same shortcut again takes back what it opened", () => {
  it("⌘K closes the search it opened", () => {
    expect(closes("search", { ...nothing, dialog: "search" }, true)).toBe(true)
    expect(closes("search", nothing, true)).toBe(false)
  })

  it("⌥Space closes the new event it opened, not an event you opened to edit", () => {
    expect(closes("newEvent", { ...nothing, newEvent: true }, true)).toBe(true)
    expect(closes("newEvent", nothing, true)).toBe(false)
  })

  it("⌘J closes Ask Claude; S and P close Shove and Pace", () => {
    expect(closes("ask", { ...nothing, dialog: "ask" }, true)).toBe(true)
    expect(closes("shove", { ...nothing, pop: "shove" }, true)).toBe(true)
    expect(closes("pace", { ...nothing, pop: "pace" }, true)).toBe(true)
  })

  it("a shortcut for something else opens it, whatever is open", () => {
    expect(closes("search", { ...nothing, dialog: "ask" }, true)).toBe(false)
    expect(closes("pace", { ...nothing, pop: "shove" }, true)).toBe(false)
    expect(isOpen("ask", { ...nothing, dialog: "search" })).toBe(false)
  })

  it("a hotkey that brings Friday up from behind other apps opens, though it was left open", () => {
    expect(closes("newEvent", { ...nothing, newEvent: true }, false)).toBe(false)
  })
})

describe("whether Friday was in front", () => {
  it("focused for a while: yes; just brought up, or behind another app: no", () => {
    expect(wasInFront(10_000, 0, true)).toBe(true)
    expect(wasInFront(10_000, 9_900, true)).toBe(false) // came up 100ms ago, with the hotkey
    expect(wasInFront(10_000, 0, false)).toBe(false)
    expect(wasInFront(10_000, Number.POSITIVE_INFINITY, true)).toBe(false)
  })
})
