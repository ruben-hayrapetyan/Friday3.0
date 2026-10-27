// What if: changes staged on the calendar instead of made. While it's on, and only on the Plan page, what you do there
// (add, move or delete an event, move a block, add a to-do, shove, a rule) is kept here rather than sent, and the
// calendar shows the plan with them (`whatif`); Keep makes them all as one change (`whatif_keep`). Elsewhere everything
// saves as usual. An item a staged change makes has no id until it's made: a later change naming it uses a
// placeholder, -(1000 × that change's place + the item's place + 1), as the server resolves them (commands/whatif.py).
//
// Like a calendar app's tentative events, a change shows the moment you make it (`trialView`): a moved block moves, a
// new event appears dashed, a deleted one fades struck through; the planned week replaces that when its answer comes.
// Moves are said against your real plan ("moved from Tue 4pm") for as long as you're trying.

import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { useEffect, useState, useSyncExternalStore } from "react"
import { queryBody, type Schemas } from "@/api/client"
import { addDays } from "@/lib/time"

export type Change = Schemas["WhatIfChange"]
type Plan = Schemas["PlanOut"]
type Fixed = Plan["fixed"][number]
type Block = Plan["blocks"][number]

const STAGED = new Set<string>(["add", "edit", "series_add", "shove", "rule_add", "pin", "unpin", "day_override", "skip", "drop", "repeat"])
const ID_KEYS = new Set(["id", "item_id", "depends_on_id", "ids"])
const PLACE = 1000
export const SPAN_DAYS = 21 // the trial is planned from yesterday this many days on, so moving around the weeks needs no new try
const SETTLE_MS = 350 // changes made within this of each other are planned once

interface State {
  on: boolean
  here: boolean // the Plan page is showing: only there is a change staged
  panel: boolean // the changes panel is open
  changes: Change[]
  made: number[][] // the items each change made in the latest answer, as the trial calendar shows them
  answer: { changes: Change[]; out: Schemas["WhatIfOut"] } | null // the latest answer, and the changes it answered
}

let state: State = { on: false, here: false, panel: true, changes: [], made: [], answer: null }
const listeners = new Set<() => void>()

function set(next: Partial<State>) {
  state = { ...state, ...next }
  for (const listener of listeners) listener()
}

export const placeholder = (change: number, item = 0) => -(PLACE * change + item + 1)

/** An id the trial calendar shows for an item a staged change made, as its placeholder. */
function placeheld(value: unknown, key = ""): unknown {
  if (Array.isArray(value)) return value.map((v) => placeheld(v, key))
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, placeheld(v, k)]))
  if (!ID_KEYS.has(key) || typeof value !== "number" || value < 0) return value
  for (const [change, ids] of state.made.entries()) {
    const at = ids.indexOf(value)
    if (at >= 0) return placeholder(change, at)
  }
  return value
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
  start: () => set({ on: true, panel: true, changes: [], made: [], answer: null }),
  stop: () => set({ on: false, changes: [], made: [], answer: null }),
  here: (here: boolean) => set({ here }),
  showPanel: (panel: boolean) => set({ panel }),
  /** Whether this command is staged rather than sent. */
  stages: (name: string) => state.on && state.here && STAGED.has(name),
  stage(command: string, input: Record<string, unknown>) {
    set({ changes: [...state.changes, { command: command as Change["command"], input: placeheld(input) as Record<string, never> }] })
  },
  /** A change put another way: a tried event's drawer saved again, which stays the one change it was. */
  replace(at: number, input: Record<string, unknown>) {
    set({ changes: state.changes.map((c, i) => (i === at ? { ...c, input: placeheld(input) as Record<string, never> } : c)) })
  },
  remove(at: number) {
    const changes = state.changes.filter((_, i) => i !== at).map((c) => ({ ...c, input: shifted(c.input, at) as Record<string, never> }))
    set({ changes, made: state.made.filter((_, i) => i !== at) })
  },
  /** ⌘Z while trying: the last change taken back, never one of your real ones. */
  undoLast(): boolean {
    if (!state.changes.length) return false
    whatIf.remove(state.changes.length - 1)
    return true
  },
  /** The change that made this item (a tried event), if one did. */
  madeBy(id: number | null | undefined): number | null {
    if (id == null) return null
    if (id < 0) {
      const change = Math.floor((-id - 1) / PLACE)
      return change < state.changes.length ? change : null
    }
    const at = state.made.findIndex((ids) => ids.includes(id))
    return at >= 0 ? at : null
  },
  learned(changes: Change[], out: Schemas["WhatIfOut"]) {
    if (state.on) set({ made: out.changes.map((c) => c.created ?? []), answer: { changes, out } })
  },
}

export function useWhatIf(): State {
  return useSyncExternalStore(whatIf.subscribe, whatIf.get)
}

/** What the calendar shows of a tried change: made by one (dashed), changed by one (outlined), or deleted (faded). */
export interface Tried {
  made: Set<number>
  changed: Set<number>
  gone: Set<number>
  moved: Map<number, string> // item → where its first block was in your plan
  pending: boolean // changes staged since the last answer: drawn as tried, the week around them not planned yet
}
export type TrialPlan = Plan & { tried?: Tried }

function useSettled<T>(value: T, ms: number): T {
  const [settled, setSettled] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), ms)
    return () => clearTimeout(timer)
  }, [value, ms])
  return settled
}

