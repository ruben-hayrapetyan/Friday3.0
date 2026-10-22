// The to-do pane's sections (DESIGN §18.5). An item goes where its next planned block is, or its due when nothing
// is planned; items with neither are Someday.

import type { Block, Item } from "@/api/client"
import { addDays, toMin } from "./time"

export const SECTIONS = ["Today", "This week", "Later", "Someday", "Ongoing", "Waiting on"] as const
export type Section = (typeof SECTIONS)[number]

export function nextBlocks(blocks: Block[]): Map<number, Block> {
  const out = new Map<number, Block>()
  for (const b of [...blocks].sort((x, y) => x.start.localeCompare(y.start))) {
    if (!out.has(b.item_id)) out.set(b.item_id, b)
  }
  return out
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
  const next = nextBlocks(blocks)
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
