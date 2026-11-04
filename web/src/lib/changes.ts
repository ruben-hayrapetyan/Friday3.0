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

// What you did, in words, for "What changed" (3 Nov: `changes` had no screen). A command not named here is "used"
// by its own name.
const DID: Record<string, string> = {
  add: "added something", edit: "changed something", drop: "deleted something", done: "finished something",
  reopen: "opened something again", start: "started a timer", stop: "stopped a timer", log: "logged time",
  progress: "set how much is done", pin: "pinned a block", unpin: "unpinned a block", shove: "cleared some time",
  unshove: "gave time back", pace: "changed the pace", settings_set: "changed a setting", rule_add: "added a rule",
  rule_set: "changed a rule", event_keep: "said whether you're going to an event", skip: "skipped one of a repeat",
  suggestion_accept: "accepted something from the Inbox", review_task: "answered the Review", undo: "undid something",
  category_merge: "merged two categories", series_edit: "changed a repeat", sync: "Friday read your calendars",
  nightly: "Friday's nightly run",
} // prettier-ignore

/** "After you deleted something and changed a setting." — what led to the plan, each kind once, in order. */
export function because(inputs: readonly { actor?: unknown; command?: unknown }[]): string {
  const said = [...new Set(inputs.map((i) => DID[String(i.command)] ?? (i.command ? `used ${String(i.command).replaceAll("_", " ")}` : "")).filter(Boolean))]
  if (!said.length) return "Friday planned again on its own."
  const yours = inputs.some((i) => i.actor === "you" || i.actor == null)
  const list = said.length === 1 ? said[0] : `${said.slice(0, -1).join(", ")} and ${said.at(-1)}`
  return yours ? `After you ${list}.` : `After ${list}.`
}
