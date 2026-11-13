// The rules lab's arithmetic, kept apart from the pages so it can be tested: a plan as spans per item, a preview's
// change list applied to it, what a plan looks like in plain numbers, and the dial and ranking mappings.

import type { Block, Schemas } from "@/api/client"
import { dayStartMin } from "@/lib/dayStart"
import { toMin } from "@/lib/time"

export interface RuleSpec {
  type: string
  name: string
  weight: number
  stage?: string | null
  scope?: Record<string, unknown> | null
  reason?: string | null
  params: Record<string, unknown>
  enabled?: boolean
}

type Changes = Schemas["ChangeOut"]
export type Spans = [string, string][]
export type PlanMap = Map<number, { title: string; spans: Spans }>

export function planMap(blocks: Pick<Block, "item_id" | "title" | "start" | "end">[]): PlanMap {
  const out: PlanMap = new Map()
  for (const b of blocks) {
    const entry = out.get(b.item_id) ?? { title: b.title, spans: [] }
    entry.spans.push([b.start, b.end])
    out.set(b.item_id, entry)
  }
  return out
}

/** The plan a preview would make: the saved plan with its change list applied (whole items replaced). */
export function applyChanges(base: PlanMap, changes: Changes): PlanMap {
  const out: PlanMap = new Map(base)
  for (const m of changes.moved ?? []) {
    out.set(Number(m.item_id), { title: String(m.title), spans: (m.after as Spans).map(([a, b]) => [a, b]) })
  }
  const added = planMap(changes.added ?? [])
  for (const [id, entry] of added) out.set(id, entry)
  for (const b of changes.removed ?? []) out.delete(b.item_id)
  return out
}

export interface Move {
  itemId: number
  title: string
  before: Spans
  after: Spans
}

/** Items placed differently in `b` than in `a`. */
export function diffPlans(a: PlanMap, b: PlanMap): Move[] {
  const ids = [...new Set([...a.keys(), ...b.keys()])].sort((x, y) => x - y)
  const out: Move[] = []
  for (const id of ids) {
    const before = a.get(id)?.spans ?? []
    const after = b.get(id)?.spans ?? []
    if (key(before) !== key(after)) out.push({ itemId: id, title: (b.get(id) ?? a.get(id))?.title ?? "", before, after })
  }
  return out
}

const key = (spans: Spans) => JSON.stringify([...spans].sort())

/** A plan's shape in a few numbers people care about, all in hours. */
export interface Shape {
  total: number
  lateNight: number // after 22:00 (or before 05:00)
  evenings: number // 18:00–22:00 on weekdays
  weekends: number
  heaviestDay: number
  longestSitting: number // back-to-back work, any items
  sittings: number
}

/** `dayStart`: minutes after midnight the planning day starts (your settings'), so 01:00 work belongs to the evening
 * before. */
export function shapeOf(plan: PlanMap, dayStart = dayStartMin()): Shape {
  const spans = [...plan.values()].flatMap((e) => e.spans).map(([a, b]) => [toMin(a), toMin(b)] as const)
  spans.sort((x, y) => x[0] - y[0])
  const byDay = new Map<number, number>()
  const shape: Shape = { total: 0, lateNight: 0, evenings: 0, weekends: 0, heaviestDay: 0, longestSitting: 0, sittings: 0 }
  for (let [s, e] of spans) {
    for (; s < e; s += 15) {
      const clock = ((s % 1440) + 1440) % 1440
      const day = Math.floor((s - dayStart) / 1440)
      const weekday = new Date(day * 86400000).getUTCDay()
      const weekend = weekday === 0 || weekday === 6
      shape.total += 0.25
      if (clock >= 22 * 60 || clock < 5 * 60) shape.lateNight += 0.25
      else if (clock >= 18 * 60 && !weekend) shape.evenings += 0.25
      if (weekend) shape.weekends += 0.25
      byDay.set(day, (byDay.get(day) ?? 0) + 0.25)
    }
  }
  shape.heaviestDay = Math.max(0, ...byDay.values())
  let runStart = -1
  let runEnd = -1
  for (const [s, e] of spans) {
    if (s > runEnd) {
      shape.sittings += 1
      runStart = s
    }
    runEnd = Math.max(runEnd, e)
    shape.longestSitting = Math.max(shape.longestSitting, (runEnd - runStart) / 60)
  }
  return shape
}

const SHAPE_WORDS: [keyof Shape, string][] = [
  ["lateNight", "late-night work (after 22:00)"],
  ["evenings", "weekday-evening work"],
  ["weekends", "weekend work"],
  ["heaviestDay", "heaviest day"],
  ["longestSitting", "longest sitting"],
  ["sittings", "separate sittings"],
]

/** "3.5 h more late-night work", one line per number that changed. */
export function shapeChanges(before: Shape, after: Shape): string[] {
  const out: string[] = []
  for (const [k, words] of SHAPE_WORDS) {
    const d = after[k] - before[k]
    if (Math.abs(d) < 0.25) continue
    const amount = k === "sittings" ? `${Math.abs(d)}` : `${fmtH(Math.abs(d))}`
    if (k === "heaviestDay" || k === "longestSitting") out.push(`${words} ${fmtH(before[k])} → ${fmtH(after[k])}`)
    else out.push(`${amount} ${d > 0 ? "more" : "less"} ${words}`)
  }
  return out
}

export const fmtH = (h: number) => `${Number(h.toFixed(2))} h`

/** Late hours by title, summed: the one number that outranks everything else. */
export const lateTotal = (late: Record<string, number> | undefined) =>
  Object.values(late ?? {}).reduce((a, b) => a + b, 0)

// Dials: a handful of human controls, each writing a few named rules. Positions are indexes into `stops`.

