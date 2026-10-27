// Several tasks at once (⌘-click or Shift-click in the list, ⌘A for all), and several blocks or events picked on the
// calendar (plan/PickBar.tsx). What one task's detail does is done to each (27 Oct: "make the group select feature
// apply to all individual components"): done or open again, the due, the estimate, the tag, the kind, how firm the
// deadline is, whether it's pointless late, whether it runs by itself, time to get there, whether it might not
// happen, starting over, Short or Long term, or deleted. Each change is made task by task and comes back as one, with
// one Undo for all of them.

import { useQueryClient } from "@tanstack/react-query"
import { createContext, type CSSProperties, type ReactNode, useContext, useState } from "react"
import type { Item } from "@/api/client"
import { Dropdown } from "@/components/fr/Dropdown"
import { Chip, Icon, Seg } from "@/components/fr/controls"
import { useToast } from "@/components/Toasts"
import { rememberTogether, runCommand, undoAll } from "@/hooks/useCommand"
import { useAreas } from "@/hooks/queries"
import { dur } from "@/lib/format"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"
import { usePresets } from "./AddBox"
import { DuePicker, LengthPicker, ListPicker } from "./Pickers"

type Ran = { command_id: number | null } | undefined

export const tasks = (n: number) => `${n} task${n === 1 ? "" : "s"}`

/** A menu of the bar's is open: Esc closes it and keeps what's picked. */
export const menuOpen = () => !!document.querySelector('[role="toolbar"] [aria-expanded="true"]')

/** A change made to each of several tasks, said once and undone together. */
export interface Group {
  items: Item[]
  busy: string | null
  each: (what: string, said: string, run: (i: Item) => Promise<Ran> | null, clear?: boolean) => Promise<void>
  together: (what: string, said: string, steps: (() => Promise<Ran> | null)[], clear?: boolean) => Promise<void>
  edit: (fields: Record<string, unknown> | ((i: Item) => Record<string, unknown> | null)) => (i: Item) => Promise<Ran> | null
  run: (name: string, input: (i: Item) => Record<string, unknown> | null) => (i: Item) => Promise<Ran> | null
  working: (what: string, label: string) => string
  same: <T>(of: (i: Item) => T) => T | null // the value they all have, or null when they differ
}

export function useGroup(items: Item[], onClear: () => void): Group {
  const client = useQueryClient()
  const toast = useToast()
  const [busy, setBusy] = useState<string | null>(null)
  // One change for every picked task, then one toast that undoes all of it.
  const together: Group["together"] = async (what, said, steps, clear = false) => {
    setBusy(what)
    const ids: number[] = []
    for (const step of steps) {
      const out = await step()
      if (out?.command_id != null) ids.push(out.command_id)
    }
    setBusy(null)
    rememberTogether(ids) // ⌘Z takes back all of them, after the toast has gone too
    if (ids.length) toast({ message: `${said}. ⌘Z undoes it`, action: { label: "Undo", run: () => undoAll(client, toast, ids) } })
    if (clear) onClear()
  }
  const each: Group["each"] = (what, said, run, clear) => together(what, said, items.map((i) => () => run(i)), clear)
  const run: Group["run"] = (name, input) => (i) => {
    const given = input(i)
    return given ? (runCommand(client, toast, name as "edit", given as never, { quiet: true }) as Promise<Ran>) : null
  }
  const edit: Group["edit"] = (fields) => run("edit", (i) => {
    const given = typeof fields === "function" ? fields(i) : fields
    return given ? { id: i.id, ...given } : null
  })
  const same: Group["same"] = (of) => (items.length && items.every((i) => of(i) === of(items[0])) ? of(items[0]) : null)
  return { items, busy, each, together, edit, run, working: (what, label) => (busy === what ? `${label}…` : label), same }
}

