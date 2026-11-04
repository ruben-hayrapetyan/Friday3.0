// The rail of what you did (plan/lived.ts, the spans): a 2px line in the gap at a column's left edge, where no block reaches,
// faint enough to read only when you look for it; hover for what and when.

import { useMeals, useSleep } from "@/hooks/queries"
import { pigment } from "@/lib/pigments"
import { type Axis, layout } from "@/lib/time"
import { type Lived, type LivedKind, mealSpans, sleepSpans } from "./lived"
import { PX } from "./Pieces"

/** Everything recorded, once for the grid; each column takes its own part with `LivedRail`. */
export function useLived(now: number): Lived[] {
  const sleep = useSleep().data
  const meals = useMeals().data
  return [...sleepSpans(sleep, now), ...mealSpans(meals, now)]
}

/** Each kind's line: sleep in the ink, the routine in Payne's Grey, meals in their Ochre, all thinned. */
export function railTone(kind: LivedKind, light: boolean): string {
  if (kind === "sleep") return "color-mix(in srgb, var(--color-accent) 30%, transparent)"
  return `color-mix(in srgb, ${pigment(kind === "meal" ? "yellow" : "graphite", light)} ${kind === "meal" ? 60 : 40}%, transparent)`
}

export function LivedRail({ lived, date, axis, light }: { lived: Lived[]; date: string; axis: Axis; light: boolean }) {
  return (
    <>
      {layout(lived, date, axis).map((p) => (
        // The hit area is wider than the line so a hover finds it; drawn under the blocks, which win where they meet.
        <div
          key={`l${p.item.kind}${p.item.start}`}
          data-lived={p.item.kind}
          title={p.item.label}
          aria-label={p.item.label}
          style={{ position: "absolute", left: 0, width: 5, top: p.top * PX, height: Math.max(p.height * PX, 2) }}
        >
          <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 2, borderRadius: 1, background: railTone(p.item.kind, light) }} />
        </div>
      ))}
    </>
  )
}
