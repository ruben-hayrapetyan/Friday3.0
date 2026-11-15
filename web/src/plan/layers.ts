// Which layer of a day column each event is drawn in (2 Nov: "have the skipped events (the ones that are grayed
// out) be not so in poppy... i basically can't see the stuff behind them"): drawn in this order, later on top.
import type { Item } from "@/api/client"
import { type Axis, columnSpan, layout, type Placed, type Span, toMin } from "@/lib/time"

type Event = Pick<Item, "gives_way_to" | "left_out">

export type Layers<T> = {
  notGoing: T[] // you said you're not going: first, behind the work planned over it, faint
  going: T[] // events that hold their time: beside each other, under work
  proposed: T[] // Friday's "Skip?" for work that needs the time: in view, at the side, yours to decide
}

export function layers<T extends Event>(events: T[]): Layers<T> {
  const proposed = events.filter((e) => !!e.gives_way_to)
  const notGoing = events.filter((e) => !e.gives_way_to && e.left_out === "skipped")
  const going = events.filter((e) => !proposed.includes(e) && !notGoing.includes(e))
  return { notGoing, going, proposed }
}

/** Whether an event is drawn dashed and the plan may put work over it: it doesn't hold its time (a "Just show it"
 * calendar's, one marked free, one you're working through). Not one you said you're not going to, which sits behind,
 * nor one holding a task's time, whose blocks are drawn inside it (planner/holds.py). */
export function givesTimeToWork(e: Pick<Item, "left_out" | "holds" | "gives_way_to">): boolean {
  return !!e.left_out && e.left_out !== "skipped" && !e.holds && !e.gives_way_to
}

/** A day column's events and blocks, each placed. An event that lets work over it is laid out with the work, side by
 * side as two overlapping events are (15 Nov: a client's dashed event was drawn under the task planned over it), with
 * the events it overlaps; the rest of the events are laid out among themselves, under the work, as before. */
export function sideBySide<E extends Span, B extends Span>(
  events: E[],
  blocks: B[],
  date: string,
  axis: Axis,
  withWork: (e: E) => boolean,
): { events: Placed<E>[]; blocks: Placed<B>[] } {
  const [lo, hi] = columnSpan(date, axis)
  const inside = events
    .map((e) => ({ e, s: Math.max(toMin(e.start), lo), t: Math.min(toMin(e.end), hi) }))
    .filter((p) => p.t > p.s)
    .sort((a, b) => a.s - b.s || b.t - a.t)
  // Events that overlap, one after another, stay together: one beside the work takes the others with it, so two
  // events at one time are never drawn one over the other.
  const pulled = new Set<E>()
  let cluster: E[] = []
  let end = -Infinity
  const flush = () => {
    if (cluster.some(withWork)) for (const e of cluster) pulled.add(e)
    cluster = []
  }
  for (const p of inside) {
    if (p.s >= end) flush()
    cluster.push(p.e)
    end = Math.max(end, p.t)
  }
  flush()
  type Either = Span & ({ event: E; block?: undefined } | { block: B; event?: undefined })
  const together: Either[] = [
    ...events.filter((e) => pulled.has(e)).map((event) => ({ start: event.start, end: event.end, event })),
    ...blocks.map((block) => ({ start: block.start, end: block.end, block })),
  ]
  const placed = layout(together, date, axis)
  const apart = layout(
    events.filter((e) => !pulled.has(e)),
    date,
    axis,
  )
  return {
    events: [...apart, ...placed.flatMap((p) => (p.item.event ? [{ ...p, item: p.item.event }] : []))],
    blocks: placed.flatMap((p) => (p.item.block ? [{ ...p, item: p.item.block }] : [])),
  }
}
