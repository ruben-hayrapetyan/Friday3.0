import { afterEach, describe, expect, it } from "vitest"
import type { Block, Item } from "@/api/client"
import { current, inARow, itemsOf, type Pick, picks, shifted } from "./picks"

const block = (itemId: number, start: string, end: string): Pick => ({ key: `T${itemId}@${start}`, itemId, title: `T${itemId}`, start, end, event: false })
const event = (id: number, start: string, end: string): Pick => ({ key: `F${id}`, itemId: id, title: `E${id}`, start, end, event: true })

afterEach(() => picks.clear())

describe("picking on the calendar", () => {
  it("the first ⌘-click picks what was selected too, and a second takes one back off", () => {
    const a = block(1, "2026-10-27T09:00", "2026-10-27T10:00")
    const b = block(2, "2026-10-27T11:00", "2026-10-27T12:00")
    picks.toggle(b, a)
    expect(picks.get().map((p) => p.key)).toEqual([a.key, b.key])
    picks.toggle(a, null)
    expect(picks.get().map((p) => p.key)).toEqual([b.key])
  })

  it("⌘-clicking the selected block picks it alone", () => {
    const a = block(1, "2026-10-27T09:00", "2026-10-27T10:00")
    picks.toggle(a, a)
    expect(picks.get()).toEqual([a])
  })

  it("a task with two picked blocks is one task", () => {
    expect(itemsOf([block(1, "2026-10-27T09:00", "2026-10-27T10:00"), block(1, "2026-10-28T09:00", "2026-10-28T10:00"), event(5, "2026-10-27T12:00", "2026-10-27T13:00")])).toEqual([1, 5])
    expect(itemsOf([block(1, "2026-10-27T09:00", "2026-10-27T10:00"), event(5, "2026-10-27T12:00", "2026-10-27T13:00")], true)).toEqual([1])
  })
})

describe("moving the picks together", () => {
  const a = block(1, "2026-10-27T09:00", "2026-10-27T10:00")
  const b = block(1, "2026-10-27T10:00", "2026-10-27T11:30")
  const e = event(7, "2026-10-27T23:00", "2026-10-28T00:30")

  it("each moves by as much and keeps its length, across midnight and days", () => {
    const moved = shifted([a, e], 24 * 60 + 30)
    expect(moved.map((p) => [p.start, p.end])).toEqual([
      ["2026-10-28T23:30", "2026-10-29T01:00"],
      ["2026-10-28T09:30", "2026-10-28T10:30"],
    ])
  })

  it("a moved block takes the key its new start gives it; an event keeps its own", () => {
    const [moved, ev] = shifted([a, e], -60).sort((x, y) => x.itemId - y.itemId)
    expect(moved.key).toBe("T1@2026-10-27T08:00")
    expect(ev.key).toBe("F7")
    expect(moved.from).toEqual(a)
  })

  it("the furthest along moves first, so no new pin lands on a block not moved yet", () => {
    expect(shifted([a, b], 30).map((p) => p.from.start)).toEqual([b.start, a.start])
    expect(shifted([b, a], -30).map((p) => p.from.start)).toEqual([a.start, b.start])
    // Neither new span overlaps where the other is still pinned when its own pin is made.
    const [first, second] = shifted([a, b], 30)
    expect(first.start >= second.from.end).toBe(true)
  })
})

describe("to-do rows dropped together", () => {
  it("are planned one after another, each for what's left of it", () => {
    const start = Date.UTC(2026, 9, 27, 22, 30) / 60000
    const placed = inARow([{ id: 1, title: "Essay", length: 90 }, { id: 2, title: "Reading", length: 45 }], start)
    expect(placed.map((p) => [p.itemId, p.start, p.end])).toEqual([
      [1, "2026-10-27T22:30", "2026-10-28T00:00"],
      [2, "2026-10-28T00:00", "2026-10-28T00:45"],
    ])
  })
})

describe("picks follow the plan", () => {
  const a = block(1, "2026-10-27T09:00", "2026-10-27T10:00")
  const e = event(7, "2026-10-27T23:00", "2026-10-28T00:30")
  const asPlanned = (p: Pick, pinned: Block["pinned"] = null) => ({ key: p.key, item_id: p.itemId, title: p.title, start: p.start, end: p.end, pinned }) as Block
  const asEvent = (p: Pick, start = p.start, end = p.end) => ({ id: p.itemId, title: p.title, start, end }) as Item

  it("nothing changed: the same list, so nothing redraws", () => {
    const list = [a, e]
    expect(current(list, [asPlanned(a)], [asEvent(e)])).toBe(list)
  })

  it("a block the plan put elsewhere is let go; an event takes its new time; a pin is noted", () => {
    expect(current([a, e], [], [asEvent(e, "2026-10-27T22:00", "2026-10-27T23:30")])).toEqual([{ ...e, start: "2026-10-27T22:00", end: "2026-10-27T23:30" }])
    expect(current([a], [asPlanned(a, "preferred")], [])[0].pinned).toBe("preferred")
  })

  it("a block joined to more of its task planned beside it stays picked, as the joined block", () => {
    const joined = block(1, "2026-10-27T08:15", "2026-10-27T10:00")
    expect(current([a], [asPlanned(joined)], [])).toEqual([{ ...joined, title: a.title, pinned: null }])
    expect(current([a], [asPlanned(block(2, "2026-10-27T08:15", "2026-10-27T10:00"))], [])).toEqual([]) // another task's
  })
})
