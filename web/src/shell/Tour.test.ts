import { describe, expect, it } from "vitest"
import { STRIP } from "@/dialogs/walk/strip"
import { BOX, STEPS, spotFor, stepsFor } from "./Tour"

const rect = (left: number, top: number, width: number, height: number) => ({ left, top, width, height, right: left + width, bottom: top + height })
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

  it("go round every page, a page's steps together, and back to the calendar to end", () => {
    // 30 Oct: "make it more in depth"
    const pages = STEPS.map((s) => s.page ?? "/")
    expect(new Set(pages)).toEqual(new Set(["/", "/todo", "/inbox", "/projects", "/rules", "/insights", "/body", "/settings"]))
    const runs = pages.filter((p, i) => i === 0 || p !== pages[i - 1])
    expect(runs.slice(0, -1)).toEqual([...new Set(pages)]) // each page visited once, then home
    expect(runs[runs.length - 1]).toBe("/")
  })
})

describe("what the tour says", () => {
  it("is short, in a few bullet points a step", () => {
    // 30 Oct: "make it a little shorter... keep text to bullet points"
    expect(STEPS.filter((s) => !s.optional).length).toBeLessThanOrEqual(13)
    for (const s of STEPS) {
      expect(s.bullets.length).toBeGreaterThanOrEqual(1)
      expect(s.bullets.length).toBeLessThanOrEqual(3)
      for (const line of s.bullets) expect(line.length).toBeLessThanOrEqual(52)
    }
  })

  it("hops and cheers at the start, and ends off to the weekend", () => {
    expect(STEPS[0].jump && STEPS[0].cheer).toBe(true)
    const end = STEPS[STEPS.length - 1]
    expect(end.finale && end.gesture === "dance").toBe(true)
  })

  it("does something of its own at nearly every step", () => {
    // 30 Oct: "dont just have the guide jump - be creative, have the guide do unique actions"
    const doing = STEPS.filter((s) => !s.optional).map((s) => s.gesture ?? "point")
    expect(new Set(doing).size).toBeGreaterThanOrEqual(doing.length - 2)
  })
})

describe("where the guide stands and their box goes", () => {
  const fits = (s: ReturnType<typeof spotFor>, size = win) => s.left >= 12 && s.left + s.width <= size.width - 12

  it("the two side by side in the middle when the step points at nothing", () => {
    const s = spotFor(null, win)
    expect(s.left).toBeGreaterThan(s.x)
    expect(Math.abs(s.x + (s.left + s.width - s.x) / 2 - win.width / 2)).toBeLessThan(60)
  })

  it("below a control up the window, pointing at it, the box on the side with room", () => {
    const nav = spotFor(rect(0, 0, 248, 900), win)
    expect(nav.x).toBeCloseTo(124)
    expect(nav.left).toBeGreaterThan(nav.x)
    const menu = spotFor(rect(1330, 14, 90, 34), win)
    expect(menu.x).toBeGreaterThan(1300)
    expect(menu.left + menu.width).toBeLessThan(menu.x)
    expect(fits(nav) && fits(menu)).toBe(true)
  })

  it("beside a control down where they stand, with the box on its far side", () => {
    const dock = rect(260, 900 - 70, 520, 56)
    const s = spotFor(dock, win)
    expect(s.x).toBeGreaterThan(dock.right)
    expect(s.left).toBeGreaterThan(s.x)
    const right = rect(1000, 900 - 70, 420, 56)
    const t = spotFor(right, win)
    expect(t.x).toBeLessThan(right.left)
    expect(t.left + t.width).toBeLessThan(t.x)
  })

  it("on a phone, the box above them, inside the screen", () => {
    const phone = { width: 390, height: 800 }
    const s = spotFor(rect(330, 14, 34, 34), phone)
    expect(s.bottom).toBeGreaterThan(STRIP / 2)
    expect(s.width).toBeLessThanOrEqual(BOX)
    expect(fits(s, phone)).toBe(true)
  })
})
