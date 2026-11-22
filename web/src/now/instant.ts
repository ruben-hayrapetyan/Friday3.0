// What a tap in the Now bar changes, shown the moment you tap (27 Oct): Start, Pause, Done, Eating now, Done eating,
// Skip, the sleep taps and naps changed the bar only once the server had answered and the bar's query had come back, a
// quarter of a second or more, so a tap looked like it hadn't taken. Each is used as its command's `optimistic`
// (hooks/useCommand.ts), which puts things back if the command fails; the refresh after it brings the server's own.

import type { QueryClient } from "@tanstack/react-query"
import type { Schemas } from "@/api/client"
import { nowMin } from "@/hooks/useClock"
import { fromMin, toMin } from "@/lib/time"

type Status = Schemas["StatusOut"]
type Now = Schemas["NowOut"]
type Meals = Schemas["MealsOut"]
type Sleep = Schemas["SleepOut"]

type Timer = Schemas["TimerOut"]

/** Started: the timer at once; `alongside`, what was being timed goes on beside it (2 Nov). */
export function timerStarted(client: QueryClient, input: { id?: number; alongside?: boolean } | null): void {
  const id = input?.id
  if (typeof id !== "number") return
  const it = known(client, id)
  client.setQueryData<Status>(["status"], (s) => s && started(s, id, !!input?.alongside, it?.title ?? null))
  // The bar's main row is the Now query's current: the started one, not what was planned, before the server answers
  // (22 Nov: Resume on "Math read 17.5" showed Math 1920 HW 11, planned then, for the seconds a busy Mac took).
  client.setQueryData<Now>(["now"], (n) => {
    if (!n) return n
    if (n.current?.item_id === id || !it) return { ...n, current_source: "timer" }
    // until its own block ends when one is on now, else until what's left of it runs out, as the server says
    const nowAt = nowMin()
    const own = it.blocks.find((b) => toMin(b.start) <= nowAt + 15 && toMin(b.end) > nowAt)
    const end = own ? own.end : fromMin(nowAt + Math.max(15, it.left ?? 60))
    const current = { key: `T${id}@${fromMin(nowAt)}`, item_id: id, title: it.title, area: it.area, preset: it.preset, start: fromMin(nowAt), end, fixed: false }
    return { ...n, current, current_source: "timer" }
  })
}

type Known = { title: string; area: string | null; preset: string | null; left: number | null; blocks: { start: string; end: string }[] }

/** What the page already has of an item: its detail, its blocks on the plan, a row of it in a list. */
export function known(client: QueryClient, id: number): Known | null {
  let found: Known | null = null
  const take = (x: Record<string, unknown>) => {
    if (typeof x.title !== "string") return
    found ??= { title: x.title, area: (x.area as string | null) ?? null, preset: (x.preset as string | null) ?? null, left: null, blocks: [] }
    const left = (x.remaining_min ?? x.duration_min) as number | null | undefined
    if (found.left === null && typeof left === "number") found.left = left
    if (x.item_id === id && typeof x.start === "string" && typeof x.end === "string") found.blocks.push({ start: x.start, end: x.end })
  }
  const detail = client.getQueryData<{ item?: Record<string, unknown> }>(["item", id])?.item
  if (detail) take(detail)
  const matches = (x: unknown): x is Record<string, unknown> =>
    !!x && typeof x === "object" && ((x as { item_id?: unknown }).item_id === id || ((x as { id?: unknown }).id === id && "status" in x))
  for (const [, data] of client.getQueriesData<unknown>({ predicate: (q) => ["plan", "items", "now", "calendar"].includes(String(q.queryKey[0])) })) {
    const lists = Array.isArray(data) ? [data] : data && typeof data === "object" ? Object.values(data as object).filter(Array.isArray) : []
    for (const list of lists) for (const x of list as unknown[]) if (matches(x)) take(x)
  }
  return found
}

export function started(s: Status, id: number, alongside: boolean, title: string | null = null): Status {
  const timer: Timer = { item_id: id, title, started: fromMin(nowMin()), minutes: 0, elapsed_s: 0 }
  const others = [...(s.alongside ?? []), ...(s.timer ? [s.timer] : [])].filter((t) => t.item_id !== id)
  return { ...s, timer, alongside: alongside ? others : [] }
}

/** Stopped: that one goes (`id`, else the timer), and the one started last of the rest is the timer. */
export function timerStopped(client: QueryClient, input: { id?: number | null; done?: boolean } | null): void {
  const s = client.getQueryData<Status>(["status"])
  const wasTimer = !s?.timer || input?.id == null || input.id === s.timer.item_id
  client.setQueryData<Status>(["status"], (x) => x && stopped(x, input?.id ?? null))
  if (input?.done && wasTimer) client.setQueryData<Now>(["now"], (n) => n && { ...n, current: null })
}

export function stopped(s: Status, id: number | null): Status {
  const rest = s.alongside ?? []
  if (id != null && s.timer?.item_id !== id) return { ...s, alongside: rest.filter((t) => t.item_id !== id) }
  return { ...s, timer: rest.length ? rest[rest.length - 1] : null, alongside: rest.slice(0, -1) }
}

export function markedDone(client: QueryClient, input: { id?: number } | null): void {
  client.setQueryData<Now>(["now"], (n) => n && (n.current?.item_id === input?.id ? { ...n, current: null } : n))
}

export function mealStarted(client: QueryClient, input: { kind?: string } | null): void {
  const kind = input?.kind ?? "snack"
  const start = fromMin(nowMin())
  const eating = { id: -1, kind, date: start.slice(0, 10), start, end: null, minutes: null, skipped: false }
  client.setQueryData<Meals>(["meals"], (m) => m && { ...m, eating, next: null })
}

export function mealEnded(client: QueryClient): void {
  client.setQueryData<Meals>(["meals"], (m) => m && { ...m, eating: null, next: null })
}

export function mealSkipped(client: QueryClient): void {
  client.setQueryData<Meals>(["meals"], (m) => m && { ...m, next: null })
}

/** A sleep tap made: the row goes until the server says which tap fits next. */
export function sleepMarked(client: QueryClient): void {
  client.setQueryData<Sleep>(["sleep"], (s) => s && { ...s, next: null })
}

/** Taking a nap: the bar says so at once, and offers no other sleep tap while you nap. */
export function napStarted(client: QueryClient): void {
  const start = fromMin(nowMin())
  client.setQueryData<Sleep>(["sleep"], (s) => s && { ...s, next: null, napping: { id: -1, date: start.slice(0, 10), start, end: null, minutes: null } })
}

export function napEnded(client: QueryClient): void {
  client.setQueryData<Sleep>(["sleep"], (s) => s && { ...s, napping: null })
}
