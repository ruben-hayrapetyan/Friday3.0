// Track my sleep and Track my meals (Settings → Schedule, and Sleep & meals): each off until you turn it on. Logging
// a night or a meal, and putting one right, is in Sleep & meals, with what Friday learned from them; the Now
// bar offers the tap that fits the hour. The night rows and their fixable times are shared with Sleep & meals.

import { useState } from "react"
import { useNavigate } from "react-router"
import type { Schemas } from "@/api/client"
import { Icon, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useSettings } from "@/hooks/queries"
import { clock, dayLabel, dur } from "@/lib/format"
import { nearestAt } from "@/lib/time"
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

/** One of the two switches, as Settings → Schedule shows it, with the way to Sleep & meals when it's on. */
export function Tracking({ what }: { what: "sleep" | "meals" }) {
  const settings = useSettings().data as Record<string, { on?: boolean }> | undefined
  const save = useCommand("settings_set", { label: () => "Saved" })
  const navigate = useNavigate()
  const key = what === "sleep" ? "sleep_tracking" : "meal_tracking"
  const on = !!settings?.[key]?.on
  const name = what === "sleep" ? "Track my sleep" : "Track my meals"
  const note =
    what === "sleep"
      ? "Optional. Tap “Done with work”, “Going to bed” and “I’m up” in the Now bar (or log a night in Sleep & meals); Friday learns your real bedtime, wake time, morning routine and wind-down before bed. Off, nothing is recorded or learned."
      : "Optional. Tap “Eating now” and “Done eating” in the Now bar (or log a meal in Sleep & meals); Friday learns when you eat, for how long and what you skip, and keeps your meal free while you eat. Off, nothing is recorded or learned."
  return (
    <Field name={name} note={note}>
      <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <Switch on={on} onToggle={() => save({ key, value: { ...settings?.[key], on: !on } })} label={name} />
        <span style={{ color: on ? "var(--color-text)" : "var(--color-neutral-400)" }}>{on ? "On" : "Off"}</span>
      </span>
      {on && (
        <button className="fr-link" onClick={() => navigate(`/body?tab=${what}`)} style={{ alignSelf: "flex-start", fontSize: 12 }}>
          {what === "sleep" ? "Log or fix a night in Sleep & meals" : "Log or fix a meal in Sleep & meals"}
        </button>
      )}
    </Field>
  )
}

export const TrackSleep = () => <Tracking what="sleep" />
export const TrackMeals = () => <Tracking what="meals" />

/** The last two weeks: each time can be put right, or taken back. */
export function Nights({ nights }: { nights: Schemas["SleepNightOut"][] }) {
  if (!nights.length) return null
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {nights.map((n) => (
        <div key={n.date} className="fr-row" style={{ display: "grid", gridTemplateColumns: "92px repeat(4, minmax(0,1fr)) 64px", gap: 8, alignItems: "center", padding: "6px 0", fontSize: 12 }}>
          <span style={{ color: "var(--color-neutral-400)" }}>{dayLabel(n.date)}</span>
          <TapTime label="Done" at={n.done} id={n.done_id} timed={n.done_timed} timedSaid="The last timer you stopped before bed" />
          <TapTime label="Bed" at={n.bed} id={n.bed_id} />
          <TapTime label="Up" at={n.up} id={n.up_id} />
          <TapTime label="Ready" at={n.ready} id={n.ready_id} timed={n.ready_timed} timedSaid="The first timer you started" />
          <span className="tnum" title={`You plan for ${dur(n.planned_min)}`} style={{ textAlign: "right", color: n.slept_min && n.slept_min < n.planned_min - 60 ? "var(--fr-warn)" : "var(--color-neutral-300)" }}>
            {n.slept_min ? dur(n.slept_min) : "—"}
          </span>
        </div>
      ))}
    </div>
  )
}

function TapTime({ label, at, id, timed, timedSaid }: { label: string; at?: string | null; id?: number | null; timed?: boolean; timedSaid?: string }) {
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
          onBlur={(e) => (e.target.value && e.target.value !== at.slice(11, 16) && edit({ id, at: nearestAt(at, e.target.value) }), setEditing(false))}
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
    <button className="fr-plain fr-hover-text tnum" disabled={!id} onClick={() => setEditing(true)} title={timed ? timedSaid : id ? "Click to change" : undefined} style={{ textAlign: "left", color: "var(--color-neutral-300)" }}>
      {label} {clock(at)}
      {timed && <span style={{ color: "var(--color-neutral-500)" }}> (timer)</span>}
    </button>
  )
}
