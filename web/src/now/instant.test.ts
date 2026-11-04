// Timing two things at once (2 Nov), shown the moment you tap: what the Now bar shows before the server answers.
import { describe, expect, it } from "vitest"
import type { Schemas } from "@/api/client"
import { started, stopped } from "./instant"

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
