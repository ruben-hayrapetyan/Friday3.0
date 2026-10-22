import { describe, expect, it } from "vitest"
import { keyAction } from "./useKeys"

const press = (key: string, extra: Partial<{ meta: boolean; alt: boolean; busy: boolean }> = {}) =>
  keyAction({ key, meta: false, alt: false, busy: false, ...extra })

describe("shortcuts", () => {
  it("map single keys to their actions", () => {
    expect([press("n"), press("w"), press("]"), press(" "), press("ArrowDown")]).toEqual([
      "quickAdd",
      "week",
      "next",
      "timer",
      "later",
    ])
  })

  it("leave typing alone, except for the palette", () => {
    expect(press("n", { busy: true })).toBeNull()
    expect(press("z", { meta: true, busy: true })).toBeNull()
    expect(press("k", { meta: true, busy: true })).toBe("palette")
  })

  it("read ⌘Z as undo and ignore other modified keys", () => {
    expect(press("z", { meta: true })).toBe("undo")
    expect(press("w", { meta: true })).toBeNull()
  })
})
