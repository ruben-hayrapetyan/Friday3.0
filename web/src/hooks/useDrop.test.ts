import { QueryClient } from "@tanstack/react-query"
import { describe, expect, it } from "vitest"
import type { Item, Schemas } from "@/api/client"
import type { Drag } from "@/components/calendar/useDrag"
import { toMin } from "@/lib/time"
import { pending } from "@/plan/pending"
import { dueOn, eventDrop, eventUnder, inOrder, moveBlock, placeEvent } from "./useDrop"

const event = (id: number, title: string, start: string, end: string, more: Partial<Item> = {}) => ({ id, title, start, end, when: "fixed", left_out: null, holds: null, event_kind: "other", gives_way_to: null, ...more }) as unknown as Item

describe("the event a task was pinned over", () => {
  const client = new QueryClient()
  client.setQueryData(["plan", "2026-10-27T00:00", "2026-11-03T12:00"], {
    fixed: [
      event(1509, "A4dd", "2026-10-27T21:00", "2026-10-27T23:00"),
      event(2, "Room booking", "2026-10-28T10:00", "2026-10-28T11:00", { left_out: "calendar" }),
      event(3, "Your time", "2026-10-28T14:00", "2026-10-28T15:00", { event_kind: "shove" }),
      event(4, "Gym", "2026-10-28T18:00", "2026-10-28T19:00", { gives_way_to: "Essay" }),
      event(5, "Study block", "2026-10-29T20:00", "2026-10-29T22:00", { holds: { id: 7, title: "Essay" } }),
    ],
  })

  it("is one that keeps work off its time (27 Oct: the design doc over A4dd)", () => {
    expect(eventUnder(client, "2026-10-27T21:30", "2026-10-27T22:30")?.id).toBe(1509)
  })

  it("isn't one that only touches it, keeps nothing off, is shoved time, is skipped for work, or is already for a task", () => {
    expect(eventUnder(client, "2026-10-27T23:00", "2026-10-28T00:00")).toBeNull()
    expect(eventUnder(client, "2026-10-28T10:00", "2026-10-28T11:00")).toBeNull()
    expect(eventUnder(client, "2026-10-28T14:00", "2026-10-28T15:00")).toBeNull()
    expect(eventUnder(client, "2026-10-28T18:00", "2026-10-28T19:00")).toBeNull()
    expect(eventUnder(client, "2026-10-29T20:00", "2026-10-29T21:00")).toBeNull()
  })
})

describe("an event's edge, dragged (29 Oct: events stretch as blocks do)", () => {
  const lecture = { start: toMin("2026-10-29T10:10"), end: toMin("2026-10-29T11:00") }
  const drag = (more: Partial<Drag>): Drag => ({ kind: "resize", ...lecture, grab: 0, itemId: 9, blockKey: null, title: "Lecture", locked: false, at: null, over: "calendar", day: null, moved: true, x: 0, y: 0, event: true, ...more })

  it("gives it a new end from its bottom edge, a new start from its top", () => {
    expect(eventDrop(drag({ at: { start: lecture.start, end: toMin("2026-10-29T11:30") } }))).toEqual({ start: "2026-10-29T10:10", end: "2026-10-29T11:30" })
    expect(eventDrop(drag({ kind: "resize-top", at: { start: toMin("2026-10-29T09:45"), end: lecture.end } }))).toEqual({ start: "2026-10-29T09:45", end: "2026-10-29T11:00" })
  })

  it("changes nothing let go where it was, off the calendar, not dragged, or for a block", () => {
    expect(eventDrop(drag({ at: { ...lecture } }))).toBeNull()
    expect(eventDrop(drag({ over: "todo", at: null }))).toBeNull()
    expect(eventDrop(drag({ moved: false, at: { start: lecture.start, end: toMin("2026-10-29T12:00") } }))).toBeNull()
    expect(eventDrop(drag({ event: false, at: { start: lecture.start, end: toMin("2026-10-29T12:00") } }))).toBeNull()
    expect(eventDrop(drag({ kind: "select", at: { start: lecture.start, end: toMin("2026-10-29T12:00") } }))).toBeNull()
  })

  it("moves it whole: to another time, or another day on the calendar (29 Oct: events that moved)", () => {
    const moved = (more: Partial<Drag>) => eventDrop(drag({ kind: "move", ...more }))
    expect(moved({ at: { start: toMin("2026-10-29T13:25"), end: toMin("2026-10-29T14:15") } })).toEqual({ start: "2026-10-29T13:25", end: "2026-10-29T14:15" })
    expect(moved({ at: { start: toMin("2026-10-31T10:10"), end: toMin("2026-10-31T11:00") } })).toEqual({ start: "2026-10-31T10:10", end: "2026-10-31T11:00" })
    expect(moved({ at: { ...lecture } })).toBeNull() // let go where it was
    expect(moved({ over: "todo", at: null })).toBeNull() // an event has no place in the to-do list
  })

  it("let go on a whole day, keeps its time and length", () => {
    expect(eventDrop(drag({ kind: "move", over: "day", day: "2026-11-02", at: null }))).toEqual({ start: "2026-11-02T10:10", end: "2026-11-02T11:00" })
    expect(eventDrop(drag({ kind: "move", over: "day", day: "2026-10-29", at: null }))).toBeNull() // its own day
    expect(eventDrop(drag({ kind: "resize", over: "day", day: "2026-11-02", at: null }))).toBeNull() // an edge isn't a move
    const late = { start: toMin("2026-10-29T23:30"), end: toMin("2026-10-30T00:30") } // past midnight: still an hour
    expect(eventDrop(drag({ kind: "move", ...late, over: "day", day: "2026-11-02", at: null }))).toEqual({ start: "2026-11-02T23:30", end: "2026-11-03T00:30" })
  })
})

