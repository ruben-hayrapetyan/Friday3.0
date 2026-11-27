// Random events and tasks for the whole-day and open-at rules (27 Nov, "Friday Notes-3": a birthday, all day, asked
// "Is this time for TC/HS Detection?", a task due before it). Thousands of generated cases, seeded.
import { describe, expect, it } from "vitest"
import { openAt, wholeDay } from "./holds"

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
const p2 = (n: number) => String(n).padStart(2, "0")
const stamp = (day: number, minute: number) => {
  const d = new Date(Date.UTC(2026, 10, 1 + day))
  return `${d.getUTCFullYear()}-${p2(d.getUTCMonth() + 1)}-${p2(d.getUTCDate())}T${p2(Math.floor(minute / 60))}:${p2(minute % 60)}`
}

describe("a whole day, over random events", () => {
  it("is exactly midnight to a later midnight", () => {
    for (let seed = 1; seed <= 4000; seed++) {
      const r = rng(seed)
      const int = (n: number) => Math.floor(r() * n)
      const day = int(60)
      const midnightStart = r() < 0.4
      const startMin = midnightStart ? 0 : int(24 * 4) * 15
      const len = r() < 0.4 ? (1 + int(4)) * 1440 : (1 + int(16)) * 15
      const endAbs = day * 1440 + startMin + len
      const start = stamp(day, startMin)
      const end = stamp(Math.floor(endAbs / 1440), endAbs % 1440)
      const expected = startMin === 0 && endAbs % 1440 === 0 && len > 0
      expect(wholeDay({ start, end }), `seed ${seed}: ${start} to ${end}`).toBe(expected)
    }
  })
})

describe("the tasks an event's time could be for, over random tasks", () => {
  it("are those still to do when it starts: none due before it, every one without a due, none lost or added", () => {
    for (let seed = 1; seed <= 2000; seed++) {
      const r = rng(seed)
      const int = (n: number) => Math.floor(r() * n)
      const start = stamp(int(30), int(96) * 15)
      const tasks = Array.from({ length: int(12) }, (_, id) => ({ id, due: r() < 0.25 ? null : stamp(int(30), int(96) * 15) }))
      const open = openAt(tasks, start)
      const said = `seed ${seed}: ${start} ${JSON.stringify(tasks)}`
      expect(open.every((t) => tasks.includes(t)), said).toBe(true)
      expect(open.some((t) => t.due !== null && t.due < start), said).toBe(false)
      expect(tasks.filter((t) => t.due === null || t.due >= start).length, said).toBe(open.length)
      expect(openAt(tasks, null), said).toEqual(tasks)
    }
  })
})
