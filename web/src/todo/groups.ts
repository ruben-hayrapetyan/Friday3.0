// How the to-do list is grouped and sorted (v22 To-do): by kind (personal's notebook: readings, assignments, the rest,
// each with its own add line), by when it happens or by tag; next up, due, length or title. Progress reads as "2h of
// 6h".

import type { Block, Item } from "@/api/client"
import { dur } from "@/lib/format"
import { nextBlocks, nextOccurrences, SECTIONS, sectionOf } from "@/lib/todo"
import { toMin } from "@/lib/time"

export type GroupBy = "When" | "Tag" | "Kind"
export type SortBy = "Next up" | "Due date" | "Length" | "Title"
export const GROUPS: GroupBy[] = ["Kind", "When", "Tag"]
// personal's buckets first, in its order (readings, assignments, emails), then any other kind, then the rest.
export const KINDS_FIRST = ["Reading", "Assignment", "Exam prep", "Errand"]
export const OTHER = "Other"
export const SORTS: SortBy[] = ["Next up", "Due date", "Length", "Title"]

export interface Group {
  name: string
  items: Item[]
}

/** The groups in order; `always` are shown even when empty, so each has its add line (personal's buckets). `all` is
 * every open item, so a project in the list goes where its steps are planned though they're in another list. */
export function grouped(items: Item[], blocks: Block[], today: string, by: GroupBy, sort: SortBy, always: string[] = [], all: Item[] = items): Group[] {
  const next = nextBlocks(blocks, all)
  const key = (i: Item): string => {
    if (i.status === "done") return "Done"
    if (by === "Tag") return i.area ?? "No tag"
    if (by === "Kind") return i.preset ?? OTHER
    return sectionOf(i, next.get(i.id), today)
  }
  const groups = new Map<string, Item[]>()
  // A repeating item shows once, as its next occurrence.
  for (const { item: i } of nextOccurrences(items, next)) groups.set(key(i), [...(groups.get(key(i)) ?? []), i])
  const names = [...new Set([...groups.keys(), ...always])]
  const rank = (name: string) => (name === "Done" ? 3 : name === OTHER || name === "No tag" ? 2 : by === "Kind" && KINDS_FIRST.includes(name) ? 0 : 1)
  const order =
    by === "When"
      ? [...SECTIONS, "Done"]
      : names.sort((a, b) => rank(a) - rank(b) || (by === "Kind" ? KINDS_FIRST.indexOf(a) - KINDS_FIRST.indexOf(b) : 0) || a.localeCompare(b))
  return order
    .filter((name) => groups.has(name) || always.includes(name))
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

/** What a group's add line fills in: its kind or its tag. Null where a group isn't something you add to (When). */
export function fillFor(by: GroupBy, name: string): { preset?: string; area?: string } | null {
  if (name === "Done" || by === "When") return null
  if (by === "Kind") return name === OTHER ? {} : { preset: name }
  return name === "No tag" ? {} : { area: name }
}

/** "Add a reading…", "Add an assignment…", "Add to psych…", "Add anything else…" */
export function addHint(by: GroupBy, name: string): string {
  if (name === OTHER || name === "No tag") return "Add anything else…"
  if (by === "Tag") return `Add to ${name}…`
  const kind = name.toLowerCase()
  if (/prep$/.test(kind)) return `Add ${kind}…`
  return `Add ${/^[aeiou]/.test(kind) ? "an" : "a"} ${kind}…`
}

/** A kind as a section's name: "Readings", "Assignments", "Exam prep", "Other". */
export function plural(kind: string): string {
  return kind === OTHER || /(prep|s|work)$/i.test(kind) ? kind : `${kind}s`
}
