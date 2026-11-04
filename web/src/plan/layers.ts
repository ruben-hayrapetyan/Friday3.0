// Which layer of a day column each event is drawn in (2 Nov: "have the skipped events (the ones that are greyed
// out) be not so in poppy... i basically can't see the stuff behind them"): drawn in this order, later on top.
import type { Item } from "@/api/client"

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
