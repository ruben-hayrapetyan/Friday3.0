// Calendars (COMBINED.md 17, 19, 28, 59, 60): what counts as busy when Friday plans, each calendar's pigment and its
// button in the title row, and the categories that colour events by their titles, with the filter that hides the
// ones you'd rather not see (office hours). Chroma's categories.json is imported into these once.

import { useEffect, useState } from "react"
import { Icon, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useSettings } from "@/hooks/queries"
import { PIGMENTS, pigment } from "@/lib/pigments"
import { useLook } from "@/theme/LookProvider"
import { Calendars, useCalendars, useMacCalendars } from "./Calendars"
import { Field, SectionHead } from "./SettingsPage"

export interface Category {
  name: string
  slug: string
  color: string
  pattern: string
  note?: string | null
}
export interface CategorySettings {
  categories: Category[]
  filter: { label: string; pattern: string; except_: string[] } | null
}
interface Busy {
  count_filtered: boolean
  count_free: boolean
  count_reminders: boolean
  calendars: Record<string, boolean>
}
interface CalendarLook {
  colors: Record<string, string>
  toolbar: string[]
}

const ROOMS = /\b(rooms?|bookings?|reservations?)\b/i

/** Whether a calendar's events block time: as you said, else all but calendars of room bookings (as the server). */
export const counts = (name: string, busy: Busy) => busy.calendars[name] ?? !ROOMS.test(name)

export function CalendarsSection() {
  const settings = useSettings().data as Record<string, unknown> | undefined
  const save = useCommand("settings_set", { label: () => "Saved" })
  const google = (useCalendars().data ?? []).filter((c) => c.on)
  const mac = (useMacCalendars().data ?? []).filter((c) => c.on && !google.some((g) => g.name === c.name))
  const reading = [...google, ...mac] // what the plan shows, by name
  if (!settings) return null
  const busy = settings.busy as Busy
  const look = settings.calendar_look as CalendarLook
  const setBusy = (change: Partial<Busy>) => save({ key: "busy", value: { ...busy, ...change } })
  const setLook = (change: Partial<CalendarLook>) => save({ key: "calendar_look", value: { ...look, ...change } })
  const filter = (settings.categories as CategorySettings).filter
  return (
    <>
      <SectionHead title="Calendars" note="What Friday plans around, and how your events look." />
      <Field name="What counts as busy" note="Not everything on a calendar is a commitment. These are left out of planning unless you switch them on; they stay on your calendar either way.">
        <Toggle on={busy.count_reminders} onToggle={() => setBusy({ count_reminders: !busy.count_reminders })} label="Reminders that something is due" hint="“Problem Set 8 due”, “Essay deadline”" />
        <Toggle on={busy.count_free} onToggle={() => setBusy({ count_free: !busy.count_free })} label="Events marked free" hint="Free in their calendar, like a reminder or a hold" />
        <Toggle on={busy.count_filtered} onToggle={() => setBusy({ count_filtered: !busy.count_filtered })} label={filter ? `${filter.label}` : "Events the filter hides"} hint={filter ? "What the categories’ filter hides" : "Set a filter under Categories"} />
      </Field>
      <Field name="Your calendars" note="A pigment for each, a button in the title row to show or hide it, and whether its events count as busy. Calendars of room bookings start out not counted.">
        {reading.length === 0 ? (
          <span className="fr-kicker">Calendars list here once Google is connected (Integrations), and the Mac app's once it runs.</span>
        ) : (
          reading.map((c) => (
            <div key={c.id} className="fr-row" style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto auto auto", gap: 14, alignItems: "center", padding: "8px 0" }}>
              <span style={{ display: "flex", gap: 8, alignItems: "center", minWidth: 0 }}>
                <span style={{ width: 10, height: 10, borderRadius: "50%", flex: "none", background: swatchOf(look.colors[c.name]) }} />
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.name}</span>
              </span>
              <PigmentMenu value={look.colors[c.name] ?? null} onPick={(color) => setLook({ colors: color ? { ...look.colors, [c.name]: color } : omit(look.colors, c.name) })} />
              <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12 }} title="A button in the title row shows or hides this calendar">
                <Switch on={look.toolbar.includes(c.name)} onToggle={() => setLook({ toolbar: look.toolbar.includes(c.name) ? look.toolbar.filter((n) => n !== c.name) : [...look.toolbar, c.name] })} label={`Button for ${c.name}`} />
                Button
              </label>
              <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12 }}>
                <Switch on={counts(c.name, busy)} onToggle={() => setBusy({ calendars: { ...busy.calendars, [c.name]: !counts(c.name, busy) } })} label={`${c.name} counts as busy`} />
                Busy
              </label>
            </div>
          ))
        )}
      </Field>
      <Field name="This Mac’s calendars" note="Sent by the Mac app. Choose which Friday reads, and whether their events skip the Inbox.">
        <Calendars mac />
      </Field>
      <Field name="New events go to" note="Events you make in Friday are saved to this Google calendar too, and follow it from then on. Kept only in Friday when none is chosen.">
        <select
          className="input"
          value={(settings.gcal as { new_events_to?: string | null }).new_events_to ?? ""}
          onChange={(e) => save({ key: "gcal", value: { ...(settings.gcal as object), new_events_to: e.target.value || null } })}
          style={{ alignSelf: "flex-start", width: 280 }}
          aria-label="New events go to"
        >
          <option value="">Only Friday</option>
          {google
            .filter((c) => c.writable)
            .map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
        </select>
      </Field>
      <Categories value={settings.categories as CategorySettings} onSave={(value) => save({ key: "categories", value })} />
    </>
  )
}

