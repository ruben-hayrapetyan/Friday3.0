// Which plan the last change needs (17 Nov: "the user can see that friday is replanning when you change the
// preferences"): a change answers with the generation it made; the plan catches up to it after.

import { useSyncExternalStore } from "react"

let wanted = 0
const listeners = new Set<() => void>()

/** A change answered with this generation: a plan of at least it is coming. */
export function expectPlan(generation: number | null | undefined): void {
  if (!generation || generation <= wanted) return
  wanted = generation
  listeners.forEach((f) => f())
}

export function useWantedPlan(): number {
  return useSyncExternalStore(
    (f) => (listeners.add(f), () => listeners.delete(f)),
    () => wanted,
  )
}

/** Whether a plan is still being made: the server's is behind its changes, or behind the last one sent. */
export function replanning(status: { generation: number; plan_generation: number | null } | undefined, want: number): boolean {
  if (!status || status.plan_generation === null) return false
  return status.plan_generation < Math.max(status.generation, want)
}
