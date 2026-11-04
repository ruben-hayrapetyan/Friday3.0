// What you did, from what you tapped (Sleep & meals): asleep, the morning routine from up to ready, naps and meals,
// as spans the calendar draws as a faint rail down each column's edge (4 Nov: "very lowk… shouldn't take the
// user's attention"). Only what was recorded: a plan's guess is the sleep band, not this.

import type { Schemas } from "@/api/client"
import { clock, dur } from "@/lib/format"
import { fromMin, toMin } from "@/lib/time"

export type LivedKind = "sleep" | "routine" | "meal"

export interface Lived {
  kind: LivedKind
  start: string // local
  end: string
  label: string // the tooltip: what and when
}

const span = (kind: LivedKind, what: string, start: string, end: string, open = false): Lived | null =>
  toMin(end) > toMin(start) ? { kind, start, end, label: `${what} ${clock(start)}–${open ? "now" : clock(end)} · ${dur(toMin(end) - toMin(start))}` } : null

/** Each night's sleep (bed to up) and routine (up to ready), and each nap; a nap still going runs to `now`. */
export function sleepSpans(sleep: Schemas["SleepOut"] | undefined, now: number): Lived[] {
  if (!sleep?.on) return []
  const out: (Lived | null)[] = []
  for (const n of sleep.nights ?? []) {
    if (n.bed && n.up) out.push(span("sleep", "Asleep", n.bed, n.up))
    if (n.up && n.ready) out.push(span("routine", "Morning routine", n.up, n.ready))
  }
  for (const nap of sleep.naps ?? []) out.push(span("sleep", "Nap", nap.start, nap.end ?? fromMin(now), !nap.end))
  if (sleep.napping && !(sleep.naps ?? []).some((n) => n.id === sleep.napping?.id)) out.push(span("sleep", "Nap", sleep.napping.start, fromMin(now), true))
  return out.filter((l): l is Lived => l !== null)
}

/** Each meal eaten (not skipped), and the one you're eating now up to `now`. */
export function mealSpans(meals: Schemas["MealsOut"] | undefined, now: number): Lived[] {
  if (!meals?.on) return []
  const name = (kind: string) => kind[0].toUpperCase() + kind.slice(1)
  const out: (Lived | null)[] = []
  const seen = new Set<number>()
  for (const day of meals.days ?? [])
    for (const m of day.meals ?? []) {
      if (m.skipped || !m.start) continue
      seen.add(m.id)
      out.push(span("meal", name(m.kind), m.start, m.end ?? fromMin(now), !m.end))
    }
  const eating = meals.eating
  if (eating?.start && !seen.has(eating.id)) out.push(span("meal", name(eating.kind), eating.start, fromMin(now), true))
  return out.filter((l): l is Lived => l !== null)
}
