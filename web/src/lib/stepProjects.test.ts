// A project made of steps isn't a to-do; its steps are, together under its name (17 Nov, proposal (h)).
import { describe, expect, it } from "vitest"
import { stepsTogether, withoutStepProjects } from "./todo"

const item = (id: number, parent_id: number | null = null, status = "todo") => ({ id, parent_id, status })

describe("a project in a to-do list", () => {
  it("isn't a row while it has steps to do", () => {
    const all = [item(1), item(2, 1), item(3, 1, "done"), item(4)]
    expect(withoutStepProjects(all).map((i) => i.id)).toEqual([2, 3, 4])
  })
  it("is one when it has no steps, or only done ones", () => {
    expect(withoutStepProjects([item(1), item(2, 1, "done")]).map((i) => i.id)).toEqual([1, 2])
    expect(withoutStepProjects([item(5)]).map((i) => i.id)).toEqual([5])
  })
  it("counts steps listed elsewhere (another list's)", () => {
    expect(withoutStepProjects([item(1)], [item(1), item(9, 1)]).map((i) => i.id)).toEqual([])
  })
})

describe("a project's steps in a list", () => {
  it("come together where the first of them falls, the rest in their order", () => {
    const sorted = [item(10, 1), item(20), item(11, 1), item(30, 2), item(12, 1), item(31, 2)]
    expect(stepsTogether(sorted).map((i) => i.id)).toEqual([10, 11, 12, 20, 30, 31])
  })
})
