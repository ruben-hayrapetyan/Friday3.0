import { describe, expect, it } from "vitest"
import { cardPlace, STEPS, stepsFor } from "./Tour"

const rect = (left: number, top: number, width: number, height: number) =>
  ({ left, top, width, height, right: left + width, bottom: top + height, x: left, y: top, toJSON: () => ({}) }) as DOMRect
const card = { width: 340, height: 190 }
const win = { width: 1440, height: 900 }

describe("the tour's steps", () => {
  it("skip a control that isn't on screen, and keep the ones you need anyway", () => {
    const all = stepsFor(() => true)
    expect(all).toEqual(STEPS)
    const none = stepsFor(() => false)
    expect(none.every((s) => !s.optional)).toBe(true)
    expect(none.map((s) => s.title)).toContain("Welcome to Friday")
    expect(none.map((s) => s.target)).not.toContain("attention")
  })

  it("start with a welcome and end on where to find the tour again", () => {
    expect(STEPS[0].target).toBeUndefined()
    expect(STEPS[STEPS.length - 1].target).toBe("help")
    expect(new Set(STEPS.map((s) => `${s.target}${s.title}`)).size).toBe(STEPS.length)
  })
})

describe("where the tour's card goes", () => {
  it("in the middle when it points at nothing", () => {
    expect(cardPlace(null, card, win)).toEqual({ left: 550, top: 355 })
  })

  it("below a control with room under it, above one near the bottom", () => {
    expect(cardPlace(rect(1000, 10, 80, 30), card, win)).toEqual({ left: 1000, top: 52 })
    expect(cardPlace(rect(400, 820, 400, 60), card, win)).toEqual({ left: 400, top: 820 - 12 - 190 })
  })

  it("beside a tall one, and in the middle of one as big as the calendar", () => {
    expect(cardPlace(rect(0, 60, 248, 820), card, win)).toEqual({ left: 260, top: 60 })
    const placed = cardPlace(rect(248, 60, 1180, 840), card, win)
    expect(placed.left).toBeCloseTo(248 + (1180 - 340) / 2)
  })

  it("stays inside a phone's screen", () => {
    const phone = { width: 390, height: 800 }
    const small = { width: 366, height: 190 }
    const at = cardPlace(rect(330, 14, 34, 34), small, phone)
    expect(at.left).toBeGreaterThanOrEqual(12)
    expect(at.left + small.width).toBeLessThanOrEqual(phone.width - 12)
  })
})
