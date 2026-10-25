// Several tasks at once (⌘-click or Shift-click in the list, ⌘A for all): done, a due date, a kind, a tag, Short or
// Long term, or deleted. Each change is made task by task and comes back as one, with one Undo for all of them.

import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import type { Item } from "@/api/client"
import { Dropdown } from "@/components/fr/Dropdown"
import { Icon } from "@/components/fr/controls"
import { useToast } from "@/components/Toasts"
import { rememberTogether, runCommand, undoAll } from "@/hooks/useCommand"
import { useAreas } from "@/hooks/queries"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"
import { usePresets } from "./AddBox"
import { DuePicker, ListPicker } from "./Pickers"

type Ran = { command_id: number | null } | undefined

export const tasks = (n: number) => `${n} task${n === 1 ? "" : "s"}`

export function BulkBar({ items, onClear }: { items: Item[]; onClear: () => void }) {
  const client = useQueryClient()
  const toast = useToast()
  const { today } = useShell()
  const { color } = useLook()
  const presets = usePresets()
  const areas = (useAreas().data ?? []).filter((a) => !a.archived).map((a) => a.name)
  const [busy, setBusy] = useState<string | null>(null)
  const n = items.length
  const allLong = items.every((i) => i.long_term)
  // One change for every picked task, then one toast that undoes all of it.
  const each = async (what: string, said: string, run: (i: Item) => Promise<Ran> | null, clear = false) => {
    setBusy(what)
    const ids: number[] = []
    for (const item of items) {
      const out = await run(item)
      if (out?.command_id != null) ids.push(out.command_id)
    }
    setBusy(null)
    rememberTogether(ids) // ⌘Z takes back all of them, after the toast has gone too
    if (ids.length) toast({ message: `${said}. ⌘Z undoes it`, action: { label: "Undo", run: () => undoAll(client, toast, ids) } })
    if (clear) onClear()
  }
  const edit = (fields: Record<string, unknown>) => (i: Item) => runCommand(client, toast, "edit", { id: i.id, ...fields }, { quiet: true })
  const working = (what: string, label: string) => (busy === what ? `${label}…` : label)
  return (
    <div
      role="toolbar"
      aria-label={`${tasks(n)} picked`}
      className="fr-float"
      // Over the list's foot, above the Now bar: picking never moves the rows under the pointer.
      style={{ position: "absolute", bottom: 96, left: "50%", transform: "translateX(-50%)", width: "min(820px, calc(100% - 44px))", zIndex: 6, display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", padding: "8px 10px" }}
    >
      <span style={{ fontWeight: 500, paddingRight: 4 }}>{tasks(n)}</span>
      <button className="btn btn-secondary fr-press" disabled={!!busy} onClick={() => each("done", `Marked ${tasks(n)} done`, (i) => (i.status === "todo" ? runCommand(client, toast, "done", { id: i.id }, { quiet: true }) : null), true)}>
        <Icon name="check" size={14} />
        {working("done", "Done")}
      </button>
      <Dropdown icon="flag" label={working("due", "Due")} wide up>
        {(close) => (
          <div style={{ padding: 6 }}>
            <DuePicker value={null} today={today} onPick={(due) => (close(), each("due", due ? `Moved the due of ${tasks(n)}` : `Took the due off ${tasks(n)}`, edit({ due })))} />
          </div>
        )}
      </Dropdown>
      <Dropdown icon="shapes" label={working("kind", "Kind")} wide up>
        {(close) => (
          <div style={{ padding: 6 }}>
            <ListPicker options={presets.map((p) => ({ value: p, label: p }))} value={null as string | null} onPick={(preset) => (close(), each("kind", `Made ${tasks(n)} ${preset}`, edit({ preset })))} />
          </div>
        )}
      </Dropdown>
      <Dropdown icon="tag" label={working("tag", "Tag")} wide up>
        {(close) => (
          <div style={{ padding: 6 }}>
            <ListPicker
              options={[{ value: null as string | null, label: "No tag" }, ...areas.map((a) => ({ value: a as string | null, label: a, swatch: color(a) }))]}
              value={undefined as unknown as string | null}
              onPick={(area) => (close(), each("tag", area ? `Tagged ${tasks(n)} ${area}` : `Took the tag off ${tasks(n)}`, edit({ area })))}
            />
          </div>
        )}
      </Dropdown>
      <button className="btn btn-secondary fr-press" disabled={!!busy} onClick={() => each("list", `Moved ${tasks(n)} to ${allLong ? "Short" : "Long"} term`, edit({ long_term: !allLong }), true)}>
        <Icon name={allLong ? "arrow-up" : "arrow-down"} size={14} />
        {working("list", allLong ? "To Short term" : "To Long term")}
      </button>
      <button className="btn btn-ghost fr-press" disabled={!!busy} onClick={() => each("delete", `Deleted ${tasks(n)}`, (i) => runCommand(client, toast, "drop", { id: i.id }, { quiet: true }), true)} style={{ color: "var(--fr-due)" }}>
        <Icon name="trash" size={14} />
        {working("delete", "Delete")}
      </button>
      <div style={{ flex: 1 }} />
      <span className="fr-kicker" style={{ whiteSpace: "nowrap" }}>
        Esc to clear
      </span>
      <button className="btn btn-icon btn-ghost" onClick={onClear} aria-label="Clear the picked tasks" style={{ width: 28, height: 28 }}>
        <Icon name="x" />
      </button>
    </div>
  )
}

/** The tasks a click picks: ⌘ (or Ctrl) adds or removes one, Shift takes the run from the last one picked. */
export function pickWith(order: number[], picked: number[], anchor: number | null, id: number, toggle: boolean, range: boolean): number[] {
  if (range && anchor !== null && order.includes(anchor)) {
    const [a, b] = [order.indexOf(anchor), order.indexOf(id)].sort((x, y) => x - y)
    return [...new Set([...picked, ...order.slice(a, b + 1)])]
  }
  if (toggle || range) return picked.includes(id) ? picked.filter((p) => p !== id) : [...picked, id]
  return []
}
