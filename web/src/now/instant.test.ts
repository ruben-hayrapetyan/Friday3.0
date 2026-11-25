// Timing two things at once (2 Nov), shown the moment you tap: what the Now bar shows before the server answers.
import { describe, expect, it } from "vitest"
import type { Schemas } from "@/api/client"
import { QueryClient } from "@tanstack/react-query"
import { mealRoutine, started, stopped, timerStarted } from "./instant"

type Status = Schemas["StatusOut"]
const timer = (item_id: number) => ({ item_id, title: `T${item_id}`, started: "2026-11-02T09:00", minutes: 5, elapsed_s: 300 })
const status = (on: number | null, alongside: number[] = []): Status =>
  ({ timer: on == null ? null : timer(on), alongside: alongside.map(timer) }) as unknown as Status
const ids = (s: Status) => ({ timer: s.timer?.item_id ?? null, alongside: (s.alongside ?? []).map((t) => t.item_id) })

describe("starting", () => {
  it("switches: what was timed stops", () => {
    expect(ids(started(status(1, [2]), 3, false))).toEqual({ timer: 3, alongside: [] })
  })
  it("alongside: what was timed goes on beside it, the oldest first", () => {
    expect(ids(started(status(1), 2, true))).toEqual({ timer: 2, alongside: [1] })
    expect(ids(started(status(2, [1]), 3, true))).toEqual({ timer: 3, alongside: [1, 2] })
  })
  it("never shows one thing twice", () => {
    expect(ids(started(status(2, [1]), 1, true))).toEqual({ timer: 1, alongside: [2] })
  })
  it("from nothing, alongside is just a start", () => {
    expect(ids(started(status(null), 4, true))).toEqual({ timer: 4, alongside: [] })
  })
})

describe("stopping", () => {
  it("the timer: the last started of the rest takes its place", () => {
    expect(ids(stopped(status(3, [1, 2]), null))).toEqual({ timer: 2, alongside: [1] })
    expect(ids(stopped(status(3, [1, 2]), 3))).toEqual({ timer: 2, alongside: [1] })
  })
  it("one alongside: only it goes", () => {
    expect(ids(stopped(status(3, [1, 2]), 1))).toEqual({ timer: 3, alongside: [2] })
  })
  it("the last one: nothing is timed", () => {
    expect(ids(stopped(status(3), null))).toEqual({ timer: null, alongside: [] })
  })
  it("starting then stopping alongside gives back what there was", () => {
    const before = status(1)
    expect(ids(stopped(started(before, 2, true), 2))).toEqual(ids(before))
  })
})

// 25 Nov, the user: Start on Dinner timed it and logged no meal. With meals tracked, Start on a meal's routine is that
// meal eaten, shown at once as eating, with no timer the server's answer then takes back.
describe("start on a meal's routine", () => {
  const client = () => {
    const c = new QueryClient()
    c.setQueryData(["meals"], { on: true, eating: null, next: "dinner", days: [], learned: [], changes: [], min_days: 4 })
    c.setQueryData(["status"], { timer: null, alongside: [] })
    c.setQueryData(["items", { status: "todo" }], [
      { id: 7, title: "Dinner", preset: "Routine", series_id: 3 },
      { id: 8, title: "Essay", preset: "Assignment", series_id: null },
    ])
    return c
  }

  it("shows eating that meal, and no timer", () => {
    const c = client()
    timerStarted(c, { id: 7 })
    expect((c.getQueryData(["meals"]) as { eating: { kind: string } }).eating.kind).toBe("dinner")
    expect((c.getQueryData(["status"]) as { timer: unknown }).timer).toBeNull()
  })

  it("times anything else, and a meal's routine when meals aren't tracked", () => {
    const c = client()
    timerStarted(c, { id: 8 })
    expect((c.getQueryData(["status"]) as { timer: { item_id: number } }).timer.item_id).toBe(8)
    c.setQueryData(["meals"], { on: false })
    expect(mealRoutine(c, 7)).toBeNull()
  })
})
