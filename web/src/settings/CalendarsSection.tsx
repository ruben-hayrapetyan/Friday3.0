// Calendars (COMBINED.md 17, 19, 28, 59, 60): what counts as busy when Friday plans, the time kept free around
// events (to get there and back), each calendar's pigment and its
// button in the title row (under its Google account's address when there are several), and the categories that colour
// events by their titles, with the filter that hides the ones you'd rather not see (office hours).

import { Fragment, useEffect, useState } from "react"
import { Chip, Icon, Menu, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useSettings } from "@/hooks/queries"
import { whose } from "@/lib/aiName"
import { mergeTargets } from "@/lib/categories"
import { newEventTargets } from "@/lib/calendars"
import { PIGMENTS, pigment } from "@/lib/pigments"
import { useLook } from "@/theme/LookProvider"
import { CalendarChoice, saying } from "./calendarChoice"
import { useAi } from "./AiConnect"
import { Calendars, useCalendars, useMacCalendars } from "./Calendars"
import { accountName, useGoogleAccess } from "./GoogleConnect"
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

interface Gap {
  before_min: number
  after_min: number
}

const ROOMS = /\b(rooms?|bookings?|reservations?)\b/i
const KINDS = [
  ["class", "Classes"],
  ["meeting", "Meetings"],
  ["exam", "Exams"],
  ["other", "Everything else"],
] as const
const GAPS = [0, 5, 10, 15, 20, 30, 45, 60]
const gapLabel = (m: number) => (m ? `${m} min` : "None")

