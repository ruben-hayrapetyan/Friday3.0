// The sidebar's mini month (personal's, COMBINED.md 10): each day tinted by how full it is, today underlined, the
// agenda's day filled. A click shows that day in the calendar and the agenda; a task dropped on a day is due then. It
// follows the calendar: moved to another week or month, it shows that month (the audit, 12 Nov: it stayed where it
// opened); its own arrows look around until the calendar moves again.

import { useShownPlan } from "@/plan/shown"
import { useState } from "react"
import { useNavigate } from "react-router"
import { useDragging } from "@/components/calendar/useDrag"
import { Icon } from "@/components/fr/controls"
import { useCalendar, useSettings } from "@/hooks/queries"
import { addDays, toMin } from "@/lib/time"
import { monthStart } from "@/plan/MonthView"
import { type CalendarPlace, useShell } from "./ShellContext"

const DOWS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

/** The month the calendar is in: the one the month view shows, or the one holding the day a day, three days or a week
 * are centred on (today, when it's on today). */
export function followedMonth(place: CalendarPlace, today: string): string {
  return monthStart(place.first ?? today)
}

export function MiniMonth() {
  const { today, place, setPlace, agendaDay, setAgendaDay } = useShell()
  const navigate = useNavigate()
  const { drag } = useDragging()
  const follows = followedMonth(place, today)
  const [month, setMonth] = useState(follows)
  // Any move of the calendar brings the mini month back to it, even within the month it's in; set while drawing, not
  // in an effect, so it never shows a frame behind the calendar.
  const moved = `${place.view}/${place.first}/${follows}`
  const [followed, setFollowed] = useState(moved)
  if (followed !== moved) {
    setFollowed(moved)
    setMonth(follows)
  }
  const settings = useSettings().data as Record<string, { week_start?: string }> | undefined
  const offset = Math.max(0, DOWS.findIndex((d) => d.toLowerCase() === (settings?.time?.week_start ?? "mon")))
  const dow = (new Date(toMin(month) * 60000).getUTCDay() + 6) % 7
  const gridStart = addDays(month, -((dow - offset + 7) % 7))
  const days = Array.from({ length: 42 }, (_, i) => addDays(gridStart, i))
  const calendar = useCalendar(gridStart, 42).data
  const plan = useShownPlan(`${gridStart}T00:00`, `${addDays(gridStart, 42)}T00:00`).data
  const fullness = (date: string) => {
    const cap = calendar?.days.find((d) => d.date === date)?.cap_hours ?? 8
    const fixed = (plan?.fixed ?? [])
      .filter((f) => f.start?.startsWith(date) && f.end && !(f.start.endsWith("T00:00") && f.end.endsWith("T00:00")))
      .reduce((sum, f) => sum + (toMin(f.end as string) - toMin(f.start as string)) / 60, 0)
    return Math.min(1, ((plan?.day_hours[date] ?? 0) + fixed) / Math.max(cap + 4, 1))
  }
  const shown = agendaDay ?? today
  const open = (date: string) => {
    setAgendaDay(date)
    setPlace({ view: place.view, first: place.view === "month" ? monthStart(date) : date })
    navigate("/")
  }
  const step = (by: number) => {
    const y = Number(month.slice(0, 4))
    const m = Number(month.slice(5, 7)) - 1 + by
    setMonth(new Date(Date.UTC(y, m, 1)).toISOString().slice(0, 10))
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, padding: "0 4px" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 4px" }}>
        <span className="fr-h" style={{ fontSize: 15 }}>
          {MONTHS[Number(month.slice(5, 7)) - 1]} <span style={{ color: "var(--color-neutral-500)" }}>{month.slice(0, 4)}</span>
        </span>
        <span style={{ display: "flex" }}>
          <button className="btn btn-icon btn-ghost" onClick={() => step(-1)} aria-label="Previous month" style={{ width: 22, height: 22, color: "var(--color-neutral-400)" }}>
            <Icon name="caret-left" size={13} />
          </button>
          <button className="btn btn-icon btn-ghost" onClick={() => step(1)} aria-label="Next month" style={{ width: 22, height: 22, color: "var(--color-neutral-400)" }}>
            <Icon name="caret-right" size={13} />
          </button>
        </span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, minmax(0,1fr))", gap: 1 }}>
        {[...DOWS.slice(offset), ...DOWS.slice(0, offset)].map((d) => (
          <span key={d} className="fr-eyebrow" style={{ textAlign: "center", fontSize: 11, letterSpacing: "0.08em", padding: "2px 0" }}>
            {d.slice(0, 1)}
          </span>
        ))}
        {days.map((date) => {
          const inMonth = date.slice(0, 7) === month.slice(0, 7)
          const isShown = date === shown
          const isToday = date === today
          const target = !!drag?.moved && drag.over === "day" && drag.day === date
          const full = fullness(date)
          return (
            <button
              key={date}
              data-drop-day={date}
              onClick={() => open(date)}
              className="fr-plain tnum"
              aria-label={date}
              aria-current={isToday ? "date" : undefined}
              style={{
                height: 26,
                borderRadius: "var(--radius-sm)",
                textAlign: "center",
                fontSize: 11.5,
                color: isShown ? "var(--fr-ink)" : inMonth ? "var(--color-text)" : "var(--color-neutral-500)",
                background: isShown
                  ? "var(--color-accent)"
                  : full > 0.02
                    ? `color-mix(in srgb, var(--color-text) ${Math.round(3 + 15 * full)}%, transparent)`
                    : undefined,
                boxShadow: target ? "inset 0 0 0 2px var(--color-accent)" : undefined,
                textDecoration: isToday ? "underline" : undefined,
                textDecorationColor: "var(--fr-now)",
                textDecorationThickness: 2,
                textUnderlineOffset: 3,
                fontWeight: isToday ? 600 : 400,
              }}
            >
              {Number(date.slice(8, 10))}
            </button>
          )
        })}
      </div>
    </div>
  )
}
