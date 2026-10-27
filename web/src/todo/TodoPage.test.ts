import { describe, expect, it } from "vitest"
import { draggedIds, droppedIds } from "./TodoPage"

describe("dragging to-dos to another section", () => {
  it("a picked task carries every picked one with it (27 Oct)", () => {
    expect(draggedIds(5, [3, 5, 9])).toEqual([3, 5, 9])
  })

  it("a task not picked, or picked alone, goes alone", () => {
    expect(draggedIds(7, [3, 5, 9])).toEqual([7])
    expect(draggedIds(5, [5])).toEqual([5])
    expect(draggedIds(5, [])).toEqual([5])
  })

  it("what a drop brings is read back, and anything that isn't a task is left out", () => {
    expect(droppedIds("3,5,9")).toEqual([3, 5, 9])
    expect(droppedIds("12")).toEqual([12])
    expect(droppedIds("")).toEqual([])
    expect(droppedIds("x,4,-1,2.5")).toEqual([4])
  })
})
