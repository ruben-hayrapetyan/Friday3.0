// The sidebar's agenda (personal's, COMBINED.md 10): the chosen day's events, planned work and deadlines in one
// timeline by the clock, with today's red line between what's done and what's to come.

import type { Block, Item, Schemas } from "@/api/client"
import { useClock } from "@/hooks/useClock"
import { useCalendar, usePlan } from "@/hooks/queries"
import { clock, weekday } from "@/lib/format"
import { addDays, toMin } from "@/lib/time"
import { useLook } from "@/theme/LookProvider"
import { draftOf } from "./EventPane"
import { useShell } from "./ShellContext"

interface Entry {
  key: string
  start: string
  end: string | null
  title: string
  sort: "event" | "work" | "due" | "allday"
  area: string | null | undefined
  block: Block
  event?: Item // a calendar event, opened in the drawer
}

export function DayAgenda() {
  const { today, agendaDay, select, setEvent } = useShell()
  const { color } = useLook()
  const day = agendaDay ?? today
  const calendar = useCalendar(day, 1).data
  const plan = usePlan(`${day}T00:00`, `${addDays(day, 1)}T00:00`).data
  const now = useClock()
  const entries = agendaOf(day, plan, calendar)
  const nowAt = day === today ? entries.findIndex((e) => e.sort !== "allday" && toMin(e.end ?? e.start) > now) : -1
  const title = day === today ? "Today" : `${weekday(day)} ${Number(day.slice(8, 10))}`
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2, padding: "0 4px" }}>
      <span className="fr-eyebrow" style={{ padding: "0 4px 4px" }}>
        {title}
      </span>
      {!plan || !calendar ? null : entries.length === 0 ? (
        <span style={{ padding: "2px 4px", fontSize: 12, color: "var(--color-neutral-500)" }}>Nothing on this day.</span>
      ) : (
        entries.map((e, i) => (
          <div key={e.key} style={{ display: "contents" }}>
            {i === nowAt && <NowRule />}
            <button
              className="fr-plain fr-hover"
              onClick={() => (e.event ? setEvent(draftOf(e.event)) : select(e.block))}
              title={e.title}
              style={{ display: "grid", gridTemplateColumns: "42px 3px minmax(0,1fr)", gap: 7, alignItems: "center", padding: "3px 4px", borderRadius: "var(--radius-sm)" }}
            >
              <span className="tnum" style={{ fontSize: 11, color: "var(--color-neutral-500)", textAlign: "right" }}>
                {e.sort === "allday" ? "all day" : e.sort === "due" && e.start.endsWith("T23:59") ? "due" : clock(e.start)}
              </span>
              <span style={{ alignSelf: "stretch", borderRadius: 2, background: e.sort === "due" ? "var(--fr-due)" : e.sort === "work" ? color(e.area) : "var(--color-neutral-500)" }} />
              <span style={{ fontSize: 12.5, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", color: e.sort === "due" ? "var(--fr-due)" : undefined }}>
                {e.title}
              </span>
            </button>
          </div>
        ))
      )}
      {nowAt === entries.length && entries.length > 0 && <NowRule />}
    </div>
  )
}

function NowRule() {
  return <div role="separator" aria-label="Now" style={{ height: 2, margin: "2px 4px", borderRadius: 1, background: "var(--fr-now)" }} />
}

/** The day's events, planned work and deadlines, by the clock; all-day events first. */
export function agendaOf(day: string, plan: Schemas["PlanOut"] | undefined, calendar: Schemas["CalendarOut"] | undefined): Entry[] {
  const out: Entry[] = []
  for (const f of plan?.fixed ?? []) {
    if (!f.start || !f.end || f.event_kind === "shove") continue
    const allDay = f.start.endsWith("T00:00") && f.end.endsWith("T00:00") && f.end > f.start
    if (allDay ? !(f.start.slice(0, 10) <= day && day < f.end.slice(0, 10)) : !f.start.startsWith(day)) continue
    out.push({ key: `F${f.id}`, start: f.start, end: f.end, title: f.title, sort: allDay ? "allday" : "event", area: f.area, block: fixedBlock(f as Item & { start: string; end: string }), event: f })
  }
  for (const b of plan?.blocks ?? []) {
    if (b.start.startsWith(day)) out.push({ key: b.key, start: b.start, end: b.end, title: b.title, sort: "work", area: b.area, block: b })
  }
  for (const d of calendar?.dues ?? []) {
    if (d.due.startsWith(day)) {
      out.push({ key: `D${d.item_id}`, start: d.due, end: null, title: d.title, sort: "due", area: null, block: { key: `D${d.item_id}`, item_id: d.item_id, title: d.title, start: d.due, end: d.due } })
    }
  }
  const rank = (e: Entry) => (e.sort === "allday" ? "" : e.start)
  return out.sort((a, b) => rank(a).localeCompare(rank(b)) || a.title.localeCompare(b.title))
}

function fixedBlock(f: Item & { start: string; end: string }): Block {
  return { key: `F${f.id}`, item_id: f.id, title: f.title, area: f.area, start: f.start, end: f.end }
}
