// Everything being timed, drawn live on the calendar side by side (15 Nov, a client: "timing two tasks at once but only
// one is getting recorded in the calendar as im doing it"; you chose both, side by side): the main timer, when the
// calendar draws it from the timer, and each one timed alongside it, each in its share of the column.

export type Timed = { key: string; title: string; seconds: number }
export type Lane = Timed & { lane: number; lanes: number }

/** The timers to draw, in lanes: `main` (null when the plan's block already shows it) first, then those alongside.
 * `drift` is how many seconds have passed since the server said how long each had run. */
export function timerLanes(main: Timed | null, alongside: { item_id: number | null; title?: string | null; elapsed_s?: number }[], drift: number): Lane[] {
  const all: Timed[] = [...(main ? [main] : []), ...alongside.map((a) => ({ key: `along-${a.item_id}`, title: a.title ?? "", seconds: (a.elapsed_s ?? 0) + drift }))]
  return all.map((t, lane) => ({ ...t, lane, lanes: all.length }))
}

/** A lane's place across its column. */
export function laneBox(lane: number, lanes: number): { left: string; width: string } {
  return { left: `calc(${(lane * 100) / lanes}% + 3px)`, width: `calc(${100 / lanes}% - 6px)` }
}
