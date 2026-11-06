// More than one of a meal in a day (5 Nov: "sometimes i have 4 meals (2 dinners)"): the second is "Second dinner"
// wherever a meal is named, and a day that has its dinner still offers another.

import type { Schemas } from "@/api/client"

const ORDINALS = ["", "Second", "Third", "Fourth", "Fifth"]
const PLANNED = ["breakfast", "lunch", "dinner"] as const
type Planned = (typeof PLANNED)[number]

/** "Dinner", "Second dinner", "Third dinner"; past the fifth, "Dinner 6". A snack is always "Snack". */
export function mealLabel(kind: string, nth = 1): string {
  const named = kind[0].toUpperCase() + kind.slice(1)
  if (nth <= 1 || kind === "snack") return named
  return nth <= ORDINALS.length ? `${ORDINALS[nth - 1]} ${kind}` : `${named} ${nth}`
}

/** A day's "+" choices: the meals not recorded (to log or say skipped), and the ones eaten already, to log another. */
export function addable(meals: Schemas["MealOut"][]): { missing: Planned[]; another: { kind: Planned; nth: number }[] } {
  const eaten = (kind: string) => meals.filter((m) => m.kind === kind && !m.skipped).length
  return {
    missing: PLANNED.filter((k) => !meals.some((m) => m.kind === k)),
    another: PLANNED.filter((k) => eaten(k) > 0).map((kind) => ({ kind, nth: eaten(kind) + 1 })),
  }
}
