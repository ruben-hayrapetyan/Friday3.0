// What a tap in the Now bar changes, shown the moment you tap (27 Oct): Start, Pause, Done, Eating now, Done eating,
// Skip, the sleep taps and naps changed the bar only once the server had answered and the bar's query had come back, a
// quarter of a second or more, so a tap looked like it hadn't taken. Each is used as its command's `optimistic`
// (hooks/useCommand.ts), which puts things back if the command fails; the refresh after it brings the server's own.

import type { QueryClient } from "@tanstack/react-query"
import type { Schemas } from "@/api/client"
import { nowMin } from "@/hooks/useClock"
import { fromMin } from "@/lib/time"

type Status = Schemas["StatusOut"]
type Now = Schemas["NowOut"]
type Meals = Schemas["MealsOut"]
type Sleep = Schemas["SleepOut"]

export function timerStarted(client: QueryClient, input: { id?: number } | null): void {
  const id = input?.id
  if (typeof id !== "number") return
  client.setQueryData<Status>(["status"], (s) => s && { ...s, timer: { item_id: id, started: fromMin(nowMin()), minutes: 0, elapsed_s: 0 } })
  client.setQueryData<Now>(["now"], (n) => n && { ...n, current_source: "timer" })
}

export function timerStopped(client: QueryClient, input: { done?: boolean } | null): void {
  client.setQueryData<Status>(["status"], (s) => s && { ...s, timer: null })
  if (input?.done) client.setQueryData<Now>(["now"], (n) => n && { ...n, current: null })
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
