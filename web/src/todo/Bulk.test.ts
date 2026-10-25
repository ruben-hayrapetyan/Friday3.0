import { describe, expect, it } from "vitest"
import { pickWith, tasks } from "./Bulk"

const order = [10, 11, 12, 13, 14]

describe("picking several tasks", () => {
  it("⌘-click adds a task, and takes it back off", () => {
    expect(pickWith(order, [10], 10, 12, true, false)).toEqual([10, 12])
    expect(pickWith(order, [10, 12], 12, 12, true, false)).toEqual([10])
  })

  it("Shift-click takes the run from the last one picked, either way", () => {
    expect(pickWith(order, [11], 11, 13, false, true)).toEqual([11, 12, 13])
    expect(pickWith(order, [13], 13, 10, false, true)).toEqual([13, 10, 11, 12])
  })

  it("Shift-click with nothing picked yet picks that one", () => {
    expect(pickWith(order, [], null, 12, false, true)).toEqual([12])
  })

  it("a plain click leaves picking", () => {
    expect(pickWith(order, [10, 11], 11, 12, false, false)).toEqual([])
  })

  it("counts tasks in words", () => {
    expect([tasks(1), tasks(3)]).toEqual(["1 task", "3 tasks"])
  })
})
