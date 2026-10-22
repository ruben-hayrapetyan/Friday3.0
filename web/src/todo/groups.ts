// How the to-do list is grouped and sorted (v22 To-do): by when it happens, by tag or by kind; next up, due, length
// or title. Progress reads as "2h of 6h".

import type { Block, Item } from "@/api/client"
import { dur } from "@/lib/format"
import { nextBlocks, nextOccurrences, SECTIONS, sectionOf } from "@/lib/todo"
import { toMin } from "@/lib/time"

export type GroupBy = "When" | "Tag" | "Kind"
export type SortBy = "Next up" | "Due date" | "Length" | "Title"
export const GROUPS: GroupBy[] = ["When", "Tag", "Kind"]
export const SORTS: SortBy[] = ["Next up", "Due date", "Length", "Title"]

export interface Group {
  name: string
  items: Item[]
}

export function grouped(items: Item[], blocks: Block[], today: string, by: GroupBy, sort: SortBy): Group[] {
  const next = nextBlocks(blocks)
  const key = (i: Item): string => {
    if (i.status === "done") return "Done"
    if (by === "Tag") return i.area ?? "No tag"
    if (by === "Kind") return i.preset ?? "No kind"
    return sectionOf(i, next.get(i.id), today)
  }
  const groups = new Map<string, Item[]>()
  // A repeating item shows once, as its next occurrence.
  for (const { item: i } of nextOccurrences(items, next)) groups.set(key(i), [...(groups.get(key(i)) ?? []), i])
  const order = by === "When" ? [...SECTIONS, "Done"] : [...groups.keys()].sort((a, b) => Number(a === "Done") - Number(b === "Done") || a.localeCompare(b))
  return order
    .filter((name) => groups.has(name))
    .map((name) => ({ name, items: [...(groups.get(name) ?? [])].sort(sorter(sort, next)) }))
}

function sorter(sort: SortBy, next: Map<number, Block>): (a: Item, b: Item) => number {
  const at = (i: Item) => {
    const when = next.get(i.id)?.start ?? i.due
    return when ? toMin(when) : Number.POSITIVE_INFINITY
  }
  const due = (i: Item) => (i.due ? toMin(i.due) : Number.POSITIVE_INFINITY)
  const left = (i: Item) => i.remaining_min ?? i.duration_min ?? 0
  return (a, b) => {
    if (sort === "Title") return a.title.localeCompare(b.title)
    if (sort === "Length") return left(b) - left(a) || a.id - b.id
    if (sort === "Due date") return due(a) - due(b) || a.id - b.id
    return at(a) - at(b) || a.id - b.id
  }
}

export function progress(item: Item): { pct: number; text: string } {
  if (item.amount === "open") return { pct: 0, text: "Fills free time" }
  const done = item.done_min
  const total = done + (item.remaining_min ?? 0)
  if (!total) return { pct: 0, text: "No length yet" }
  if (!done) return { pct: 0, text: `${dur(total)} to do` }
  return { pct: Math.round((done / total) * 100), text: `${dur(done)} of ${dur(total)}` }
}

export function summary(items: Item[]): string {
  const open = items.filter((i) => i.status === "todo")
  const left = open.reduce((s, i) => s + (i.remaining_min ?? 0), 0)
  return `${open.length} open, ${dur(left)} left`
}
