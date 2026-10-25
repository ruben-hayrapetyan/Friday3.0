// Track my sleep (Settings → Schedule): off until you turn it on. On, the Now bar offers "I'm up", "Ready to work" and
// "Going to bed", one tap each; here are the last two weeks of nights, each time fixable, a missed tap to add, and what
// Friday has learned: bedtimes and wake times to take with one click, and your morning routine.

import { useState } from "react"
import type { Schemas } from "@/api/client"
import { Icon, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useSettings, useSleep } from "@/hooks/queries"
import { ampm, clock, dayLabel, dur } from "@/lib/format"
import { Field } from "./SettingsPage"

const KINDS = [
  { value: "bed", label: "Went to bed" },
  { value: "up", label: "Got up" },
  { value: "ready", label: "Ready to work" },
] as const
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
  const sleep = useSleep().data
  const save = useCommand("settings_set", { label: () => "Saved" })
  const on = !!settings?.sleep_tracking?.on
  return (
    <Field name="Track my sleep" note="Optional. One tap in the Now bar when you get up, when you're ready to work and when you go to bed; Friday learns from them. Off, nothing is recorded or learned.">
      <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <Switch on={on} onToggle={() => save({ key: "sleep_tracking", value: { ...settings?.sleep_tracking, on: !on } })} label="Track my sleep" />
        <span style={{ color: on ? "var(--color-text)" : "var(--color-neutral-400)" }}>{on ? "On" : "Off"}</span>
      </span>
      {on && sleep?.on && <Learned sleep={sleep} />}
    </Field>
  )
}

function Learned({ sleep }: { sleep: Schemas["SleepOut"] }) {
  const use = useCommand("settings_set", { label: () => "Your bedtimes and wake times are updated" })
  const routines = Object.entries(sleep.routine_min ?? {})
  const weekday = routines.filter(([d]) => WEEKDAY_MORNINGS.includes(d)).map(([, m]) => m)
  const weekend = routines.filter(([d]) => !WEEKDAY_MORNINGS.includes(d)).map(([, m]) => m)
  const left = Math.max(0, (sleep.min_nights ?? 4) - (sleep.recorded_nights ?? 0))
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <span className="fr-kicker" style={{ textWrap: "pretty" }}>
        {sleep.recorded_nights ? `${sleep.recorded_nights} night${sleep.recorded_nights === 1 ? "" : "s"} recorded` : "No nights recorded yet"}
        {sleep.average_slept_min ? `, about ${dur(sleep.average_slept_min)} of sleep a night lately` : ""}
        {left ? `. Friday learns your times after ${left} more.` : "."}
      </span>
      {!!sleep.changes?.length && (
        <div className="fr-well" style={{ display: "flex", flexDirection: "column", gap: 8, padding: "12px 14px" }}>
          <span style={{ display: "flex", gap: 8, alignItems: "center", fontWeight: 500 }}>
            <Icon name="sparkle" size={14} style={{ color: "var(--color-accent-300)" }} />
            Your real times differ from your schedule
          </span>
          {sleep.changes.map((c) => (
            <span key={`${c.field}${c.days.join()}`} style={{ fontSize: 13 }}>
              {daysSaid(c.days, c.field)}: {c.field === "bedtime" ? "to bed" : "up"} around <b style={{ fontWeight: 500 }}>{ampm(c.learned)}</b>
              <span style={{ color: "var(--color-neutral-500)" }}>, not {ampm(c.now)}</span>
            </span>
          ))}
          {sleep.suggested && (
            <button className="btn btn-primary fr-press" onClick={() => use({ key: "sleep", value: sleep.suggested })} style={{ alignSelf: "flex-start", fontSize: 12 }}>
              Use these times
            </button>
          )}
        </div>
      )}
      {(weekday.length > 0 || weekend.length > 0) && (
        <span style={{ fontSize: 13, textWrap: "pretty" }}>
          Your mornings: {weekday.length > 0 && `about ${dur(weekday[0])} from up to ready on weekdays`}
          {weekday.length > 0 && weekend.length > 0 && ", "}
          {weekend.length > 0 && `${dur(weekend[0])} at weekends`}. Friday keeps that time light.
        </span>
      )}
      <Nights nights={sleep.nights ?? []} />
      <MissedTap />
    </div>
  )
}

/** The last two weeks: each time can be put right, or taken back. */
function Nights({ nights }: { nights: Schemas["SleepNightOut"][] }) {
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

/** A tap you forgot, after the fact. */
function MissedTap() {
  const add = useCommand("sleep_mark", { label: (o) => o.result.message ?? "Added" })
  const [kind, setKind] = useState<"bed" | "up" | "ready">("bed")
  const [at, setAt] = useState("")
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", fontSize: 12 }}>
      <span className="fr-kicker">Forgot a tap?</span>
      <select className="input" value={kind} onChange={(e) => setKind(e.target.value as typeof kind)} aria-label="What" style={{ width: 140, padding: "3px 6px", minHeight: 0, fontSize: 12 }}>
        {KINDS.map((k) => (
          <option key={k.value} value={k.value}>
            {k.label}
          </option>
        ))}
      </select>
      <input type="datetime-local" className="input" value={at} onChange={(e) => setAt(e.target.value)} aria-label="When" style={{ width: 200, padding: "3px 6px", minHeight: 0, fontSize: 12 }} />
      <button className="btn btn-secondary" disabled={!at} onClick={async () => (await add({ kind, at: at.slice(0, 16) })) && setAt("")} style={{ fontSize: 12 }}>
        Add
      </button>
    </div>
  )
}
