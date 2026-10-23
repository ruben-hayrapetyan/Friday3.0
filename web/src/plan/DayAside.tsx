// The day view's side panel (v22): the day in numbers, its blocks in order, and what's due in the next three days.

import type { Schemas } from "@/api/client"
import { clock, dur, weekday, when } from "@/lib/format"
import { addDays, toMin } from "@/lib/time"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"

const FULL = { Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday", Thu: "Thursday", Fri: "Friday", Sat: "Saturday", Sun: "Sunday" } as Record<string, string>
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

export function DayAside({ date, calendar, plan }: { date: string; calendar: Schemas["CalendarOut"]; plan: Schemas["PlanOut"] }) {
  const { today, select } = useShell()
  const { color } = useLook()
  const blocks = plan.blocks.filter((b) => b.start.startsWith(date))
  const fixed = plan.fixed.filter((f) => f.start?.startsWith(date) && f.end)
  const day = calendar.days.find((d) => d.date === date)
  const hours = plan.day_hours[date] ?? 0
  const rows = [
    ...blocks.map((b) => ({ key: b.key, start: b.start, end: b.end, title: b.title, area: b.area, note: b.pinned === "locked" ? "Locked" : b.pinned ? "Pinned" : b.tentative ? "Could fit here" : "Planned", fixed: false, block: b })),
    ...fixed.map((f) => ({ key: `F${f.id}`, start: f.start as string, end: f.end as string, title: f.title, area: f.area, note: "Fixed time", fixed: true, block: null })),
  ].sort((a, b) => a.start.localeCompare(b.start))
  const free = day ? Math.max(0, day.cap_hours - hours) : 0
  const stats = [
    { k: "focused", v: `${hours.toFixed(1)} h` },
    { k: "blocks", v: String(rows.length) },
    { k: "room left", v: `${free.toFixed(1)} h` },
  ]
  const soon = calendar.dues.filter((d) => d.due >= date && d.due < addDays(date, 3)).sort((a, b) => a.due.localeCompare(b.due))
  const last = rows.at(-1)
  return (
    <aside
      style={{
        position: "absolute",
        right: 12,
        top: 60,
        bottom: 0,
        width: 340,
        zIndex: 5,
        display: "flex",
        flexDirection: "column",
        gap: 16,
        padding: "18px 18px 120px",
        overflowY: "auto",
        borderRadius: "var(--radius-lg) var(--radius-lg) 0 0",
        background: "var(--color-surface)",
        boxShadow: "0 0 0 1px color-mix(in srgb, var(--color-text) 6%, transparent)",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span className="fr-h" style={{ fontSize: 22 }}>
          {FULL[weekday(date)]} {Number(date.slice(8, 10))} {MONTHS[Number(date.slice(5, 7)) - 1]}
        </span>
        <span className="tnum" style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>
          {day ? `${hours.toFixed(1)} of ${day.cap_hours} h planned` : ""}
          {last ? `, last block ends ${clock(last.end)}` : ""}
        </span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: 8 }}>
        {stats.map((x) => (
          <div key={x.k} style={{ display: "flex", flexDirection: "column", gap: 2, padding: 10, borderRadius: "var(--radius-md)", background: "var(--color-bg)" }}>
            <span className="fr-h tnum" style={{ fontSize: 20 }}>
              {x.v}
            </span>
            <span style={{ fontSize: 11, color: "var(--color-neutral-500)" }}>{x.k}</span>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", flexDirection: "column" }}>
        <span className="fr-kicker" style={{ paddingBottom: 6 }}>
          In order
        </span>
        {rows.map((r) => {
          const past = toMin(r.end) <= toMin(calendar.now)
          return (
            <button
              key={r.key}
              className="fr-plain fr-row fr-hover-soft"
              onClick={() => r.block && select(r.block)}
              style={{ display: "grid", gridTemplateColumns: "44px 3px minmax(0,1fr)", gap: 10, alignItems: "center", padding: "8px 4px", opacity: past ? 0.55 : 1 }}
            >
              <span className="tnum" style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>
                {clock(r.start)}
              </span>
              <span style={{ alignSelf: "stretch", borderRadius: 2, background: r.fixed ? "var(--color-neutral-600)" : color(r.area) }} />
              <span style={{ display: "flex", flexDirection: "column", gap: 1, minWidth: 0 }}>
                <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", fontWeight: r.fixed ? 400 : 500 }}>{r.title}</span>
                <span style={{ fontSize: 11, color: "var(--color-neutral-500)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {dur(toMin(r.end) - toMin(r.start))}, {r.note}
                </span>
              </span>
            </button>
          )
        })}
        {!rows.length && <span style={{ color: "var(--color-neutral-500)", padding: "8px 4px" }}>Nothing planned.</span>}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <span className="fr-kicker">Due in the next 3 days</span>
        {soon.map((d) => (
          <div key={`${d.item_id}${d.due}`} style={{ display: "flex", justifyContent: "space-between", gap: 10, fontSize: 13 }}>
            <span>{d.title}</span>
            <span className="tnum" style={{ color: d.due.startsWith(date) ? "var(--fr-due)" : "var(--color-neutral-300)" }}>
              {when(d.due, today)}
            </span>
          </div>
        ))}
        {!soon.length && <span style={{ color: "var(--color-neutral-500)" }}>Nothing.</span>}
      </div>
    </aside>
  )
}
