// A break, in a popup in the middle of the screen (UI-PRINCIPLES: something opened from a list opens as a center
// popup): its name, days, how much work, what it pauses, meals and sleep. Each row says its value and opens its
// choices, as To-do details' rows do. A change to one of yours is saved at once, with Undo in its toast; a new one is
// added with Add break. Deleting one is undone the same way, so it asks nothing.

import { type QueryClient, useQuery } from "@tanstack/react-query"
import { type ReactNode, useState } from "react"
import { query, type Schemas } from "@/api/client"
import { Icon, Menu, Switch } from "@/components/fr/controls"
import { Modal } from "@/dialogs/Dialogs"
import { useItems, useSettings } from "@/hooks/queries"
import { useCommand } from "@/hooks/useCommand"
import type { BreakEdit } from "@/shell/ShellContext"
import { useShell } from "@/shell/ShellContext"
import { LengthField } from "@/todo/Pickers"
import { PauseChooser, useBreakChoices } from "./PauseChooser"
import { BREAK_ICON, daysIn, EVERYTHING, full, nextDay, type Pause, pauseWords, rangeWords, things, type Vacation, WORK_AMOUNTS } from "./words"

/** Your defaults for a break (Settings → Breaks; core/settings.py `BreakSettings`). */
export type Defaults = { work_min: number; pause: Pause; plan_meals: boolean; plan_repeating?: boolean; keep_sleep: boolean }
type Row = "dates" | "mode" | "pause" | null

export const useVacations = () => useQuery({ queryKey: ["vacations"], queryFn: () => query("vacations") })

export function useBreakDefaults(): Defaults {
  const saved = (useSettings().data as Record<string, unknown> | undefined)?.breaks as Defaults | undefined
  return saved ? { ...saved, pause: full(saved.pause) } : { work_min: 120, pause: EVERYTHING, plan_meals: false, plan_repeating: false, keep_sleep: false }
}

/** A change to a break shows at once in the list of breaks (the server's answer follows). */
export function editedNow(client: QueryClient, input: Schemas["VacationEditInput"]): void {
  client.setQueryData<Schemas["VacationsOut"]>(["vacations"], (all) => all && { vacations: all.vacations.map((v) => (v.id === input.id ? { ...v, ...withoutNulls(input) } as Vacation : v)) })
}

function withoutNulls(input: Schemas["VacationEditInput"]): Partial<Vacation> {
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(input)) if (v !== null && v !== undefined && k !== "id" && k !== "defaults") out[k] = v
  return out as Partial<Vacation>
}