export function BulkBar({ items, onClear, hint, place }: { items: Item[]; onClear: () => void; hint?: string; place?: Place }) {
  const g = useGroup(items, onClear)
  const n = items.length
  const allLong = items.every((i) => i.long_term)
  return (
    <GroupBar label={tasks(n)} onClear={onClear} hint={hint} place={place}>
      <DoneButton g={g} />
      <DueAction g={g} />
      <EstimateAction g={g} />
      <TagAction g={g} />
      <KindAction g={g} />
      <Act icon={allLong ? "arrow-up" : "arrow-down"} label={g.working("list", allLong ? "To Short term" : "To Long term")} disabled={!!g.busy} onClick={() => g.each("list", `Moved ${tasks(n)} to ${allLong ? "Short" : "Long"} term`, g.edit({ long_term: !allLong }), true)} />
      <MoreAction g={g} />
      <DeleteButton g={g} />
    </GroupBar>
  )
}

type Place = "list" | "calendar" | "drawer"

// In the drawer the bar is one row of icons, each named on hover, with its menus opening down.
const Compact = createContext(false)
const useBarLook = () => (useContext(Compact) ? { wide: false, up: false } : { wide: true, up: true })

function Act({ icon, label, onClick, disabled, danger }: { icon: string; label: string; onClick: () => void; disabled?: boolean; danger?: boolean }) {
  const compact = useContext(Compact)
  return (
    <button
      className={compact ? "btn btn-icon btn-ghost fr-press" : `btn ${danger ? "btn-ghost" : "btn-secondary"} fr-press`}
      disabled={disabled}
      onClick={onClick}
      title={compact ? label : undefined}
      aria-label={compact ? label : undefined}
      style={{ ...(danger ? { color: "var(--fr-due)" } : compact ? { color: "var(--color-neutral-300)" } : {}), ...(compact ? { width: 30, height: 30 } : {}) }}
    >
      <Icon name={icon} size={compact ? 16 : 14} />
      {!compact && label}
    </button>
  )
}

const PLACED: Record<Place, CSSProperties> = {
  list: { position: "absolute", bottom: 96, left: "50%", transform: "translateX(-50%)", width: "min(900px, calc(100% - 44px))", zIndex: 6 },
  // The calendar scrolls under it, so it stays put on the screen.
  calendar: { position: "fixed", bottom: 96, left: "calc(50% + var(--fr-side, 0px) / 2)", transform: "translateX(-50%)", width: "min(900px, calc(100vw - var(--fr-side, 0px) - 44px))", zIndex: 8 },
  // Over the drawer's title and quick add, which picking doesn't need: under the list it took the place of the rows
  // at its foot, and over them it hid the rows just picked.
  drawer: { position: "absolute", top: 6, left: 8, right: 8, zIndex: 3 },
}

/** The bar itself: over the list's foot or the calendar's, above the Now bar, so picking never moves what's under
 * the pointer; in the drawer, under its list. */
export function GroupBar({ label, onClear, place = "list", hint, children }: { label: string; onClear: () => void; place?: Place; hint?: string; children: ReactNode }) {
  return (
    <div
      role="toolbar"
      aria-label={`${label} picked`}
      className="fr-float"
      style={{ ...PLACED[place], display: "flex", alignItems: "center", gap: place === "drawer" ? 2 : 6, flexWrap: "wrap", padding: place === "drawer" ? "6px 8px" : "8px 10px" }}
    >
      <span style={{ fontWeight: 500, paddingRight: 4 }}>{label}</span>
      <Compact.Provider value={place === "drawer"}>{children}</Compact.Provider>
      <div style={{ flex: 1 }} />
      <span className="fr-kicker" style={{ whiteSpace: "nowrap", ...(place === "drawer" ? { order: 1, flexBasis: "100%" } : {}) }}>
        {hint ? `${hint} · ` : ""}Esc to clear
      </span>
      <button className="btn btn-icon btn-ghost" onClick={onClear} aria-label="Clear the picked tasks" style={{ width: 28, height: 28 }}>
        <Icon name="x" />
      </button>
    </div>
  )
}

