import { describe, expect, it } from "vitest"
import { drawerOver, layoutFor, RAIL, SIDEBAR } from "./layout"

describe("the layout for the window's width", () => {
  it("keeps the whole sidebar on a wide screen, a rail of icons when narrower, and none on a phone", () => {
    expect(layoutFor(1440)).toMatchObject({ mode: "wide", side: SIDEBAR, main: 1440 - SIDEBAR, labels: true, tight: false, weekFits: true })
    expect(layoutFor(1000)).toMatchObject({ mode: "rail", side: RAIL, main: 1000 - RAIL, labels: false, tight: false, weekFits: true })
    expect(layoutFor(390)).toMatchObject({ mode: "narrow", side: 0, main: 390, tight: true, weekFits: false, dayAside: false })
  })

  it("changes at the edges and never goes below nothing", () => {
    expect(layoutFor(1180).mode).toBe("wide")
    expect(layoutFor(1179).mode).toBe("rail")
    expect(layoutFor(760).mode).toBe("rail")
    expect(layoutFor(759).mode).toBe("narrow")
    expect(layoutFor(0)).toMatchObject({ main: 0, tight: true })
  })

  it("shows a week only when seven columns can be read, and the day's panel only beside a wide grid", () => {
    expect(layoutFor(700).weekFits).toBe(false) // a narrow window: the week shows its day
    expect(layoutFor(840).weekFits).toBe(true)
    expect(layoutFor(1440).dayAside).toBe(true)
    expect(layoutFor(1000).dayAside).toBe(false)
  })
})

describe("the to-do drawer", () => {
  it("sits beside the calendar when a week still fits beside it, and slides over it when it wouldn't", () => {
    expect(drawerOver(layoutFor(1440), 340)).toBe(false)
    expect(drawerOver(layoutFor(1000), 340)).toBe(true)
    expect(drawerOver(layoutFor(900), 340)).toBe(true)
    expect(drawerOver(layoutFor(390), 340)).toBe(true)
    expect(drawerOver(layoutFor(1440), 760)).toBe(true) // a drawer dragged very wide
  })
})