export function BreakDialog({ edit, onClose }: { edit: BreakEdit; onClose: () => void }) {
  const { today } = useShell()
  const defaults = useBreakDefaults()
  const saved = useVacations().data?.vacations.find((v) => v.id === edit.id)
  const start = edit.id === undefined ? (edit.start ?? today) : undefined
  // A new break's own state until it's added: from your defaults, a week from the day it was opened on.
  const [draft, setDraft] = useState<Vacation>(() => ({
    id: 0, name: edit.id === undefined ? (edit.name ?? "") : "", start: start ?? today, end: edit.id === undefined ? (edit.end ?? addWeek(start ?? today)) : today, days: 7, mode: "light",
    work_min: defaults.work_min, pause: defaults.pause, plan_meals: defaults.plan_meals, plan_repeating: defaults.plan_repeating ?? false, keep_sleep: defaults.keep_sleep, own: [],
  }))
  const v = edit.id === undefined ? draft : saved
  const [open, setOpen] = useState<Row>(edit.id === undefined && edit.pickDays ? "dates" : null)
  const change = useCommand("vacation_edit", { optimistic: editedNow, label: (o) => o.result.message })
  const add = useCommand("vacation_add", { label: (o) => o.result.message })
  const remove = useCommand("vacation_delete", { label: (o) => o.result.message })
  const [refused, setRefused] = useState<string | null>(null)
  if (!v) return null
  const isNew = edit.id === undefined
  const set = (fields: Partial<Vacation>) => {
    setRefused(null)
    if (isNew) return setDraft({ ...draft, ...fields })
    change({ ...(fields as Schemas["VacationEditInput"]), id: v.id })
  }
  const toggle = (row: Row) => setOpen(open === row ? null : row)
  const create = async () => {
    const name = v.name.trim() || "Break"
    const out = await add({ name, start: v.start, end: v.end, mode: v.mode, work_min: v.work_min, pause: full(v.pause), plan_meals: v.plan_meals, plan_repeating: v.plan_repeating, keep_sleep: v.keep_sleep })
    if (out) onClose()
  }
  const badDays = v.end < v.start
  return (
    <Modal onClose={onClose} top width={620} label={isNew ? "Add a break" : v.name}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span className="fr-kicker" style={{ flex: 1, color: "var(--fr-break)" }}>
          <Icon name={BREAK_ICON} size={12} /> {isNew ? "A new break" : "Break"}
        </span>
        <button className="btn btn-icon btn-ghost" onClick={onClose} aria-label="Close" style={{ width: 28, height: 28, color: "var(--color-neutral-400)" }}>
          <Icon name="x" />
        </button>
      </div>
      <input
        className="fr-plain fr-h"
        value={isNew ? draft.name : undefined}
        defaultValue={isNew ? undefined : v.name}
        key={isNew ? "new" : `name${v.id}`}
        placeholder="Name this break"
        aria-label="Name"
        onChange={(e) => isNew && setDraft({ ...draft, name: e.target.value })}
        onBlur={(e) => !isNew && e.target.value.trim() && e.target.value.trim() !== v.name && set({ name: e.target.value.trim() })}
        onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
        style={{ fontSize: 28, lineHeight: 1.15, width: "100%", background: "transparent", border: 0, outline: 0, padding: "4px 0", color: "var(--color-text)" }}
      />
      <div style={{ display: "grid", gridTemplateColumns: "120px minmax(0,1fr)", gap: "12px 14px", alignItems: "center", marginTop: 8 }}>
        <span className="fr-kicker">Days</span>
        <Value onClick={() => toggle("dates")} icon="calendar-blank">
          {rangeWords(v.start, v.end)}
          {!badDays && <span style={{ color: "var(--color-neutral-500)" }}> · {daysIn(v.start, v.end)} days</span>}
        </Value>
        {open === "dates" && (
          <Panel>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <span className="fr-kicker">From</span>
                <input className="input tnum" type="date" value={v.start} onChange={(e) => e.target.value && set({ start: e.target.value, ...(e.target.value > v.end ? { end: e.target.value } : {}) })} aria-label="First day" />
              </label>
              <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <span className="fr-kicker">To</span>
                <input className="input tnum" type="date" value={v.end} min={v.start} onChange={(e) => e.target.value && set({ end: e.target.value })} aria-label="Last day" />
              </label>
            </div>
          </Panel>
        )}
        <span className="fr-kicker">Work</span>
        {/* Friday's own menu, as every dropdown (25 Nov, the user: "the dropdown for take a break ... is huge": two
            choices opened a panel the width of the dialog) */}
        <div style={{ justifySelf: "start" }}>
          <Menu
            label="Work during the break"
            value={v.mode}
            onPick={(mode) => set({ mode: mode as Vacation["mode"] })}
            options={[
              { value: "light", label: "Light", hint: "A few things to get done each day, whenever suits: a list, no set times." },
              { value: "off", label: "Off", hint: "Nothing to do. Work due during the break is planned before it starts." },
            ]}
          />
        </div>
        {v.mode === "light" && (
          <>
            <span className="fr-kicker">A day</span>
            {/* 19 Nov: time a day, not a number of things; the day's list still names tasks, never minutes */}
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <LengthField value={v.work_min} onPick={(m) => m && set({ work_min: m })} label="Work a day" amounts={WORK_AMOUNTS} unit=" a day" />
              <span className="fr-kicker">of work; its list shows tasks by name, not minutes</span>
            </div>
          </>
        )}
        <span className="fr-kicker">Pauses</span>
        <PauseValue pause={full(v.pause)} onClick={() => toggle("pause")} />
        {open === "pause" && (
          <Panel>
            <PauseChooser pause={full(v.pause)} onChange={(pause: Pause) => set({ pause })} />
          </Panel>
        )}
        <span className="fr-kicker">Meals</span>
        <Toggle on={v.plan_meals} label="Plan meals during the break" onToggle={() => set({ plan_meals: !v.plan_meals })}>
          {v.plan_meals ? "Planned as usual" : "Not planned"}
        </Toggle>
        <span className="fr-kicker">Repeating tasks</span>
        <Toggle on={v.plan_repeating} label="Plan repeating tasks during the break" onToggle={() => set({ plan_repeating: !v.plan_repeating })}>
          {v.plan_repeating ? "Planned as usual" : "Not planned"}
        </Toggle>
        <span className="fr-kicker">Sleep</span>
        <Toggle on={v.keep_sleep} label="Keep my sleep schedule during the break" onToggle={() => set({ keep_sleep: !v.keep_sleep })}>
          {v.keep_sleep ? "Your usual schedule" : "Not planned"}
        </Toggle>
        <span className="fr-kicker">Due in it</span>
        <DueInside start={v.start} end={v.end} mode={v.mode} />
        <span className="fr-kicker">Learning</span>
        <span style={{ fontSize: 12.5, color: "var(--color-neutral-300)", textWrap: "pretty" }}>Paused: these days don't count toward Insights or teach Friday how long things take.</span>
      </div>
      {(refused || badDays) && <span style={{ color: "var(--fr-warn)", fontSize: 12.5, marginTop: 10, display: "block" }}>{refused ?? "A break ends on or after the day it starts."}</span>}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 18 }}>
        {!isNew && (
          <button className="btn btn-ghost" onClick={() => (remove({ id: v.id }), onClose())}>
            <Icon name="trash" size={14} /> Delete break
          </button>
        )}
        <span style={{ flex: 1, fontSize: 12, color: "var(--color-neutral-500)" }}>{isNew ? "" : "Changes are saved as you make them."}</span>
        {isNew ? (
          <button className="btn btn-primary" disabled={badDays} onClick={create}>
            Add break
          </button>
        ) : (
          <button className="btn btn-primary" onClick={onClose}>
            Done
          </button>
        )}
      </div>
    </Modal>
  )
}