describe("a task dropped on a whole day", () => {
  it("is due that day at the time it was due, or at the end of the day", () => {
    expect(dueOn("2026-11-14", "2026-11-12T17:00")).toBe("2026-11-14T17:00")
    expect(dueOn("2026-11-14", null)).toBe("2026-11-14T23:59")
    expect(dueOn("2026-11-14", "2026-11-12")).toBe("2026-11-14T23:59")
  })
})

describe("moves sent one after another", () => {
  it("run in the order they were made, even when the first is slower, and one that fails doesn't stop the next", async () => {
    const said: string[] = []
    const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))
    const first = inOrder(async () => (await wait(30), said.push("first")))
    const failing = inOrder(async () => {
      said.push("second")
      throw new Error("refused")
    })
    const third = inOrder(async () => said.push("third"))
    await first
    await expect(failing).rejects.toThrow("refused")
    await third
    expect(said).toEqual(["first", "second", "third"])
  })
})

describe("a change shown before the plan has it", () => {
  const plan = (more: Partial<Schemas["PlanOut"]> = {}) => ({ generation: 1, blocks: [], fixed: [], sessions: [], day_hours: {}, ...more }) as unknown as Schemas["PlanOut"]
  const client = new QueryClient()

  it("a pinned block moves where it was let go, with a key for its new start", () => {
    pending.clear()
    const block = { key: "T7@2026-11-14T09:00", item_id: 7, title: "Essay", start: "2026-11-14T09:00", end: "2026-11-14T10:00" }
    moveBlock(client, block.key, "2026-11-14T13:00", "2026-11-14T14:00", "locked")
    const shown = pending.apply(plan({ blocks: [block] as never }))
    expect(shown.blocks[0]).toMatchObject({ key: "T7@2026-11-14T13:00", start: "2026-11-14T13:00", end: "2026-11-14T14:00", pinned: "locked" })
    pending.clear()
  })

  it("an event added shows at once in its category's paint, and steps aside once the plan has it", () => {
    pending.clear()
    placeEvent(client, { title: "Movie", when: "fixed", start: "2026-11-15T20:00", end: "2026-11-15T22:00", color: null }, { category_color: "blue" })
    const shown = pending.apply(plan())
    expect(shown.fixed).toHaveLength(1)
    expect(shown.fixed[0]).toMatchObject({ title: "Movie", start: "2026-11-15T20:00", category_color: "blue", when: "fixed" })
    const real = event(80, "Movie", "2026-11-15T20:00", "2026-11-15T22:00")
    expect(pending.apply(plan({ fixed: [real] })).fixed).toEqual([real])
    pending.clear()
  })

  it("an event moved takes its new time; a change with no times, or a task, shows nothing", () => {
    pending.clear()
    placeEvent(client, { id: 80, start: "2026-11-15T21:00", end: "2026-11-15T23:00" })
    placeEvent(client, { id: 80, title: "No times" })
    placeEvent(client, { title: "A task", start: "2026-11-15T09:00", end: "2026-11-15T10:00" })
    placeEvent(client, null)
    const shown = pending.apply(plan({ fixed: [event(80, "Movie", "2026-11-15T20:00", "2026-11-15T22:00")] }))
    expect(shown.fixed).toHaveLength(1)
    expect(shown.fixed[0]).toMatchObject({ id: 80, start: "2026-11-15T21:00", end: "2026-11-15T23:00" })
    pending.clear()
  })
})
