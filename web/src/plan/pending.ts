// A change to the calendar shows the moment you make it and stays until the plan has it (27 Oct). It was written into
// the plan's cache, so the refresh every change sets off redrew the plan from before it: a dragged block went back
// to where it had been until the replan, and a click looked like it hadn't taken. Now each change's look is kept
// here, laid over every plan the calendar draws (`plan/shown.ts`), until a plan comes that has seen the change: one
// whose `generation` has reached the change's. A change that fails is taken back at once.

import { useEffect, useMemo, useSyncExternalStore } from "react"
import type { Schemas } from "@/api/client"

type Plan = Schemas["PlanOut"]

interface Patch {
  id: number
  generation: number | null // the change's, once it has answered; null while it's on its way
  at: number
  apply: (plan: Plan) => Plan
}

const LONGEST_MS = 120_000 // a change no plan has shown by then (the planner stopped) isn't drawn any longer

let patches: Patch[] = []
let collecting: number[] | null = null
let next = 1
let version = 0
const listeners = new Set<() => void>()

function changed() {
  version += 1
  for (const listener of listeners) listener()
}

export const pending = {
  subscribe(listener: () => void) {
    listeners.add(listener)
    return () => void listeners.delete(listener)
  },
  version: () => version,
  /** Draw `apply` over the plan until the change it's part of is in it. */
  add(apply: (plan: Plan) => Plan): void {
    const id = next++
    patches = [...patches, { id, generation: null, at: Date.now(), apply }]
    collecting?.push(id)
    changed()
  },
  /** The patches `run` adds: one change's look. */
  collect(run: () => void): number[] {
    const was = collecting
    collecting = []
    try {
      run()
      return collecting
    } finally {
      collecting = was
    }
  },
  /** The change answered: its look stays until a plan has seen `generation`. */
  settle(ids: number[], generation: number): void {
    if (!ids.length) return
    patches = patches.map((p) => (ids.includes(p.id) ? { ...p, generation } : p))
    changed()
  },
  /** The change failed: its look goes. */
  drop(ids: number[]): void {
    if (!ids.length) return
    patches = patches.filter((p) => !ids.includes(p.id))
    changed()
  },
  /** `plan` with the changes it hasn't seen yet laid over it, oldest first. */
  apply(plan: Plan): Plan {
    const now = Date.now()
    const seen = plan.generation ?? 0
    const open = patches.filter((p) => (p.generation === null || p.generation > seen) && now - p.at < LONGEST_MS)
    return open.reduce((shown, p) => p.apply(shown), plan)
  },
  /** Let go of what a plan has seen. */
  forget(generation: number): void {
    const now = Date.now()
    const kept = patches.filter((p) => (p.generation === null || p.generation > generation) && now - p.at < LONGEST_MS)
    if (kept.length !== patches.length) {
      patches = kept
      changed()
    }
  },
  clear(): void {
    patches = []
    changed()
  },
}

/** A plan with the changes it hasn't seen yet laid over it (plan/pending.ts); what it has seen let go. */
export function usePending<Q extends { data?: Schemas["PlanOut"] }>(q: Q): Q {
  const version = useSyncExternalStore(pending.subscribe, pending.version)
  const generation = q.data?.generation
  useEffect(() => {
    if (generation !== undefined) pending.forget(generation)
  }, [generation])
  const data = useMemo(() => (q.data ? pending.apply(q.data) : q.data), [q.data, version])
  return data === q.data ? q : { ...q, data }
}