const addWeek = (date: string) => {
  let d = date
  for (let n = 0; n < 6; n++) d = nextDay(d)
  return d
}

/** A row's value, as To-do details shows one: words in a well, opening its choices. */
export function Value({ onClick, icon, children }: { onClick: () => void; icon: string; children: ReactNode }) {
  return (
    <button onClick={onClick} className="fr-plain fr-well tnum" style={{ justifySelf: "start", alignSelf: "flex-start", display: "inline-flex", gap: 6, alignItems: "center", padding: "4px 10px", borderRadius: "var(--radius-sm)", fontSize: 12.5, textAlign: "left", maxWidth: "100%", cursor: "pointer" }}>
      <Icon name={icon} size={12} style={{ flex: "none" }} />
      <span style={{ minWidth: 0, overflowWrap: "anywhere" }}>{children}</span>
      <Icon name="caret-down" size={10} style={{ opacity: 0.6, flex: "none" }} />
    </button>
  )
}

/** What a value opens: under it, as wide as what's in it, and never taller than a third of the window (25 Nov, the
 * user: "the dropdown for take a break when i select it is huge": it spanned the dialog for two dates or two choices,
 * and Pauses' list pushed Add break off the screen); a long one scrolls inside. */
export function Panel({ children }: { children: ReactNode }) {
  return (
    <div className="fr-well" data-panel="break-value" style={{ gridColumn: "2 / -1", justifySelf: "start", width: "fit-content", maxWidth: "min(100%, 440px)", maxHeight: "max(220px, 34vh)", overflowY: "auto", padding: 12 }}>
      {children}
    </div>
  )
}

export function PauseValue({ pause, onClick }: { pause: Pause; onClick: () => void }) {
  const choices = useBreakChoices().data
  return (
    <Value onClick={onClick} icon="pause-circle">
      {pauseWords(pause, choices)}
    </Value>
  )
}

function Toggle({ on, label, onToggle, children }: { on: boolean; label: string; onToggle: () => void; children: ReactNode }) {
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12.5 }}>
      <Switch on={on} onToggle={onToggle} label={label} />
      <span style={{ color: on ? "var(--color-text)" : "var(--color-neutral-400)" }}>{children}</span>
    </span>
  )
}

/** Work due during a break: not meals, routines or habits, which are part of the day (as Insights counts work). */
export function dueInside<T extends { due?: string | null; preset?: string | null; when?: string | null }>(items: T[], start: string, end: string): T[] {
  return items.filter((i) => !!i.due && i.due.slice(0, 10) >= start && i.due.slice(0, 10) <= end && i.preset !== "Routine" && i.preset !== "Habit" && i.when !== "fixed")
}

/** What's due during a break, and what happens to it. */
function DueInside({ start, end, mode }: { start: string; end: string; mode: string }) {
  const due = dueInside(useItems().data ?? [], start, end)
  if (!due.length) return <span style={{ fontSize: 12.5, color: "var(--color-neutral-400)" }}>Nothing due</span>
  const names = due.slice(0, 3).map((i) => i.title)
  const more = due.length > 3 ? ` and ${due.length - 3} more` : ""
  return (
    <span style={{ fontSize: 12.5, color: "var(--color-neutral-300)", textWrap: "pretty" }}>
      {things(due.length)}: {names.join(", ")}
      {more}. {mode === "off" ? "Planned in the days before it starts." : "On the lists of the days before they're due."}
    </span>
  )
}
