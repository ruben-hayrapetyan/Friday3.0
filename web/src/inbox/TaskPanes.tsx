// Copies of a task, and going over what Friday brought in again, each a message in the Inbox (they were a page of
// their own, Check your tasks, until 29 Oct: "make everything just a message the user needs to deal with in inbox").
// A copy usually comes from one deadline sitting on two calendars: you pick the one to keep and the others' time logged
// moves onto it. Going over again keeps each task planned until you've decided: keep it, change its kind, or take it
// off your list (its calendar keeps the event either way).

import { useState } from "react"
import type { Item, Schemas } from "@/api/client"
import { DueLabel } from "@/components/DueLabel"
import { Menu } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { dur } from "@/lib/format"
import { useLook } from "@/theme/LookProvider"
import { usePresets } from "@/todo/AddBox"
import { Actions, After, Pane } from "./Pane"

type Group = Schemas["DuplicateGroup"]
type Done = (sent?: Promise<unknown>) => void

/** A task on your list more than once: which to keep. `all` are every task with copies, for one of each at once. */
export function CopiesPane({ group, from, all, onDone, onAllDone }: { group: Group; from: Record<number, string>; all: Group[]; onDone: Done; onAllDone: Done }) {
  const merge = useCommand("duplicates_merge", { label: (o) => o.result.message ?? "Merged" })
  const apart = useCommand("not_duplicates", { label: () => "Kept apart" })
  const [kept, setKept] = useState(group.keep)
  const drop = (g: Group, keep: number) => g.items.map((i) => i.id).filter((id) => id !== keep)
  return (
    <Pane icon="copy" kicker={`Copies · on your list ${group.items.length} times`} title={group.items[0]?.title ?? group.key}>
      <span style={{ color: "var(--color-neutral-300)", textWrap: "pretty" }}>
        Usually a deadline on two of your calendars. Pick the one to keep; the others’ time logged moves onto it, and your calendars keep their events.
      </span>
      <div className="fr-well" style={{ display: "flex", flexDirection: "column", gap: 4, padding: "10px 12px", borderRadius: "var(--radius-md)" }}>
        {group.items.map((i) => (
          <label key={i.id} className="fr-hover-soft" style={{ display: "grid", gridTemplateColumns: "20px minmax(0,1fr)", gap: 8, alignItems: "center", padding: "4px 6px", borderRadius: 4, cursor: "pointer" }}>
            <input type="radio" name={group.key} checked={i.id === kept} onChange={() => setKept(i.id)} aria-label={`Keep ${i.title} (${from[i.id] ?? "you"})`} />
            <TaskLine item={i} from={from[i.id]} dim={i.id !== kept} />
          </label>
        ))}
      </div>
      <Actions>
        <button className="btn btn-primary" onClick={() => onDone(merge({ groups: [{ keep: kept, drop: drop(group, kept) }] }))}>
          Keep the chosen one
        </button>
        <button className="btn btn-secondary" onClick={() => onDone(apart({ ids: group.items.map((i) => i.id) }))}>
          They’re different
        </button>
      </Actions>
      {all.length > 1 && (
        <After>
          {all.length} tasks have copies.
          <button className="fr-plain fr-link" style={{ fontSize: 12 }} onClick={() => onAllDone(merge({ groups: all.map((g) => (g.key === group.key ? { keep: kept, drop: drop(g, kept) } : { keep: g.keep, drop: drop(g, g.keep) })) }))}>
            Keep one of each ({all.length})
          </button>
        </After>
      )}
    </Pane>
  )
}

/** A task Friday brought in, gone over again: keep it, fix its kind, or take it off your list. */
export function AgainPane({ item, from, all, onDone, onAllDone }: { item: Item; from?: string; all: Item[]; onDone: Done; onAllDone: Done }) {
  const done = useCommand("reviewed", { label: (o) => o.result.message ?? "Done" })
  const edit = useCommand("edit", { label: () => "Kind changed" })
  const presets = usePresets()
  return (
    <Pane icon="arrow-counter-clockwise" kicker={`Going over what Friday brought in · from ${from ?? "you"}`} title={item.title}>
      <TaskLine item={item} from={from} />
      <span style={{ color: "var(--color-neutral-300)", textWrap: "pretty" }}>Keep it if it’s right, fix a wrong kind, or take it off your list. Taking it off never touches your calendar. Until you decide, it stays planned.</span>
      <Actions>
        <button className="btn btn-primary" onClick={() => onDone(done({ ids: [item.id], keep: true }))}>
          Keep it
        </button>
        <Menu options={presets.map((p) => ({ value: p, label: p }))} value={item.preset ?? ""} onPick={(preset) => edit({ id: item.id, preset })} label={`Kind of ${item.title}`} />
        <button className="btn btn-ghost" onClick={() => onDone(done({ ids: [item.id], keep: false }))} style={{ color: "var(--fr-due)" }}>
          Take it off my list
        </button>
      </Actions>
      {all.length > 1 && (
        <After>
          {all.length} left to go over.
          <button className="fr-plain fr-link" style={{ fontSize: 12 }} onClick={() => onAllDone(done({ ids: all.map((i) => i.id), keep: true }))}>
            Keep all {all.length}
          </button>
        </After>
      )}
    </Pane>
  )
}

/** A task on one line: its title and tag, then kind, due, length, time done and where it came from. */
function TaskLine({ item, from, dim }: { item: Item; from?: string; dim?: boolean }) {
  const { color } = useLook()
  const meta = { fontSize: 11, color: "var(--color-neutral-500)", whiteSpace: "nowrap" } as const
  return (
    <span style={{ display: "flex", flexWrap: "wrap", gap: "2px 10px", alignItems: "baseline", minWidth: 0, opacity: dim ? 0.6 : 1 }}>
      <span style={{ fontSize: 13, fontWeight: 500 }}>{item.title}</span>
      {item.area && (
        <span style={{ ...meta, display: "inline-flex", gap: 4, alignItems: "center" }}>
          <span style={{ width: 6, height: 6, borderRadius: 2, background: color(item.area, item.preset) }} />
          {item.area}
        </span>
      )}
      <span className="tnum fr-mono" style={meta}>
        {item.preset ?? "No kind"}
        {item.due && (
          <>
            {" · "}
            <DueLabel due={item.due} prefix="due " />
          </>
        )}
        {item.duration_min ? ` · ${dur(item.duration_min)}` : ""}
        {item.done_min ? ` · ${dur(item.done_min)} done` : ""}
        {` · from ${from ?? "you"}`}
      </span>
    </span>
  )
}
