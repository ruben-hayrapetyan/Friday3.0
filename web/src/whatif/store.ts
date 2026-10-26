// What if: changes staged on the calendar instead of made. While it's on, and only on the Plan page, what you do there
// (add or move an event, skip one, add a task, shove, a rule) is kept here rather than sent, and the calendar shows
// the plan with them (`whatif`); Keep makes them all as one change (`whatif_keep`). Elsewhere everything saves as
// usual. An item a staged change makes has no id until it's made: a later change naming it uses a placeholder,
// -(1000 × that change's place + the item's place + 1), as the server resolves them (commands/whatif.py).

import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { useEffect, useSyncExternalStore } from "react"
import { queryBody, type Schemas } from "@/api/client"
import { addDays } from "@/lib/time"

export type Change = Schemas["WhatIfChange"]
const STAGED = new Set<string>(["add", "edit", "series_add", "shove", "rule_add", "pin", "unpin", "day_override", "skip", "drop"])
const ID_KEYS = new Set(["id", "item_id", "depends_on_id", "ids"])
const PLACE = 1000
export const SPAN_DAYS = 21 // the trial is planned from yesterday this many days on, so moving around the weeks needs no new try

interface State {
  on: boolean
  here: boolean // the Plan page is showing: only there is a change staged
  changes: Change[]
  made: number[][] // the items each change made in the latest try, as the trial calendar shows them
  marked: Set<number> // items the changes make or change, outlined on the calendar
}

let state: State = { on: false, here: false, changes: [], made: [], marked: new Set() }
const listeners = new Set<() => void>()

function set(next: Partial<State>) {
  state = { ...state, ...next }
  for (const listener of listeners) listener()
}

/** An id the trial calendar shows for an item a staged change made, as its placeholder. */
function placeholder(id: unknown): unknown {
  if (typeof id !== "number") return id
  for (const [change, ids] of state.made.entries()) {
    const at = ids.indexOf(id)
    if (at >= 0) return -(PLACE * change + at + 1)
  }
  return id
}

function placeheld(value: unknown, key = ""): unknown {
  if (Array.isArray(value)) return value.map((v) => placeheld(v, key))
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, placeheld(v, k)]))
  return ID_KEYS.has(key) ? placeholder(value) : value
}

/** After taking change `gone` out, the placeholders of later changes point one place earlier. */
function shifted(value: unknown, gone: number, key = ""): unknown {
  if (Array.isArray(value)) return value.map((v) => shifted(v, gone, key))
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, shifted(v, gone, k)]))
  if (ID_KEYS.has(key) && typeof value === "number" && value < 0) {
    const change = Math.floor((-value - 1) / PLACE)
    if (change > gone) return value + PLACE
  }
  return value
}

export const whatIf = {
  get: () => state,
  subscribe(listener: () => void) {
    listeners.add(listener)
    return () => void listeners.delete(listener)
  },
  start: () => set({ on: true, changes: [], made: [], marked: new Set() }),
  stop: () => set({ on: false, changes: [], made: [], marked: new Set() }),
  here: (here: boolean) => set({ here }),
  /** Whether this command is staged rather than sent. */
  stages: (name: string) => state.on && state.here && STAGED.has(name),
  stage(command: string, input: Record<string, unknown>) {
    set({ changes: [...state.changes, { command: command as Change["command"], input: placeheld(input) as Record<string, never> }] })
  },
  remove(at: number) {
    const changes = state.changes.filter((_, i) => i !== at).map((c) => ({ ...c, input: shifted(c.input, at) as Record<string, never> }))
    set({ changes, made: state.made.filter((_, i) => i !== at) })
  },
  learned(out: Schemas["WhatIfOut"]) {
    set({ made: out.changes.map((c) => c.created ?? []), marked: new Set(out.changes.flatMap((c) => [...(c.created ?? []), ...(c.changed ?? [])])) })
  },
}

export function useWhatIf(): State {
  return useSyncExternalStore(whatIf.subscribe, whatIf.get)
}

/** Whether the calendar outlines this item: one the staged changes make or change. */
export function useTried(id: number | null | undefined): boolean {
  const w = useWhatIf()
  return w.on && id != null && w.marked.has(id)
}

/** The staged changes tried: the calendar with them and what they cost. Planned again only when they change. */
export function useTrial(today: string) {
  const w = useWhatIf()
  const start = `${addDays(today, -1)}T00:00`
  const end = `${addDays(today, SPAN_DAYS)}T00:00`
  const q = useQuery({
    queryKey: ["whatif", w.changes, start, end],
    queryFn: () => queryBody("whatif", { changes: w.changes, start, end }),
    enabled: w.on && w.changes.length > 0,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    retry: false,
  })
  useEffect(() => {
    if (q.data && !q.isPlaceholderData) whatIf.learned(q.data)
  }, [q.data, q.isPlaceholderData])
  return q
}

/** The part of the trial calendar in [start, end). */
export function within(plan: Schemas["PlanOut"], start: string, end: string): Schemas["PlanOut"] {
  const overlaps = (x: { start?: string | null; end?: string | null }) => !!x.start && !!x.end && x.start < end && x.end > start
  return {
    ...plan,
    blocks: plan.blocks.filter(overlaps),
    fixed: plan.fixed.filter(overlaps),
    sessions: (plan.sessions ?? []).filter(overlaps),
    day_hours: Object.fromEntries(Object.entries(plan.day_hours).filter(([d]) => d >= start.slice(0, 10) && d < end.slice(0, 10))),
  }
}
