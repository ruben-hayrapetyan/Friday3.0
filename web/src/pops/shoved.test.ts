import { afterEach, describe, expect, it, vi } from "vitest"
import { isJustShoved, markShoved } from "./shoved"

describe("the time just shoved", () => {
  afterEach(() => vi.useRealTimers())

  it("glows for a few seconds, then stops", () => {
    vi.useFakeTimers()
    markShoved([7, 8])
    expect(isJustShoved(7) && isJustShoved(8)).toBe(true)
    expect(isJustShoved(9)).toBe(false)
    vi.advanceTimersByTime(5000)
    expect(isJustShoved(7)).toBe(false)
  })

  it("a newer shove keeps its glow when the older one's time runs out", () => {
    vi.useFakeTimers()
    markShoved([1])
    vi.advanceTimersByTime(3000)
    markShoved([2])
    vi.advanceTimersByTime(2000) // the first one's timer fires here
    expect(isJustShoved(2)).toBe(true)
    expect(isJustShoved(1)).toBe(false)
  })
})
