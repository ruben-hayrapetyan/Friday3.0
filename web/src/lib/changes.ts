// A full preview's change list, read for people: one summary line and a line per changed item.

import type { Schemas } from "@/api/client"
import { when } from "./format"

type Changes = Schemas["ChangeOut"]

export function summary(changes: Changes): string {
  const all = [...(changes.added ?? []), ...(changes.removed ?? []), ...(changes.moved ?? [])]
  const ids = new Set(all.map((c) => Number(c.item_id)))
  const late = Object.entries(changes.late_hours ?? {})
  const parts = [
    ids.size ? `${ids.size} ${ids.size === 1 ? "item" : "items"} change` : "Nothing moves",
    late.length ? late.map(([title, h]) => `${title} ${h} h late`).join(", ") : "all deadlines met",
  ]
  return parts.join(" · ")
}

interface Line {
  title: string
  text: string
}

/** Each item once: where its first block goes, or that it joins or leaves the plan. */
export function lines(changes: Changes, today: string): Line[] {
  const out = new Map<number, Line>()
  for (const m of changes.moved ?? []) {
    const [before, after] = [m.before as string[][], m.after as string[][]]
    const text = after.length ? `${when(before[0][0], today)} → ${when(after[0][0], today)}` : "off the plan"
    out.set(Number(m.item_id), { title: String(m.title), text })
  }
  for (const b of changes.added ?? []) {
    if (!out.has(b.item_id)) out.set(b.item_id, { title: b.title, text: `new at ${when(b.start, today)}` })
  }
  for (const b of changes.removed ?? []) {
    if (!out.has(b.item_id)) out.set(b.item_id, { title: b.title, text: "off the plan" })
  }
  return [...out.values()]
}
