// Random projects for the bar's rules (27 Nov, "Friday Notes-3": the bar passed an open diamond; three diamonds for
// seven steps). The user asked for "hundreds + random tests": thousands of generated projects, each checked against
// the rules rather than against an answer written down. A seeded generator, so a failure can be replayed.
import { describe, expect, it } from "vitest"
import { at, diamonds, milestones, reached, share } from "./model"

const TODAY = "2026-11-16"
function rng(seed: number) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
const day = (n: number) => {
  const d = new Date(`${TODAY}T12:00:00`)
  d.setDate(d.getDate() + n)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

function project(r: () => number) {
  const int = (lo: number, hi: number) => lo + Math.floor(r() * (hi - lo + 1))
  const due = `${day(int(1, 40))}T23:59`
  const steps = Array.from({ length: int(0, 9) }, (_, i) => {
    const kind = r()
    const own = kind < 0.2 ? null : kind < 0.3 ? due : `${day(int(-5, 45))}T${["09:00", "17:00", "23:59"][int(0, 2)]}`
    return { id: i + 1, title: `Step ${i + 1}`, done: r() < 0.4, minutes: int(15, 300), due: own }
  })
  const totalMin = steps.reduce((s, x) => s + x.minutes, 0) || int(30, 600)
  return { steps, due, doneMin: int(0, totalMin), totalMin }
}

const CASES = 3000

describe("the bar's fill, over random projects", () => {
  it("is between empty and full, reaches every done diamond, and never passes an open one ahead unless a later one is done", () => {
    for (let seed = 1; seed <= CASES; seed++) {
      const p = project(rng(seed))
      const end = at(p.due, TODAY)
      const on = (due: string) => at(due, TODAY) / end
      const fill = reached(p, TODAY)
      const all = milestones(p)
      const said = `seed ${seed}: ${JSON.stringify(p)}`
      expect(fill, said).toBeGreaterThanOrEqual(0)
      expect(fill, said).toBeLessThanOrEqual(1)
      for (const m of all.filter((x) => x.done)) expect(fill, said).toBeGreaterThanOrEqual(Math.min(1, on(m.due as string)) - 1e-9)
      const open = all.filter((x) => !x.done && on(x.due as string) > 0)
      if (open.length) {
        const first = Math.min(...open.map((x) => on(x.due as string)))
        const doneAfter = all.some((x) => x.done && on(x.due as string) > first)
        if (!doneAfter) expect(fill, said).toBeLessThanOrEqual(first + 1e-9)
        expect(fill, said).toBeGreaterThanOrEqual(Math.min(share(p), first) - 1e-9)
      } else expect(fill, said).toBeGreaterThanOrEqual(share(p) - 1e-9)
    }
  })
})

describe("the bar's diamonds, over random projects", () => {
  it("are one a day a step is due by the project's due, soonest first, naming every such step once, done when all are", () => {
    for (let seed = 1; seed <= CASES; seed++) {
      const p = project(rng(seed))
      const said = `seed ${seed}: ${JSON.stringify(p)}`
      const shown = diamonds(p)
      const days = shown.map((d) => d.due.slice(0, 10))
      expect(new Set(days).size, said).toBe(days.length) // one a day
      expect([...days].sort(), said).toEqual(days) // soonest first
      const due = p.steps.filter((s) => s.due && s.due <= p.due)
      expect(shown.flatMap((d) => d.titles).sort(), said).toEqual(due.map((s) => s.title).sort()) // each step once
      for (const d of shown) {
        const there = due.filter((s) => (s.due as string).slice(0, 10) === d.due.slice(0, 10))
        expect(d.done, said).toBe(there.every((s) => s.done))
      }
      expect(p.steps.filter((s) => !s.due || s.due > p.due).some((s) => shown.some((d) => d.titles.includes(s.title))), said).toBe(false)
    }
  })
})