/** The staged changes tried: the calendar with them and what they cost. Planned again only when they change. */
export function useTrial(today: string) {
  const w = useWhatIf()
  const changes = useSettled(w.changes, SETTLE_MS)
  const start = `${addDays(today, -1)}T00:00`
  const end = `${addDays(today, SPAN_DAYS)}T00:00`
  const q = useQuery({
    queryKey: ["whatif", changes, start, end],
    queryFn: () => queryBody("whatif", { changes, start, end }),
    enabled: w.on && changes.length > 0,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    retry: false,
  })
  useEffect(() => {
    if (q.data && !q.isPlaceholderData) whatIf.learned(changes, q.data)
  }, [q.data, q.isPlaceholderData, changes])
  // The latest answer stands for the changes it answered that are still as they were, in order.
  const answered = w.answer ? leading(w.answer.changes, w.changes) : 0
  const planning = w.changes.length > 0 && answered < w.changes.length && !q.isError
  return { out: w.answer?.out, answered, planning, error: q.error, refetch: q.refetch }
}

/** How many of the first changes are the same in both. */
export function leading(a: Change[], b: Change[]): number {
  let n = 0
  while (n < a.length && n < b.length && JSON.stringify(a[n]) === JSON.stringify(b[n])) n += 1
  return n
}

/** The part of a plan in [start, end). */
export function within(plan: Plan, start: string, end: string): Plan {
  const overlaps = (x: { start?: string | null; end?: string | null }) => !!x.start && !!x.end && x.start < end && x.end > start
  return {
    ...plan,
    blocks: plan.blocks.filter(overlaps),
    fixed: plan.fixed.filter(overlaps),
    sessions: (plan.sessions ?? []).filter(overlaps),
    day_hours: Object.fromEntries(Object.entries(plan.day_hours).filter(([d]) => d >= start.slice(0, 10) && d < end.slice(0, 10))),
  }
}

const firsts = (blocks: Block[]) => {
  const out = new Map<number, string>()
  for (const b of [...blocks].sort((a, c) => a.start.localeCompare(c.start))) if (!out.has(b.item_id)) out.set(b.item_id, b.start)
  return out
}

/** The calendar while trying: the latest answer (or your plan, before the first), with the changes made since drawn
 * at once, deleted events kept faded, and each block that moved said against your plan. */
export function trialView(real: Plan, answer: Schemas["WhatIfOut"] | undefined, changes: Change[], answered: number): TrialPlan {
  const base: Plan = answer && answered > 0 ? answer.plan : real
  const made = new Set<number>()
  const changed = new Set<number>()
  const gone = new Set<number>()
  for (const [i, c] of (answer?.changes ?? []).entries()) {
    if (i >= answered) break
    for (const id of c.created ?? []) made.add(id)
    for (const id of c.changed ?? []) changed.add(id)
  }
  // What the answer made for changes since put another way or taken out isn't there any more (an event moved in its
  // drawer was drawn twice: where the answer had it, and where you put it).
  const stale = new Set((answer?.changes ?? []).slice(answered).flatMap((c) => c.created ?? []))
  let fixed: Fixed[] = base.fixed.filter((f) => !stale.has(f.id))
  let blocks: Block[] = base.blocks.filter((b) => !stale.has(b.item_id))
  for (const [i, c] of changes.entries()) {
    const input = c.input as Record<string, unknown>
    const id = typeof input.id === "number" ? input.id : null
    if ((c.command === "drop" || c.command === "skip") && id !== null) gone.add(id)
    if (i < answered) continue
    // Not planned yet: drawn as you made it.
    if (c.command === "add" && input.when === "fixed" && typeof input.start === "string" && typeof input.end === "string") {
      const temp = placeholder(i)
      made.add(temp)
      fixed.push({ ...EMPTY_EVENT, id: temp, title: String(input.title ?? "New event"), start: input.start, end: input.end, color: (input.color as string | null) ?? null } as unknown as Fixed)
    } else if (c.command === "edit" && id !== null) {
      changed.add(id)
      fixed = fixed.map((f) => (f.id === id ? { ...f, ...pick(input, ["title", "start", "end", "color"]) } : f))
    } else if (c.command === "pin" && id !== null && typeof input.start === "string" && typeof input.end === "string") {
      changed.add(id)
      const from = input.from_start
      blocks = blocks.map((b) => (b.item_id === id && (from === undefined || b.start === from) ? { ...b, start: input.start as string, end: input.end as string } : b))
    }
  }
  // A deleted event the answer no longer has stays where it was, faded, so you see what went.
  const shown = new Set(fixed.map((f) => f.id))
  fixed = [...fixed, ...real.fixed.filter((f) => gone.has(f.id) && !shown.has(f.id))]
  const was = firsts(real.blocks)
  const now = firsts(blocks)
  const moved = new Map<number, string>()
  for (const [item, start] of now) {
    const before = was.get(item)
    if (before && before !== start) moved.set(item, before)
  }
  return { ...base, fixed, blocks, tried: { made, changed, gone, moved, pending: answered < changes.length } }
}

const pick = (input: Record<string, unknown>, keys: string[]) => Object.fromEntries(keys.filter((k) => input[k] !== undefined).map((k) => [k, input[k]]))

const EMPTY_EVENT = {
  preset: "Event",
  area: null,
  tags: [],
  parent_id: null,
  when: "fixed",
  release: null,
  due: null,
  amount: "fixed",
  duration_min: null,
  firmness: "soft",
  status: "todo",
  event_kind: "other",
  blocks_time: true,
  notes: "",
}
