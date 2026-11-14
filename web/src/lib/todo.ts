// The to-do pane's sections (DESIGN §18.5). An item goes where its next planned block is, or its due when nothing
// is planned; items with neither are Someday.

import type { Block, Item } from "@/api/client"
import { addDays, toMin } from "./time"

export const SECTIONS = ["Today", "This week", "Later", "Someday", "Ongoing", "Waiting on"] as const
export type Section = (typeof SECTIONS)[number]

/** Each item's next block. With `items`, a project's is the soonest of its steps': the planner plans the steps, never
 * the project, so it had no block of its own and its row read "not planned" while its steps were (13 Nov). */
export function nextBlocks(blocks: Block[], items: Item[] = []): Map<number, Block> {
  const parent = new Map(items.map((i) => [i.id, i.parent_id ?? null]))
  const out = new Map<number, Block>()
  for (const b of [...blocks].sort((x, y) => x.start.localeCompare(y.start))) {
    // the block's own item, then each project it's a step of (a loop can't be saved; `seen` guards all the same)
    for (let at: number | null = b.item_id, seen = 0; at != null && seen < 32; at = parent.get(at) ?? null, seen++) {
      if (!out.has(at)) out.set(at, b)
    }
  }
  return out
}

/** The project an item is a step of, when it's one of `items`. */
export function projectOf(item: Pick<Item, "parent_id">, items: Item[]): Item | undefined {
  return item.parent_id == null ? undefined : items.find((i) => i.id === item.parent_id)
}

export function sectionOf(item: Item, next: Block | undefined, today: string): Section {
  if (item.waiting_on?.length) return "Waiting on"
  if (item.amount === "open") return "Ongoing"
  const day = next?.start.slice(0, 10) ?? item.due?.slice(0, 10)
  if (!day) return "Someday"
  if (day <= today) return "Today"
  return day < addDays(today, 7) ? "This week" : "Later"
}

/** A repeating item shows only its next occurrence, with how many more are open. */
export function nextOccurrences(items: Item[], next: Map<number, Block>): { item: Item; more: number }[] {
  const key = (i: Item) => next.get(i.id)?.start ?? i.release ?? i.due ?? ""
  const bySeries = new Map<number, Item[]>()
  const out: { item: Item; more: number }[] = []
  for (const item of items) {
    if (item.series_id == null) out.push({ item, more: 0 })
    else bySeries.set(item.series_id, [...(bySeries.get(item.series_id) ?? []), item])
  }
  for (const all of bySeries.values()) {
    const first = all.reduce((a, b) => (key(b) < key(a) ? b : a))
    out.push({ item: first, more: all.length - 1 })
  }
  return out
}

export type Row = { item: Item; more: number }

export function sections(items: Item[], blocks: Block[], today: string): Record<Section, Row[]> {
  const next = nextBlocks(blocks, items)
  const out = Object.fromEntries(SECTIONS.map((s) => [s, [] as Row[]])) as Record<Section, Row[]>
  for (const row of nextOccurrences(items, next)) out[sectionOf(row.item, next.get(row.item.id), today)].push(row)
  for (const rows of Object.values(out)) rows.sort((a, b) => order(a.item, next) - order(b.item, next) || a.item.id - b.item.id)
  return out
}

// Within a section: by next block, then due, then id, so the list reads in the order work happens.
function order(item: Item, next: Map<number, Block>): number {
  const at = next.get(item.id)?.start ?? item.due
  return at ? toMin(at) : Number.POSITIVE_INFINITY
}
