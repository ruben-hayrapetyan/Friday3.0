// An event in the drawer (personal's inspector and new-event form, COMBINED.md 12): title, all day, date and times,
// a repeat for a new one, its pigment and notes. The dashed block on the grid is the same draft, so changing the
// times here moves it there. Return in the title saves; Escape closes.

import { useEffect, useRef, useState } from "react"
import type { Item } from "@/api/client"
import { Icon, Menu, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { clock, weekday } from "@/lib/format"
import { PIGMENTS, pigment, UNMARKED } from "@/lib/pigments"
import { addDays, fromMin, toMin } from "@/lib/time"
import { useLook } from "@/theme/LookProvider"
import { type EventDraft, useShell } from "./ShellContext"

const REPEATS = [
  { value: "", label: "Doesn't repeat" },
  { value: "rrule:FREQ=DAILY", label: "Every day" },
  { value: "rrule:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", label: "Every weekday" },
  { value: "rrule:FREQ=WEEKLY", label: "Every week" },
  { value: "rrule:FREQ=WEEKLY;INTERVAL=2", label: "Every other week" },
  { value: "rrule:FREQ=MONTHLY", label: "Every month" },
] as const

/** A new event's draft: an hour from the quarter hour it was asked for. */
export function draftAt(start: string, end?: string): EventDraft {
  return { id: null, title: "", start, end: end ?? fromMin(toMin(start) + 60), allDay: false, color: null, notes: "", every: null, seriesId: null, calendar: null, savesToCalendar: false }
}

/** An event to edit, as the drawer holds it. */
export function draftOf(
  item: Pick<Item, "id" | "title" | "start" | "end" | "series_id" | "color" | "notes" | "calendar" | "saves_to_calendar" | "chroma_color" | "category" | "category_color" | "calendar_color">,
): EventDraft {
  const start = item.start ?? ""
  const end = item.end ?? start
  const allDay = start.endsWith("T00:00") && end.endsWith("T00:00") && end > start
  return {
    id: item.id,
    title: item.title,
    start,
    end,
    allDay,
    color: item.color ?? null,
    notes: item.notes ?? "",
    every: null,
    seriesId: item.series_id ?? null,
    calendar: item.calendar ?? null,
    savesToCalendar: item.saves_to_calendar ?? false,
    auto: item.chroma_color
      ? { color: item.chroma_color, from: "as in Chroma" }
      : item.category_color
        ? { color: item.category_color, from: item.category ?? "its category" }
        : item.calendar_color
          ? { color: item.calendar_color, from: item.calendar ?? "its calendar" }
          : { color: null, from: "no category matches" },
  }
}

export function EventPane({ draft }: { draft: EventDraft }) {
  const { setEvent } = useShell()
  const { light } = useLook()
  const add = useCommand("add", { label: () => `Added ${draft.title || "the event"}` })
  const edit = useCommand("edit", { label: () => `Saved ${draft.title}` })
  const drop = useCommand("drop", { label: () => `Deleted ${draft.title}` })
  const skip = useCommand("skip", { label: () => "Deleted this one" })
  const deleteSeries = useCommand("series_delete", { label: (o) => o.result.message ?? "Deleted" })
  const [asking, setAsking] = useState(false)
  const title = useRef<HTMLInputElement>(null)
  const set = (change: Partial<EventDraft>) => setEvent({ ...draft, ...change })
  const isNew = draft.id === null
  useEffect(() => {
    if (isNew) title.current?.focus()
  }, [isNew])
  useEffect(() => setAsking(false), [draft.id])
  const day = draft.start.slice(0, 10)
  const lastDay = draft.allDay ? addDays(draft.end.slice(0, 10), -1) : day
  const autoName = draft.auto?.color ? `${PIGMENTS.find((p) => p.id === draft.auto?.color)?.name ?? draft.auto.color}, ${draft.auto.from}` : `Unmarked, ${draft.auto?.from ?? "no category matches"}`
  const valid = draft.title.trim() !== "" && (draft.allDay ? lastDay >= day : toMin(draft.end) > toMin(draft.start))
  const close = () => setEvent(null)
  const save = async () => {
    if (!valid) return
    const fields = { title: draft.title.trim(), start: draft.start, end: draft.end, color: draft.color, notes: draft.notes, blocks_time: !draft.allDay }
    const done = isNew
      ? await add({ ...fields, when: "fixed", ...(draft.every ? { every: draft.every } : {}) })
      : await edit({ id: draft.id as number, ...fields })
    if (done) close()
  }
  const remove = async (how: "one" | "all") => {
    if (draft.id === null) return
    const done = how === "all" && draft.seriesId !== null ? await deleteSeries({ id: draft.seriesId }) : draft.seriesId !== null ? await skip({ id: draft.id }) : await drop({ id: draft.id })
    if (done) close()
  }
  // Times are kept as local wall time; moving the date keeps the times, moving the start keeps the length.
  const setDay = (next: string) => {
    if (!next) return
    const length = toMin(draft.end) - toMin(draft.start)
    const start = `${next}T${draft.start.slice(11, 16)}`
    set({ start, end: fromMin(toMin(start) + length) })
  }
  const setStart = (time: string) => {
    if (!time) return
    const length = toMin(draft.end) - toMin(draft.start)
    const start = `${day}T${time}`
    set({ start, end: fromMin(toMin(start) + length) })
  }
  const setEnd = (time: string) => {
    if (!time) return
    let end = `${day}T${time}`
    if (toMin(end) <= toMin(draft.start)) end = `${addDays(day, 1)}T${time}` // past midnight
    set({ end })
  }
  const setAllDay = (on: boolean) =>
    on
      ? set({ allDay: true, start: `${day}T00:00`, end: `${addDays(day, 1)}T00:00` })
      : set({ allDay: false, start: `${day}T09:00`, end: `${day}T10:00` })
  return (
    <div
      onKeyDown={(e) => {
        if (e.key === "Escape") (e.stopPropagation(), close())
        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) save()
      }}
      style={{ display: "flex", flexDirection: "column", gap: 14, minHeight: 0, overflowY: "auto", overflowX: "hidden", paddingBottom: 24 }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, height: 32 }}>
        <span className="fr-h" style={{ fontSize: 20, lineHeight: 1, flex: 1 }}>
          {isNew ? "New event" : "Event"}
        </span>
        <button className="btn btn-icon btn-ghost" onClick={close} aria-label="Close" style={{ width: 28, height: 28, color: "var(--color-neutral-400)" }}>
          <Icon name="x" />
        </button>
      </div>
      {draft.calendar && (
        <span className="fr-kicker" style={{ display: "flex", gap: 6, alignItems: "center", marginTop: -6 }}>
          <Icon name={draft.savesToCalendar ? "cloud-check" : "lock-simple"} size={13} />
          {draft.savesToCalendar ? `From ${draft.calendar}; changes are saved there too.` : `From ${draft.calendar}, which Friday doesn't change: edits stay here until the calendar changes it.`}
        </span>
      )}
      <input
        ref={title}
        className="input"
        value={draft.title}
        onChange={(e) => set({ title: e.target.value })}
        onKeyDown={(e) => e.key === "Enter" && !e.metaKey && save()}
        placeholder="Title"
        aria-label="Title"
        style={{ fontSize: 16, fontWeight: 500 }}
      />
      <Row label="All day">
        <Switch on={draft.allDay} onToggle={() => setAllDay(!draft.allDay)} label="All day" />
      </Row>
      <Row label={draft.allDay ? "From" : "Day"}>
        <input className="input tnum" type="date" value={day} onChange={(e) => setDay(e.target.value)} aria-label="Day" style={field} />
      </Row>
      {draft.allDay ? (
        <Row label="To">
          <input
            className="input tnum"
            type="date"
            value={lastDay}
            min={day}
            onChange={(e) => e.target.value && set({ end: `${addDays(e.target.value, 1)}T00:00` })}
            aria-label="Last day"
            style={field}
          />
        </Row>
      ) : (
        <Row label="Time">
          <span style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", minWidth: 0 }}>
            <input className="input tnum" type="time" step={300} value={draft.start.slice(11, 16)} onChange={(e) => setStart(e.target.value)} aria-label="Starts" style={field} />
            <span style={{ color: "var(--color-neutral-500)" }}>–</span>
            <input className="input tnum" type="time" step={300} value={draft.end.slice(11, 16)} onChange={(e) => setEnd(e.target.value)} aria-label="Ends" style={field} />
          </span>
        </Row>
      )}
      <span className="tnum fr-kicker" style={{ marginTop: -6 }}>
        {summary(draft)}
      </span>
      {isNew ? (
        <Row label="Repeats">
          <Menu options={REPEATS} value={(draft.every ?? "") as (typeof REPEATS)[number]["value"]} onPick={(v) => set({ every: v || null })} label="Repeats" />
        </Row>
      ) : (
        draft.seriesId !== null && (
          <span style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, color: "var(--color-neutral-400)" }}>
            <Icon name="repeat" size={13} />
            Repeats. Changes here are to this time only.
          </span>
        )
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <span className="fr-eyebrow">Colour</span>
        {/* Chroma's picker: rounded squares that wrap, Automatic first, the choice named underneath. */}
        <div role="radiogroup" aria-label="Colour" style={{ display: "grid", gridTemplateColumns: "repeat(6, 24px)", gap: 8, padding: 3 }}>
          <button
            className="fr-plain"
            role="radio"
            onClick={() => set({ color: null })}
            title={`Automatic: ${autoName}`}
            aria-label="Automatic"
            aria-checked={draft.color === null}
            style={{ ...swatch, background: pigment(draft.auto?.color, light) ?? UNMARKED, boxShadow: ring(draft.color === null), display: "grid", placeItems: "center" }}
          >
            <span style={{ fontSize: 10, fontWeight: 700, color: "#fff", lineHeight: 1 }}>A</span>
          </button>
          {PIGMENTS.map((p) => (
            <button key={p.id} className="fr-plain" role="radio" onClick={() => set({ color: p.id })} title={p.name} aria-label={p.name} aria-checked={draft.color === p.id} style={{ ...swatch, background: pigment(p.id, light) ?? undefined, boxShadow: ring(draft.color === p.id) }} />
          ))}
        </div>
        <span className="fr-kicker">{draft.color ? (PIGMENTS.find((p) => p.id === draft.color)?.name ?? draft.color) : `Automatic: ${autoName}`}</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <span className="fr-eyebrow">Notes</span>
        <textarea className="input" value={draft.notes} onChange={(e) => set({ notes: e.target.value })} aria-label="Notes" style={{ minHeight: 70, fontSize: 13 }} />
      </div>
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
        <button className="btn btn-primary" onClick={save} disabled={!valid}>
          <Icon name="check" />
          {isNew ? "Add" : "Save"}
        </button>
        <button className="btn btn-secondary" onClick={close}>
          Cancel
        </button>
        {!isNew &&
          (asking ? (
            <span style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
              <button className="btn btn-ghost" onClick={() => remove("one")}>
                Just this one
              </button>
              <button className="btn btn-ghost" onClick={() => remove("all")} style={{ color: "var(--fr-due)" }}>
                Every one
              </button>
            </span>
          ) : (
            <button className="btn btn-ghost" onClick={() => (draft.seriesId !== null ? setAsking(true) : remove("one"))} style={{ marginLeft: "auto", color: "var(--fr-due)" }}>
              <Icon name="trash" />
              Delete
            </button>
          ))}
      </div>
      <span className="fr-kicker">⌘↩ saves · Esc closes</span>
    </div>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "64px minmax(0,1fr)", gap: 10, alignItems: "center" }}>
      <span className="fr-eyebrow">{label}</span>
      {children}
    </div>
  )
}

const field = { minHeight: 0, padding: "4px 6px", fontSize: 13, width: "auto", maxWidth: "100%" }
const swatch = { width: 24, height: 24, borderRadius: 4, flex: "none" } as const
const ring = (on: boolean) => (on ? "0 0 0 2px var(--color-surface), 0 0 0 3.5px color-mix(in srgb, var(--color-text) 75%, transparent)" : "none")

function summary(d: EventDraft): string {
  const day = d.start.slice(0, 10)
  const name = (date: string) => `${weekday(date)} ${Number(date.slice(8, 10))}`
  if (d.allDay) {
    const last = addDays(d.end.slice(0, 10), -1)
    return last === day ? `${name(day)}, all day` : `${name(day)} to ${name(last)}, all day`
  }
  const minutes = toMin(d.end) - toMin(d.start)
  const h = Math.floor(minutes / 60)
  const length = h && minutes % 60 ? `${h} h ${minutes % 60} min` : h ? `${h} h` : `${minutes} min`
  return `${name(day)}, ${clock(d.start)}–${clock(d.end)} · ${length}`
}