export function DoneButton({ g }: { g: Group }) {
  const n = g.items.length
  const allDone = n > 0 && g.items.every((i) => i.status === "done")
  return allDone ? (
    <Act icon="arrow-counter-clockwise" label={g.working("done", "Open again")} disabled={!!g.busy} onClick={() => g.each("done", `Opened ${tasks(n)} again`, g.run("reopen", (i) => ({ id: i.id })), true)} />
  ) : (
    <Act icon="check" label={g.working("done", "Done")} disabled={!!g.busy || !n} onClick={() => g.each("done", `Marked ${tasks(n)} done`, g.run("done", (i) => (i.status === "todo" ? { id: i.id } : null)), true)} />
  )
}

export function DueAction({ g }: { g: Group }) {
  const { today } = useShell()
  const n = g.items.length
  return (
    <Dropdown icon="flag" label={g.working("due", "Due")} {...useBarLook()}>
      {(close) => (
        <div style={{ padding: 6 }}>
          <DuePicker value={g.same((i) => i.due)} today={today} onPick={(due) => (close(), g.each("due", due ? `Moved the due of ${tasks(n)}` : `Took the due off ${tasks(n)}`, g.edit({ due })))} />
        </div>
      )}
    </Dropdown>
  )
}

const NUDGES = [-15, 15, 30, 60]

/** Each one's estimate a little more or less, or all of them one length. Only tasks of a set length have one. */
export function EstimateAction({ g }: { g: Group }) {
  const sized = g.items.filter((i) => i.amount === "fixed")
  const n = sized.length
  if (!n) return null
  const by = (step: number) => g.edit((i) => (i.amount === "fixed" && i.duration_min != null ? { duration_min: Math.max(15, i.duration_min + step) } : null))
  return (
    <Dropdown icon="hourglass-medium" label={g.working("length", "Estimate")} {...useBarLook()}>
      {(close) => (
        <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "8px 10px" }}>
          <span className="fr-eyebrow">Each one</span>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {NUDGES.map((step) => (
              <Chip key={step} onClick={() => (close(), g.each("length", `${step < 0 ? "Took" : "Gave"} ${tasks(n)} ${dur(Math.abs(step))} ${step < 0 ? "off" : "more"}`, by(step)))}>
                {step < 0 ? `−${dur(-step)}` : `+${dur(step)}`}
              </Chip>
            ))}
          </div>
          <span className="fr-eyebrow">All of them</span>
          <LengthPicker group value={g.same((i) => i.duration_min ?? null)} onPick={(v) => v && (close(), g.each("length", `${tasks(n)} expected to take ${dur(v)}`, g.edit((i) => (i.amount === "fixed" ? { duration_min: v } : null))))} />
        </div>
      )}
    </Dropdown>
  )
}

export function TagAction({ g }: { g: Group }) {
  const { color } = useLook()
  const areas = (useAreas().data ?? []).filter((a) => !a.archived).map((a) => a.name)
  const n = g.items.length
  return (
    <Dropdown icon="tag" label={g.working("tag", "Tag")} {...useBarLook()}>
      {(close) => (
        <div style={{ padding: 6 }}>
          <ListPicker
            options={[{ value: null as string | null, label: "No tag" }, ...areas.map((a) => ({ value: a as string | null, label: a, swatch: color(a) }))]}
            value={undefined as unknown as string | null}
            onPick={(area) => (close(), g.each("tag", area ? `Tagged ${tasks(n)} ${area}` : `Took the tag off ${tasks(n)}`, g.edit({ area })))}
          />
        </div>
      )}
    </Dropdown>
  )
}

export function KindAction({ g }: { g: Group }) {
  const presets = usePresets()
  const n = g.items.length
  return (
    <Dropdown icon="shapes" label={g.working("kind", "Kind")} {...useBarLook()}>
      {(close) => (
        <div style={{ padding: 6 }}>
          <ListPicker options={presets.map((p) => ({ value: p, label: p }))} value={null as string | null} onPick={(preset) => (close(), g.each("kind", `Made ${tasks(n)} ${preset}`, g.edit({ preset })))} />
        </div>
      )}
    </Dropdown>
  )
}

const TRAVEL = [0, 10, 15, 30] // minutes each way, as a task's detail offers