function Toggle({ on, onToggle, label, hint }: { on: boolean; onToggle: () => void; label: string; hint: string }) {
  return (
    <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
      <Switch on={on} onToggle={onToggle} label={label} />
      <span style={{ display: "flex", flexDirection: "column" }}>
        <span>{label}</span>
        <span className="fr-kicker">{on ? "Counted as busy" : "Left out"} · {hint}</span>
      </span>
    </div>
  )
}

function swatchOf(id: string | null | undefined): string {
  return pigment(id, true) ?? "color-mix(in srgb, var(--color-text) 25%, transparent)"
}

function omit(colors: Record<string, string>, name: string): Record<string, string> {
  return Object.fromEntries(Object.entries(colors).filter(([k]) => k !== name))
}

/** A pigment from personal's palette, or none. */
export function PigmentMenu({ value, onPick }: { value: string | null; onPick: (id: string | null) => void }) {
  const { light } = useLook()
  const [open, setOpen] = useState(false)
  return (
    <span style={{ position: "relative" }}>
      <button className="fr-menu-button" onClick={() => setOpen(!open)} aria-haspopup="listbox" aria-expanded={open} style={{ minWidth: 130 }}>
        <span style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <span style={{ width: 10, height: 10, borderRadius: "50%", background: pigment(value, light) ?? "transparent", boxShadow: "inset 0 0 0 1px var(--fr-rule)" }} />
          {PIGMENTS.find((p) => p.id === value)?.name ?? "No pigment"}
        </span>
        <Icon name="caret-down" size={11} />
      </button>
      {open && (
        <div className="fr-menu-list fr-float" role="listbox" style={{ minWidth: 170 }}>
          {[null, ...PIGMENTS.map((p) => p.id)].map((id) => (
            <button key={id ?? "none"} role="option" aria-selected={id === value} onClick={() => (onPick(id), setOpen(false))}>
              <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span style={{ width: 10, height: 10, borderRadius: "50%", background: pigment(id, light) ?? "transparent", boxShadow: "inset 0 0 0 1px var(--fr-rule)" }} />
                {PIGMENTS.find((p) => p.id === id)?.name ?? "No pigment"}
              </span>
            </button>
          ))}
        </div>
      )}
    </span>
  )
}

