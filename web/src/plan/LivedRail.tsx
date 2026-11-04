// The rail of what you did (plan/lived.ts, the spans): a 3px line in the gap at a column's left edge, where no block
// reaches, over a soft wash of the same paint across the column, behind everything (4 Nov: the 2px line alone was
// "too faint"). Hover the line for what and when; the wash lets clicks and drags through to the empty time.

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

const PAINT: Record<LivedKind, string | null> = { sleep: null, routine: "graphite", meal: "yellow" } // null: the ink

function paintOf(kind: LivedKind, light: boolean): string {
  const id = PAINT[kind]
  return id ? (pigment(id, light) as string) : "var(--color-accent)"
}

/** Each kind's line: sleep in the ink, the routine in Payne's Grey, meals in their Ochre. */
export function railTone(kind: LivedKind, light: boolean): string {
  return `color-mix(in srgb, ${paintOf(kind, light)} ${kind === "meal" ? 90 : 70}%, transparent)`
}

/** The same paint, thin enough to sit under events and work: a little more on the dark page, where it vanishes. */
export function washTone(kind: LivedKind, light: boolean): string {
  const share = (kind === "meal" ? 13 : kind === "routine" ? 10 : 8) + (light ? 0 : 4)
  return `color-mix(in srgb, ${paintOf(kind, light)} ${share}%, transparent)`
}

export function LivedRail({ lived, date, axis, light }: { lived: Lived[]; date: string; axis: Axis; light: boolean }) {
  return (
    <>
      {layout(lived, date, axis).map((p) => {
        const box = { position: "absolute", top: p.top * PX, height: Math.max(p.height * PX, 2) } as const
        const key = `${p.item.kind}${p.item.start}`
        return [
          <div key={`w${key}`} data-lived-wash={p.item.kind} style={{ ...box, left: 0, right: 0, pointerEvents: "none", background: washTone(p.item.kind, light) }} />,
          // The hit area is wider than the line so a hover finds it; drawn under the blocks, which win where they meet.
          <div key={`l${key}`} data-lived={p.item.kind} title={p.item.label} aria-label={p.item.label} style={{ ...box, left: 0, width: 6 }}>
            <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 3, borderRadius: 1.5, background: railTone(p.item.kind, light) }} />
          </div>,
        ]
      })}
    </>
  )
}