/** Time kept free of work before and after events, to get there and away: the same for all, or kind by kind. */
function AroundEvents({ kinds, onSave }: { kinds: Record<string, Gap>; onSave: (value: Record<string, Gap>) => void }) {
  const all = KINDS.map(([k]) => kinds[k] ?? { before_min: 0, after_min: 0 })
  const same = all.every((g) => g.before_min === all[0].before_min && g.after_min === all[0].after_min && g.before_min === g.after_min) ? all[0].before_min : null
  const set = (kind: string, side: keyof Gap, minutes: number) => onSave({ [kind]: { ...(kinds[kind] ?? { before_min: 0, after_min: 0 }), [side]: minutes } })
  const options = GAPS.map((m) => ({ value: String(m), label: gapLabel(m) }))
  return (
    <Field name="Time around events" note="Kept free of work before and after your events, to get there and to get back to where you work.">
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
        <span style={{ fontSize: 12, color: "var(--color-neutral-400)", marginRight: 4 }}>Before and after every event</span>
        {[0, 10, 15, 30].map((m) => (
          <Chip key={m} on={same === m} onClick={() => onSave(Object.fromEntries(KINDS.map(([k]) => [k, { before_min: m, after_min: m }])))}>
            {gapLabel(m)}
          </Chip>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto auto", gap: "6px 12px", alignItems: "center", maxWidth: 420, paddingTop: 4 }}>
        <span />
        <span className="fr-kicker">Before</span>
        <span className="fr-kicker">After</span>
        {KINDS.map(([k, name], i) => (
          <Fragment key={k}>
            <span style={{ fontSize: 13 }}>{name}</span>
            <Menu options={options} value={String(all[i].before_min)} onPick={(v) => set(k, "before_min", Number(v))} label={`Before ${name.toLowerCase()}`} />
            <Menu options={options} value={String(all[i].after_min)} onPick={(v) => set(k, "after_min", Number(v))} label={`After ${name.toLowerCase()}`} />
          </Fragment>
        ))}
      </div>
    </Field>
  )
}

/** Whether a calendar's events block time: as you said, else all but calendars of room bookings (as the server). */
export const counts = (name: string, busy: Busy) => busy.calendars[name] ?? !ROOMS.test(name)

export function CalendarsSection() {
  const settings = useSettings().data as Record<string, unknown> | undefined
  const save = useCommand("settings_set", { label: () => "Saved" })
  const toCalendar = useCommand("events_to_calendar", { label: (o) => o.result.message ?? "Done" })
  // Every calendar a new event can go to: Google's and the Mac's, each once, the way Friday reads it (lib/calendars.ts).
  const targets = newEventTargets(useCalendars().data ?? [], useMacCalendars().data ?? [])
  const google = (useCalendars().data ?? []).filter((c) => c.on)
  const mac = (useMacCalendars().data ?? []).filter((c) => c.on && !google.some((g) => g.name === c.name))
  const reading = [...google, ...mac] // what the plan shows, by name
  const accounts = (useGoogleAccess()?.accounts ?? []).map((a) => a.email)
  const several = accounts.length > 1
  const lost = (c: (typeof google)[number]) => !accounts.includes(c.account ?? "") // listed before its account was known
  const of = (account: string) => google.filter((c) => (c.account ?? "") === account || (account === accounts[0] && lost(c)))
  const groups: [string | null, typeof reading][] = several ? [...accounts.map((a): [string, typeof reading] => [accountName(a), of(a)]), ["On this Mac", mac]] : [[null, reading]]
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
      <AroundEvents kinds={settings.event_kinds as Record<string, Gap>} onSave={(value) => save({ key: "event_kinds", value })} />
      <Field name="Your calendars" note="For each: plan around its events, just show them (dashed, and work may go over them), or hide it until you switch it on under Show (⌥⌘1–9). And a pigment. Calendars of room bookings start out just shown.">
        {reading.length === 0 ? (
          <span className="fr-kicker">Calendars list here once Google is connected (Integrations), and the Mac app's once it runs.</span>
        ) : (
          groups.map(([label, list]) => (
            <Fragment key={label ?? "all"}>
              {label !== null && list.length > 0 && (
                <span className="fr-kicker" style={{ padding: "10px 0 2px", fontWeight: 500, color: "var(--color-neutral-300)", overflowWrap: "anywhere" }}>
                  {label}
                </span>
              )}
              {list.map((c) => {
                const shown = !look.toolbar.includes(c.name)
                const busyNow = counts(c.name, busy)
                const pick = (to: { shown: boolean; busy: boolean }) => {
                  if (to.shown !== shown) setLook({ toolbar: to.shown ? look.toolbar.filter((n) => n !== c.name) : [...look.toolbar, c.name] })
                  if (to.busy !== busyNow) setBusy({ calendars: { ...busy.calendars, [c.name]: to.busy } })
                }
                return (
                  <div key={c.id} className="fr-row" style={{ display: "flex", flexWrap: "wrap", gap: "8px 14px", alignItems: "center", padding: "8px 0" }}>
                    <span style={{ flex: "1 1 180px", display: "flex", flexDirection: "column", minWidth: 0 }}>
                      <span style={{ display: "flex", gap: 8, alignItems: "center", minWidth: 0 }}>
                        <span style={{ width: 10, height: 10, borderRadius: "50%", flex: "none", background: swatchOf(look.colors[c.name]) }} />
                        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.name}</span>
                      </span>
                      <span className="fr-kicker">
                        {saying(shown, busyNow)}
                        {!shown && (
                          // Hidden and still kept clear: rare, so a link rather than a third switch.
                          <button className="fr-plain fr-link" onClick={() => setBusy({ calendars: { ...busy.calendars, [c.name]: !busyNow } })} style={{ marginLeft: 6 }}>
                            {busyNow ? "Let work go over it" : "Keep work off it anyway"}
                          </button>
                        )}
                      </span>
                    </span>
                    <CalendarChoice name={c.name} shown={shown} busy={busyNow} onPick={pick} />
                    <PigmentMenu value={look.colors[c.name] ?? null} onPick={(color) => setLook({ colors: color ? { ...look.colors, [c.name]: color } : omit(look.colors, c.name) })} />
                  </div>
                )
              })}
            </Fragment>
          ))
        )}
      </Field>
      <Field name="This Mac’s calendars" note="Sent by the Mac app. Choose which Friday reads, and whether their events skip the Inbox. One you switch off leaves your calendar, its events and repeats coming back if you switch it on again.">
        <Calendars mac />
      </Field>
      <Field name="New events go to" note="Your default calendar: events you make in Friday are saved to it too, wear its colour, and follow it from then on. Each new event can choose another in its drawer. Kept only in Friday when none is chosen.">
        <select
          className="input"
          value={(settings.gcal as { new_events_to?: string | null }).new_events_to ?? ""}
          onChange={(e) => save({ key: "gcal", value: { ...(settings.gcal as object), new_events_to: e.target.value || null } })}
          style={{ alignSelf: "flex-start", width: 280 }}
          aria-label="New events go to"
        >
          <option value="">Only Friday</option>
          {targets.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
              {t.account && t.account !== t.name ? ` · ${t.via === "mac" ? `${t.account}, through this Mac` : accountName(t.account)}` : t.via === "mac" ? " · through this Mac" : ""}
            </option>
          ))}
        </select>
        {(settings.gcal as { new_events_to?: string | null }).new_events_to && (
          // Events made before a calendar was chosen here, put on it (3 Nov: `events_to_calendar` had no button)
          <button className="btn btn-secondary" onClick={() => toCalendar({})} title="Events you made in Friday that are still to come and on no calendar yet; ones kept only in Friday and ones from a feed stay as they are" style={{ alignSelf: "flex-start" }}>
            <Icon name="calendar-plus" />
            Put Friday’s events on it
          </button>
        )}
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

/** The categories and the filter, saved together. A category's words are optional (31 Oct): an event no one's words
 * find is placed by what it shares with events you know, and Claude, and your choice on its card wins. */
function Categories({ value, onSave }: { value: CategorySettings; onSave: (value: CategorySettings) => void }) {
  const [draft, setDraft] = useState(value)
  // One category folded into another, its events and words going with it (3 Nov: `category_merge` had no button)
  const merge = useCommand("category_merge", { label: (o) => o.result.message ?? "Merged" })
  const ai = useAi().name
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
  const valid = draft.categories.every((c) => c.name.trim() && !broken(c.pattern)) && (!draft.filter || !broken(draft.filter.pattern))
  return (
    <Field
      name="Categories"
      note={`Friday puts each event in one: the one you chose on its card; else the first whose words are in its title; else ${whose(ai)} pick, given what the event shares with ones you know; else, when that's clear, the events most like it. Words are optional, for what's always that category, written as regular expressions without regard to case: “office hours|drop.?in”.`}
    >
      {draft.categories.map((c, i) => (
        <div key={i} className="fr-row" style={{ display: "grid", gridTemplateColumns: "minmax(0,0.8fr) minmax(0,1.2fr) auto auto", gap: 8, alignItems: "center", padding: "8px 0" }}>
          <input className="input" value={c.name} onChange={(e) => set(i, { name: e.target.value })} aria-label="Category name" style={{ minHeight: 0, padding: "4px 8px", fontSize: 13 }} />
          <input className="input fr-mono" value={c.pattern} onChange={(e) => set(i, { pattern: e.target.value })} placeholder="Always when its title has… (optional)" aria-label={`${c.name}: always when its title has`} style={{ minHeight: 0, padding: "4px 8px", fontSize: 12, boxShadow: broken(c.pattern) ? "0 0 0 1px var(--fr-due)" : undefined }} />
          <PigmentMenu value={c.color} onPick={(id) => id && set(i, { color: id })} />
          <span style={{ display: "flex", alignItems: "center" }}>
            {!changed && mergeTargets(value, c.name).length > 0 && (
              <Menu label={`Merge ${c.name} into`} value="" onPick={(into) => into && merge({ name: c.name, into })} options={[{ value: "", label: "Merge into…" }, ...mergeTargets(value, c.name).map((n) => ({ value: n, label: n }))]} />
            )}
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