/** The categories in order (the first that matches a title wins) and the filter, saved together. */
function Categories({ value, onSave }: { value: CategorySettings; onSave: (value: CategorySettings) => void }) {
  const [draft, setDraft] = useState(value)
  useEffect(() => setDraft(value), [value])
  const changed = JSON.stringify(draft) !== JSON.stringify(value)
  const set = (i: number, change: Partial<Category>) => setDraft({ ...draft, categories: draft.categories.map((c, j) => (j === i ? { ...c, ...change } : c)) })
  const move = (i: number, by: number) => {
    const list = [...draft.categories]
    const [taken] = list.splice(i, 1)
    list.splice(Math.max(0, Math.min(list.length, i + by)), 0, taken)
    setDraft({ ...draft, categories: list })
  }
  const broken = (pattern: string) => {
    try {
      new RegExp(pattern, "i")
      return false
    } catch {
      return true
    }
  }
  const valid = draft.categories.every((c) => c.name.trim() && c.pattern.trim() && !broken(c.pattern)) && (!draft.filter || !broken(draft.filter.pattern))
  return (
    <Field name="Categories" note="An event takes the colour of the first category whose pattern finds its title, unless it wears a pigment of its own. Patterns are regular expressions, without regard to case: “office hours|drop.?in”.">
      {draft.categories.map((c, i) => (
        <div key={i} className="fr-row" style={{ display: "grid", gridTemplateColumns: "minmax(0,0.8fr) minmax(0,1.2fr) auto auto", gap: 8, alignItems: "center", padding: "8px 0" }}>
          <input className="input" value={c.name} onChange={(e) => set(i, { name: e.target.value })} aria-label="Category name" style={{ minHeight: 0, padding: "4px 8px", fontSize: 13 }} />
          <input className="input fr-mono" value={c.pattern} onChange={(e) => set(i, { pattern: e.target.value })} aria-label={`${c.name} pattern`} style={{ minHeight: 0, padding: "4px 8px", fontSize: 12, boxShadow: broken(c.pattern) ? "0 0 0 1px var(--fr-due)" : undefined }} />
          <PigmentMenu value={c.color} onPick={(id) => id && set(i, { color: id })} />
          <span style={{ display: "flex" }}>
            <button className="btn btn-icon btn-ghost" onClick={() => move(i, -1)} disabled={i === 0} aria-label="Earlier" style={{ width: 26, height: 26 }}>
              <Icon name="arrow-up" size={13} />
            </button>
            <button className="btn btn-icon btn-ghost" onClick={() => move(i, 1)} disabled={i === draft.categories.length - 1} aria-label="Later" style={{ width: 26, height: 26 }}>
              <Icon name="arrow-down" size={13} />
            </button>
            <button className="btn btn-icon btn-ghost" onClick={() => setDraft({ ...draft, categories: draft.categories.filter((_, j) => j !== i) })} aria-label={`Delete ${c.name}`} style={{ width: 26, height: 26, color: "var(--fr-due)" }}>
              <Icon name="trash" size={13} />
            </button>
          </span>
        </div>
      ))}
      <button className="btn btn-secondary" onClick={() => setDraft({ ...draft, categories: [...draft.categories, { name: "New category", slug: "", color: "graphite", pattern: "" }] })} style={{ alignSelf: "flex-start" }}>
        <Icon name="plus" />
        Add a category
      </button>
      <div style={{ display: "flex", flexDirection: "column", gap: 8, paddingTop: 8 }}>
        <span className="fr-eyebrow">Filter</span>
        {draft.filter ? (
          <div style={{ display: "grid", gridTemplateColumns: "minmax(0,0.8fr) minmax(0,1.2fr) auto", gap: 8, alignItems: "center" }}>
            <input className="input" value={draft.filter.label} onChange={(e) => setDraft({ ...draft, filter: { ...draft.filter!, label: e.target.value } })} aria-label="Filter label" style={{ minHeight: 0, padding: "4px 8px", fontSize: 13 }} />
            <input className="input fr-mono" value={draft.filter.pattern} onChange={(e) => setDraft({ ...draft, filter: { ...draft.filter!, pattern: e.target.value } })} aria-label="Filter pattern" style={{ minHeight: 0, padding: "4px 8px", fontSize: 12 }} />
            <button className="btn btn-ghost" onClick={() => setDraft({ ...draft, filter: null })} style={{ color: "var(--fr-due)" }}>
              Remove
            </button>
            <span className="fr-kicker" style={{ gridColumn: "1 / -1" }}>
              Never hides:{" "}
              {draft.categories.filter((c) => c.slug).map((c) => (
                <label key={`${c.slug}-${c.name}`} style={{ marginRight: 10, whiteSpace: "nowrap" }}>
                  <input type="checkbox" checked={draft.filter!.except_.includes(c.slug)} onChange={(e) => setDraft({ ...draft, filter: { ...draft.filter!, except_: e.target.checked ? [...draft.filter!.except_, c.slug] : draft.filter!.except_.filter((s) => s !== c.slug) } })} /> {c.name}
                </label>
              ))}
            </span>
          </div>
        ) : (
          <button className="btn btn-secondary" onClick={() => setDraft({ ...draft, filter: { label: "Office hours", pattern: "office hours|drop.?in", except_: [] } })} style={{ alignSelf: "flex-start" }}>
            Add a filter
          </button>
        )}
      </div>
      {changed && (
        <span style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-primary" onClick={() => onSave(draft)} disabled={!valid}>
            Save categories
          </button>
          <button className="btn btn-secondary" onClick={() => setDraft(value)}>
            Undo changes
          </button>
        </span>
      )}
    </Field>
  )
}
