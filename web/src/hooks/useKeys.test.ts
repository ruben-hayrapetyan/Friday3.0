import { describe, expect, it } from "vitest"
import { keyAction } from "./useKeys"

const press = (key: string, extra: Partial<{ meta: boolean; alt: boolean; busy: boolean; modal: boolean }> = {}) =>
  keyAction({ key, meta: false, alt: false, busy: false, ...extra })

describe("shortcuts", () => {
  it("map single keys to their actions", () => {
    expect([press("n"), press("w"), press("m"), press("]"), press(" "), press("ArrowDown")]).toEqual([
      "quickAdd",
      "week",
      "month",
      "next",
      "timer",
      "later",
    ])
  })

  it("leave typing alone, except for the palette", () => {
    expect(press("n", { busy: true })).toBeNull()
    expect(press("z", { meta: true, busy: true })).toBeNull()
    expect(press("k", { meta: true, busy: true })).toBe("palette")
    expect(press("f", { meta: true })).toBe("palette")
  })

  it("read ⌘Z as undo and ignore other modified keys", () => {
    expect(press("z", { meta: true })).toBe("undo")
    expect(press("w", { meta: true })).toBeNull()
    expect(press("3", { meta: true })).toBeNull()
    expect(press("3")).toBe("three") // the 3 days view
  })

  it("wait while setup or a dialog is open over the page, even ⌘K", () => {
    // the audit, 31 Oct: under setup, Space ran the timer and ⌘K swapped setup for search
    expect(press(" ", { modal: true })).toBeNull()
    expect(press("k", { meta: true, modal: true })).toBeNull()
    expect(press("z", { meta: true, modal: true })).toBeNull()
  })
})
