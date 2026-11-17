// Whether Friday is still making a plan for the last change (17 Nov: "the user can see that friday is replanning").
import { describe, expect, it } from "vitest"
import { replanning } from "./replan"

describe("replanning", () => {
  it("while the plan is behind the server's changes", () => {
    expect(replanning({ generation: 9, plan_generation: 8 }, 0)).toBe(true)
  })
  it("while the plan is behind the change just sent, before the server says so", () => {
    expect(replanning({ generation: 8, plan_generation: 8 }, 9)).toBe(true)
  })
  it("not once the plan has caught up, nor before there's any plan", () => {
    expect(replanning({ generation: 9, plan_generation: 9 }, 9)).toBe(false)
    expect(replanning({ generation: 9, plan_generation: null }, 9)).toBe(false)
    expect(replanning(undefined, 9)).toBe(false)
  })
})
