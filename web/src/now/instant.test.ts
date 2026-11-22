// Timing two things at once (2 Nov), shown the moment you tap: what the Now bar shows before the server answers.
import { QueryClient } from "@tanstack/react-query"
import { describe, expect, it } from "vitest"
import type { Schemas } from "@/api/client"
import { nowMin } from "@/hooks/useClock"
import { fromMin } from "@/lib/time"
import { started, stopped, timerStarted } from "./instant"

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


// 22 Nov, the user: Resume on "Math read 17.5" seemed to start Math 1920 HW 11. The timer took the started task at
// once, but the bar's main row is the Now query's current, still the planned Math 1920 HW 11 until the server answered
// (seconds, on a busy Mac), so it showed that one as what you were on.
describe("the Now bar the moment you start", () => {
  const block = (item_id: number, title: string) => ({ key: `T${item_id}@2026-11-22T13:00`, item_id, title, area: "MATH 1920", preset: "Assignment", start: "2026-11-22T13:00", end: "2026-11-22T15:00", fixed: false })
  const planned = () => {
    const client = new QueryClient()
    client.setQueryData(["status"], status(null))
    client.setQueryData(["now"], { current: block(7, "Math 1920 HW 11"), current_source: "block", next: null })
    return client
  }
  const now = (client: QueryClient) => client.getQueryData<Schemas["NowOut"]>(["now"])

  it("shows the task you started, named, not what was planned", () => {
    const client = planned()
    client.setQueryData(["item", 9], { item: { id: 9, title: "Math read 17.5", area: "MATH 1920", preset: "Reading", status: "todo" } })
    timerStarted(client, { id: 9 })
    expect(now(client)?.current).toMatchObject({ item_id: 9, title: "Math read 17.5", area: "MATH 1920", preset: "Reading", fixed: false })
    expect(now(client)?.current_source).toBe("timer")
    expect(client.getQueryData<Status>(["status"])?.timer).toMatchObject({ item_id: 9, title: "Math read 17.5" })
  })

  it("finds it on the plan, or in a list, when its detail isn't open", () => {
    const client = planned()
    client.setQueryData(["plan", "2026-11-22"], { blocks: [block(7, "Math 1920 HW 11"), block(9, "Math read 17.5")] })
    timerStarted(client, { id: 9 })
    expect(now(client)?.current).toMatchObject({ item_id: 9, title: "Math read 17.5" })
    const other = planned()
    other.setQueryData(["items", { status: "todo" }], [{ id: 9, title: "Math read 17.5", area: null, preset: "Reading", status: "todo" }])
    timerStarted(other, { id: 9 })
    expect(now(other)?.current).toMatchObject({ item_id: 9, title: "Math read 17.5", preset: "Reading" })
  })

  it("runs until its block on now ends, else until what's left of it is done", () => {
    const client = planned()
    const start = fromMin(nowMin() - 30)
    const end = fromMin(nowMin() + 45)
    client.setQueryData(["plan", "today"], { blocks: [{ ...block(9, "Math read 17.5"), start, end }] })
    timerStarted(client, { id: 9 })
    expect(now(client)?.current?.end).toBe(end)
    const other = planned()
    other.setQueryData(["item", 9], { item: { id: 9, title: "Math read 17.5", status: "todo", remaining_min: 50, duration_min: 90 } })
    timerStarted(other, { id: 9 })
    expect(now(other)?.current?.end).toBe(fromMin(nowMin() + 50))
  })

  it("keeps what's on when it's the one started", () => {
    const client = planned()
    timerStarted(client, { id: 7 })
    expect(now(client)?.current).toMatchObject({ item_id: 7, title: "Math 1920 HW 11" })
  })
})