export interface Stop {
  label: string
  set: Record<string, { weight?: number; params?: Record<string, unknown> }>
}

export interface Dial {
  id: string
  title: string
  low: string
  high: string
  stops: Stop[]
}

export const DIALS: Dial[] = [
  {
    id: "sleep",
    title: "Protect sleep",
    low: "Work late if it helps",
    high: "Guard my nights",
    stops: [
      { label: "Loose", set: { late_night: { weight: 0.4, params: { gradient_start: "23:30" } } } },
      { label: "Normal", set: { late_night: { weight: 1, params: { gradient_start: "22:00" } } } },
      { label: "Strict", set: { late_night: { weight: 3, params: { gradient_start: "21:00" } } } },
    ],
  },
  {
    id: "early",
    title: "When to start",
    low: "Close to the deadline",
    high: "Well ahead",
    stops: [
      { label: "Last minute", set: { finish_early: { weight: 0, params: { days: 1 } } } },
      { label: "A day early", set: { finish_early: { weight: 1, params: { days: 1 } } } },
      { label: "Days early", set: { finish_early: { weight: 2, params: { days: 3 } } } },
    ],
  },
  {
    id: "sittings",
    title: "Sitting length",
    low: "Short bursts",
    high: "Long focus",
    stops: [
      { label: "Short", set: { deep_run: { params: { threshold: "1.5h" } }, chunk_cost: { weight: 3 } } },
      { label: "Medium", set: { deep_run: { params: { threshold: "3h" } }, chunk_cost: { weight: 10 } } },
      { label: "Long", set: { deep_run: { params: { threshold: "4h" } }, chunk_cost: { weight: 30 } } },
    ],
  },
  {
    id: "free",
    title: "Free evenings and weekends",
    low: "Use them",
    high: "Keep them free",
    stops: [
      { label: "Use them", set: { weekday_evenings: { weight: 1, params: { free: "1h" } }, weekends: { weight: 1, params: { free: "2h" } } } },
      { label: "Some", set: { weekday_evenings: { weight: 2, params: { free: "2h" } }, weekends: { weight: 2, params: { free: "4h" } } } },
      { label: "Keep free", set: { weekday_evenings: { weight: 5, params: { free: "3h" } }, weekends: { weight: 5, params: { free: "8h" } } } },
    ],
  },
  {
    id: "spread",
    title: "Spread or batch",
    low: "Batch into big days",
    high: "Even, lighter days",
    stops: [
      { label: "Batch", set: { even_load: { weight: 0 }, daily_load: { params: { threshold: "10h" } } } },
      { label: "Balanced", set: { even_load: { weight: 1 }, daily_load: { params: { threshold: "8h" } } } },
      { label: "Even", set: { even_load: { weight: 4 }, daily_load: { params: { threshold: "6h" } } } },
    ],
  },
]

/** The rules with each dial's stop written over them; rules a stop names that you don't have are left alone. */
export function applyDials(rules: RuleSpec[], positions: Record<string, number>): RuleSpec[] {
  let out = rules
  for (const dial of DIALS) {
    const stop = dial.stops[positions[dial.id] ?? -1]
    if (stop) out = applySet(out, stop.set)
  }
  return out
}

export function applySet(rules: RuleSpec[], set: Stop["set"]): RuleSpec[] {
  return rules.map((r) => {
    const change = set[r.name]
    if (!change) return r
    return { ...r, weight: change.weight ?? r.weight, params: { ...r.params, ...change.params } }
  })
}

/** Which stop each dial is at now, or -1 when your rules match none of them (set by hand). */
export function readDials(rules: RuleSpec[]): Record<string, number> {
  return Object.fromEntries(DIALS.map((d) => [d.id, d.stops.findIndex((s) => matches(rules, s.set))]))
}

function matches(rules: RuleSpec[], set: Stop["set"]): boolean {
  return Object.entries(set).every(([name, change]) => {
    const r = rules.find((x) => x.name === name)
    if (!r) return true
    const weightOk = change.weight === undefined || Math.abs(r.weight - change.weight) < 1e-9
    return weightOk && Object.entries(change.params ?? {}).every(([k, v]) => JSON.stringify(r.params[k]) === JSON.stringify(v))
  })
}

// Ranking: the order of what matters becomes stages and weights. Above the line is wellbeing (never traded for
// anything below it); below is preferences. Each place a concern moves up doubles its weight; down halves it.

// The engine's default stage per type (DESIGN §12.2), for rules whose settings leave `stage` empty.
export const DEFAULT_STAGE: Record<string, string> = {
  late_work: "deadlines",
  quota: "deadlines",
  late_night: "wellbeing",
  deep_run: "wellbeing",
  reserve: "wellbeing",
  daily_load: "wellbeing",
  even_load: "wellbeing",
  buffer: "wellbeing",
}

export const stageOf = (r: RuleSpec) => r.stage ?? DEFAULT_STAGE[r.type] ?? "preferences"

export interface Concern {
  id: string
  title: string
  rules: string[]
}

/** `start` and `order` list concern ids, best first; the first `line` of `order` are protected. */
export function rankRules(rules: RuleSpec[], start: string[], order: string[], line: number, concerns: Concern[]): RuleSpec[] {
  const update = new Map<string, { stage: string; factor: number }>()
  order.forEach((id, i) => {
    const change = { stage: i < line ? "wellbeing" : "preferences", factor: 2 ** (start.indexOf(id) - i) }
    for (const name of concerns.find((c) => c.id === id)?.rules ?? []) update.set(name, change)
  })
  return rules.map((r) => {
    const u = update.get(r.name)
    if (!u) return r
    return { ...r, stage: u.stage === stageOf(r) ? r.stage : u.stage, weight: Math.round(r.weight * u.factor * 1000) / 1000 }
  })
}

