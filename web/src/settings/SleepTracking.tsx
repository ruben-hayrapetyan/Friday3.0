// Track my sleep (Settings → Schedule): off until you turn it on. Your nights, logging one and what Friday learned are
// in Insights → Sleep; the Now bar also offers "I'm up", "Ready to work" and "Going to bed", one tap each. The night
// rows and their fixable times are shared with Insights.

import { useState } from "react"
import { useNavigate } from "react-router"
import type { Schemas } from "@/api/client"
import { Icon, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useSettings } from "@/hooks/queries"
import { clock, dayLabel, dur } from "@/lib/format"
import { Field } from "./SettingsPage"

const SCHOOL_NIGHTS = ["sun", "mon", "tue", "wed", "thu"]
const WEEKDAY_MORNINGS = ["mon", "tue", "wed", "thu", "fri"]
const SHORT: Record<string, string> = { mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun" }

/** "Sunday to Thursday nights", "weekday mornings", or the days named. */
export function daysSaid(days: string[], field: "bedtime" | "wake"): string {
  const same = (group: string[]) => group.length === days.length && group.every((d) => days.includes(d))
  if (field === "bedtime" && same(SCHOOL_NIGHTS)) return "Sunday to Thursday nights"
  if (field === "bedtime" && same(["fri", "sat"])) return "Friday and Saturday nights"
  if (field === "wake" && same(WEEKDAY_MORNINGS)) return "Weekday mornings"
  if (field === "wake" && same(["sat", "sun"])) return "Weekend mornings"
  return `${days.map((d) => SHORT[d]).join(", ")} ${field === "bedtime" ? "nights" : "mornings"}`
}

export function TrackSleep() {
  const settings = useSettings().data as Record<string, { on?: boolean }> | undefined
  const save = useCommand("settings_set", { label: () => "Saved" })
  const navigate = useNavigate()
  const on = !!settings?.sleep_tracking?.on
  return (
    <Field name="Track my sleep" note="Optional. Log your nights in Insights → Sleep (or tap in the Now bar); Friday learns your real bedtime, wake time and morning routine. Off, nothing is recorded or learned.">
      <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <Switch on={on} onToggle={() => save({ key: "sleep_tracking", value: { ...settings?.sleep_tracking, on: !on } })} label="Track my sleep" />
        <span style={{ color: on ? "var(--color-text)" : "var(--color-neutral-400)" }}>{on ? "On" : "Off"}</span>
      </span>
      {on && (
        <button className="fr-link" onClick={() => navigate("/insights")} style={{ alignSelf: "flex-start", fontSize: 12 }}>
          Your nights and what Friday learned are in Insights → Sleep
        </button>
      )}
    </Field>
  )
}

/** The last two weeks: each time can be put right, or taken back. */
export function Nights({ nights }: { nights: Schemas["SleepNightOut"][] }) {
  if (!nights.length) return null
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {nights.map((n) => (
        <div key={n.date} className="fr-row" style={{ display: "grid", gridTemplateColumns: "92px repeat(3, minmax(0,1fr)) 64px", gap: 8, alignItems: "center", padding: "6px 0", fontSize: 12 }}>
          <span style={{ color: "var(--color-neutral-400)" }}>{dayLabel(n.date)}</span>
          <TapTime label="Bed" at={n.bed} id={n.bed_id} />
          <TapTime label="Up" at={n.up} id={n.up_id} />
          <TapTime label="Ready" at={n.ready} id={n.ready_id} timed={n.ready_timed} />
          <span className="tnum" title={`You plan for ${dur(n.planned_min)}`} style={{ textAlign: "right", color: n.slept_min && n.slept_min < n.planned_min - 60 ? "var(--fr-warn)" : "var(--color-neutral-300)" }}>
            {n.slept_min ? dur(n.slept_min) : "—"}
          </span>
        </div>
      ))}
    </div>
  )
}

function TapTime({ label, at, id, timed }: { label: string; at?: string | null; id?: number | null; timed?: boolean }) {
  const edit = useCommand("sleep_mark_edit", { label: (o) => o.result.message ?? "Moved" })
  const remove = useCommand("sleep_mark_remove", { label: (o) => o.result.message ?? "Removed" })
  const [editing, setEditing] = useState(false)
  if (!at) return <span style={{ color: "var(--color-neutral-600)" }}>{label} —</span>
  if (editing && id) {
    return (
      <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
        <input
          type="time"
          autoFocus
          defaultValue={at.slice(11, 16)}
          aria-label={`${label} time`}
          className="input"
          onBlur={(e) => (e.target.value && e.target.value !== at.slice(11, 16) && edit({ id, at: `${at.slice(0, 11)}${e.target.value}` }), setEditing(false))}
          onKeyDown={(e) => (e.key === "Enter" ? e.currentTarget.blur() : e.key === "Escape" && setEditing(false))}
          style={{ width: 100, padding: "2px 6px", minHeight: 0, fontSize: 12 }}
        />
        <button className="btn btn-icon btn-ghost" onMouseDown={(e) => e.preventDefault()} onClick={() => (remove({ id }), setEditing(false))} aria-label={`Remove ${label.toLowerCase()}`} style={{ width: 22, height: 22 }}>
          <Icon name="trash" size={12} />
        </button>
      </span>
    )
  }
  return (
    <button className="fr-plain fr-hover-text tnum" disabled={!id} onClick={() => setEditing(true)} title={timed ? "The first timer you started" : id ? "Click to change" : undefined} style={{ textAlign: "left", color: "var(--color-neutral-300)" }}>
      {label} {clock(at)}
      {timed && <span style={{ color: "var(--color-neutral-500)" }}> (timer)</span>}
    </button>
  )
}
