import { describe, expect, it } from "vitest"
import { AGAIN, ARROW, CHECK, CURSOR, DROP, earlyArt, FLAG, lengthArt, letterDelay, LOGO, MOON, MORE, runs, SUN, WATCH } from "./pixel"

const square = (art: readonly string[]) => new Set(art.map((r) => r.length)).size === 1

describe("sprites", () => {
  it("are drawn row by row, a run of one colour a cell, leaving the clear ones out", () => {
    expect(runs(["kk.y", ".yyy"])).toEqual([
      [0, 0, 2, "k"],
      [3, 0, 1, "y"],
      [1, 1, 3, "y"],
    ])
  })

  it("have rows all the same width, so none is drawn askew", () => {
    for (const art of [SUN, MOON, LOGO, DROP, AGAIN, WATCH, FLAG, CURSOR, MORE, CHECK, ARROW]) expect(square(art)).toBe(true)
    for (const h of [0.75, 1, 1.5, 2, 3, 4, 8]) expect(square(lengthArt(h))).toBe(true)
    for (const d of [0, 1, 2, 3, 5]) expect(square(earlyArt(d))).toBe(true)
  })

  it("show a sitting as long as it is, out of four hours", () => {
    const filled = (h: number) => lengthArt(h)[1].split("").filter((c) => c === "G").length
    expect(filled(1)).toBeLessThan(filled(2))
    expect(filled(2)).toBeLessThan(filled(4))
    expect(filled(8)).toBe(filled(4)) // past four hours, the bar is full
  })

  it("fill the day the work is done, the flag's day for on the day", () => {
    const done = (d: number) => earlyArt(d)[5].split(".").findIndex((cell) => cell.includes("g"))
    expect([done(0), done(1), done(2), done(3), done(7)]).toEqual([3, 2, 1, 0, 0])
  })
})

describe("the typed question", () => {
  it("waits a beat after a sentence or a clause, and not between letters", () => {
    expect(letterDelay(".")).toBeGreaterThan(letterDelay(","))
    expect(letterDelay(",")).toBeGreaterThan(letterDelay("a"))
  })
})
