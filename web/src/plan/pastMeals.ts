// The meals you ate, on the calendar as your Lunch and Dinner are, only in the past (4 Nov: "treat them as if they
// were regular lunch and dinner but just in the past"): each meal Sleep & meals recorded is a done block at the time
// you ate it, and the pieces the plan had for that day's routine give way to it. A meal you're eating runs to now.
// Skipped meals draw nothing; the routine they skipped is gone from the plan already.

import type { Block, Schemas } from "@/api/client"
import { fromMin, toMin } from "@/lib/time"

export interface PastMeal {
  block: Block
  eating: boolean
}

const named = (kind: string) => kind[0].toUpperCase() + kind.slice(1)

/** Every meal eaten (and the one you're eating), as blocks that look like the routine they ticked off. */
export function pastMeals(meals: Schemas["MealsOut"] | undefined, plan: { blocks: Block[]; sessions?: Block[] | null }, now: number): PastMeal[] {
  if (!meals?.on) return []
  const routineOf = new Map([...plan.blocks, ...(plan.sessions ?? [])].map((b) => [b.item_id, b]))
  const out: PastMeal[] = []
  const seen = new Set<number>()
  const eaten = (meals.days ?? []).flatMap((d) => d.meals ?? [])
  if (meals.eating) eaten.push(meals.eating)
  for (const m of eaten) {
    if (m.skipped || !m.start || seen.has(m.id)) continue
    seen.add(m.id)
    const end = m.end ?? fromMin(now)
    if (toMin(end) <= toMin(m.start)) continue
    const routine = m.item_id != null ? routineOf.get(m.item_id) : undefined
    out.push({
      eating: !m.end,
      block: {
        key: `M${m.id}`,
        item_id: m.item_id ?? -m.id,
        title: routine?.title ?? named(m.kind),
        area: routine?.area ?? null,
        preset: routine?.preset ?? "Routine",
        start: m.start,
        end,
        state: m.end ? "done" : null,
      },
    })
  }
  return out
}

/** The routines a recorded meal stands for: their planned pieces and held time give way to the meal. */
export function eatenRoutines(meals: PastMeal[]): Set<number> {
  return new Set(meals.map((m) => m.block.item_id).filter((id) => id > 0))
}
