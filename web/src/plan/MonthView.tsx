// The month view (v22): weeks of day cells with the planned hours, a load bar, dues and the first few blocks. A
// click opens that day. Blocks exist only inside the planning horizon, so later days show fixed items and dues.

import { useDragging } from "@/components/calendar/useDrag"
import { useCalendar, usePlan, useSettings } from "@/hooks/queries"
import { clock } from "@/lib/format"
import { addDays, toMin } from "@/lib/time"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"

const DOWS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
const SHOWN = 3

export function monthStart(date: string): string {
  return `${date.slice(0, 8)}01`
}

export function MonthView({ first, onDay }: { first: string; onDay: (date: string) => void }) {
  const { today } = useShell()
  const { skinOf } = useLook()
  const { drag } = useDragging()
  const settings = useSettings().data as Record<string, { week_start?: string }> | undefined
  const weekStart = settings?.time?.week_start ?? "mon"
  const offset = DOWS.findIndex((d) => d.toLowerCase() === weekStart)
  const dow = (new Date(toMin(first) * 60000).getUTCDay() + 6) % 7 // Monday is 0
  const gridStart = addDays(first, -((dow - offset + 7) % 7))
  const days = Array.from({ length: 42 }, (_, i) => addDays(gridStart, i))
  const calendar = useCalendar(gridStart, 42).data
  const plan = usePlan(`${gridStart}T00:00`, `${addDays(gridStart, 42)}T00:00`).data
  const caps = new Map(calendar?.days.map((d) => [d.date, d.cap_hours]))
  const month = first.slice(0, 7)
  const weeks = days.filter((_, i) => i % 7 === 0).filter((d, w) => w < 5 || addDays(d, 0).slice(0, 7) === month)
  const dows = [...DOWS.slice(offset), ...DOWS.slice(0, offset)]
  return (
    <div className="fr-panel" style={{ overflowY: "auto", display: "grid", gridTemplateRows: `auto repeat(${weeks.length}, minmax(132px, 1fr))`, paddingBottom: 116 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, minmax(0,1fr))" }}>
        {dows.map((d) => (
          <div key={d} style={{ padding: "10px 12px 8px", fontSize: 12, color: "var(--color-neutral-500)" }}>
            {d}
          </div>
        ))}
      </div>
      {weeks.map((start) => (
        <div key={start} className="fr-row" style={{ display: "grid", gridTemplateColumns: "repeat(7, minmax(0,1fr))" }}>
          {Array.from({ length: 7 }, (_, i) => addDays(start, i)).map((date) => {
            const hrs = plan?.day_hours[date] ?? 0
            const cap = caps.get(date) ?? 8
            const items = [
              ...(plan?.blocks ?? []).filter((b) => b.start.startsWith(date)).map((b) => ({ key: b.key, start: b.start, title: b.title, s: skinOf(b.pinned === "locked" ? "locked" : "planned", b.area) })),
              ...(plan?.fixed ?? []).filter((f) => f.start?.startsWith(date)).map((f) => ({ key: `F${f.id}`, start: f.start as string, title: f.title, s: skinOf("fixed", f.area) })),
            ].sort((a, b) => a.start.localeCompare(b.start))
            const dues = (calendar?.dues ?? []).filter((d) => d.due.startsWith(date))
            const inMonth = date.slice(0, 7) === month
            const isToday = date === today
            return (
              <div
                key={date}
                data-drop-day={date}
                className="fr-hover-accent"
                onClick={() => onDay(date)}
                style={{
                  outline: drag?.moved && drag.over === "day" && drag.day === date ? "2px solid var(--color-accent)" : undefined,
                  outlineOffset: -2,
                  padding: "8px 8px 10px",
                  display: "flex",
                  flexDirection: "column",
                  gap: 4,
                  minWidth: 0,
                  boxShadow: "inset 1px 0 0 color-mix(in srgb, var(--color-text) 7%, transparent)",
                  opacity: inMonth ? 1 : 0.45,
                  cursor: "pointer",
                }}
              >
                <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 6 }}>
                  <span
                    className="fr-h tnum"
                    style={{
                      fontSize: 22,
                      lineHeight: 1,
                      color: isToday ? "var(--color-accent-200)" : date < today ? "var(--color-neutral-500)" : undefined,
                      textShadow: isToday ? "0 0 calc(18px * var(--g-today)) var(--color-accent)" : undefined,
                    }}
                  >
                    {Number(date.slice(8, 10))}
                  </span>
                  {hrs > 0 && (
                    <span className="tnum" style={{ fontSize: 11, color: "var(--color-neutral-500)" }}>
                      {hrs.toFixed(1)} h
                    </span>
                  )}
                </div>
                <div style={{ height: 2, borderRadius: 1, background: "color-mix(in srgb, var(--color-text) 8%, transparent)" }}>
                  <div style={{ height: "100%", width: `${Math.min(100, (hrs / cap) * 100)}%`, borderRadius: 1, background: hrs > cap ? "var(--fr-warn)" : "var(--color-neutral-400)" }} />
                </div>
                {dues.map((d) => (
                  <span key={d.item_id} className="fr-tag due" style={{ alignSelf: "flex-start" }}>
                    <i className="ph ph-flag" style={{ fontSize: 11 }} />
                    {d.title}
                  </span>
                ))}
                {items.slice(0, SHOWN).map((it) => (
                  <div
                    key={it.key}
                    style={{ position: "relative", display: "flex", alignItems: "center", gap: 6, padding: "2px 6px 2px 8px", borderRadius: 4, background: it.s.bg, border: it.s.bd, color: it.s.fg, fontSize: 12, whiteSpace: "nowrap", overflow: "hidden" }}
                  >
                    <span style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 3, background: it.s.stripe }} />
                    <span className="tnum" style={{ color: it.s.sub, fontSize: 11 }}>
                      {clock(it.start)}
                    </span>
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{it.title}</span>
                  </div>
                ))}
                {items.length > SHOWN && <span style={{ fontSize: 11, color: "var(--color-neutral-500)", paddingLeft: 2 }}>{items.length - SHOWN} more</span>}
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}