/** The rest of a task's detail, for all of them: each row shows the choice they share, or none lit when they differ. */
export function MoreAction({ g }: { g: Group }) {
  const { today } = useShell()
  const n = g.items.length
  const tasksOnly = g.items.every((i) => i.when !== "fixed")
  const travel = g.same((i) => ((i.buffer_before_min ?? 0) === (i.buffer_after_min ?? 0) ? i.buffer_before_min ?? 0 : -1))
  const started = g.items.filter((i) => i.done_min > 0 && i.status === "todo")
  const row = (label: string, control: ReactNode, note?: string) => (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <span className="fr-eyebrow">{label}</span>
      {control}
      {note && <span className="fr-kicker">{note}</span>}
    </div>
  )
  return (
    <Dropdown icon="dots-three" label={g.working("more", "More")} {...useBarLook()}>
      {(close) => (
        <div style={{ display: "flex", flexDirection: "column", gap: 12, padding: "8px 10px" }}>
          {tasksOnly &&
            row(
              "Deadline",
              <Seg
                options={[{ value: "hard", label: "Hard" }, { value: "soft", label: "Soft" }, { value: "none", label: "None" }]}
                value={g.same((i) => i.firmness)}
                onPick={(firmness) => (close(), g.each("more", `Made the deadline ${firmness} for ${tasks(n)}`, g.edit({ firmness })))}
                size="small"
              />,
            )}
          {tasksOnly &&
            row(
              "After it's due",
              <Seg
                options={[{ value: "pointless", label: "⏳ Pointless" }, { value: "late", label: "Still worth doing" }]}
                value={g.same((i) => (i.pointless_late ? "pointless" : "late"))}
                onPick={(v) => (close(), g.each("more", v === "pointless" ? `${tasks(n)} never planned after their due` : `${tasks(n)} planned late if they can't be on time`, g.edit({ expires: v === "pointless" })))}
                size="small"
              />,
            )}
          {tasksOnly &&
            row(
              "Runs by itself",
              <Seg
                options={[{ value: "on", label: "Runs by itself" }, { value: "off", label: "You work on it" }]}
                value={g.same((i) => (i.background ? "on" : "off"))}
                onPick={(v) => (close(), g.each("more", v === "on" ? `${tasks(n)} run by themselves` : `${tasks(n)} need you the whole time`, g.edit({ background: v === "on" })))}
                size="small"
              />,
            )}
          {row(
            "Getting there",
            <Seg
              options={TRAVEL.map((m) => ({ value: m, label: m ? `${m} min` : "None" }))}
              value={travel === -1 ? null : travel}
              onPick={(m) =>
                (close(),
                g.each("more", m ? `${m} min kept free around ${tasks(n)}` : `Nothing kept free around ${tasks(n)}`, g.edit((i) => ({ buffer_before_min: m || null, buffer_after_min: m || null, ...(i.series_id != null ? { from_date: today } : {}) }))))
              }
              size="small"
            />,
          )}
          {row(
            "Might not happen",
            <Seg
              options={[{ value: "planned", label: "Planned as usual" }, { value: "tentative", label: "Might not happen" }]}
              value={g.same((i) => i.certainty)}
              onPick={(certainty) => (close(), g.each("more", certainty === "tentative" ? `${tasks(n)} planned loosely` : `${tasks(n)} planned as usual`, g.edit({ certainty })))}
              size="small"
            />,
          )}
          {started.length > 0 &&
            row(
              "Progress",
              <button className="btn btn-secondary" style={{ alignSelf: "flex-start" }} onClick={() => (close(), g.each("more", `Started ${tasks(started.length)} over`, g.run("progress", (i) => (started.includes(i) ? { id: i.id, share: 0 } : null))))}>
                <Icon name="arrow-counter-clockwise" size={14} />
                Start over
              </button>,
              `${tasks(started.length)} with work done: count none of it, and Friday plans all of it again.`,
            )}
        </div>
      )}
    </Dropdown>
  )
}

export function DeleteButton({ g, label = "Delete" }: { g: Group; label?: string }) {
  const n = g.items.length
  return (
    <Act icon="trash" label={g.working("delete", label)} danger disabled={!!g.busy || !n} onClick={() => g.each("delete", `Deleted ${tasks(n)}`, g.run("drop", (i) => ({ id: i.id })), true)} />
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
