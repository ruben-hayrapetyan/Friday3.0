// What's going on at once, for Minimal's pill (21 Nov, the user: timing CATC, then lunch, then math, "i would like
// the two or more timers to be next to each other"; the pill had shown one, a meal as a small mark and the rest as
// "+1"). Each timer, alongside ones included, and the meal you're eating: oldest first, the timer the pill's buttons
// act on marked `main`.
import type { Schemas } from "@/api/client"
import { mealLabel } from "@/body/mealNames"

export type Running = {
  key: string
  title: string
  started: string | null // local, to the minute
  elapsed_s: number | null // a timer's seconds so far; a meal's are counted from `started`
  kind: "timer" | "meal"
  meal?: string // the meal's kind, for its icon
  main?: boolean
}

export function runningNow(status: Schemas["StatusOut"] | undefined, meals: Schemas["MealsOut"] | undefined): Running[] {
  const timers = [...(status?.alongside ?? []), ...(status?.timer ? [status.timer] : [])]
  const out: Running[] = timers
    .filter((t) => t.item_id != null)
    .map((t) => ({ key: `t${t.item_id}`, title: t.title ?? "", started: t.started ?? null, elapsed_s: t.elapsed_s ?? 0, kind: "timer", main: t === status?.timer }))
  const eating = meals?.on ? meals.eating : null
  if (eating) out.push({ key: `m${eating.id}`, title: mealLabel(eating.kind, eating.nth), started: eating.start ?? null, elapsed_s: null, kind: "meal", meal: eating.kind })
  // oldest first; the same minute keeps the order above (alongside, then the timer, then the meal)
  return out.map((r, i) => [r, i] as const).sort(([a, i], [b, j]) => (a.started ?? "").localeCompare(b.started ?? "") || i - j).map(([r]) => r)
}
