// Sleep (Insights; tracking is a setting, off until you turn it on): your last two weeks of nights on one timeline,
// from 8pm to the next noon (a bar from bed to up, the schedule you set as an outline behind it, a tick where you were
// ready to work), your usual times, a night to log or put right, and what Friday learned, to take with one click.

import { useState } from "react"
import { useNavigate } from "react-router"
import type { Schemas } from "@/api/client"
import { Icon, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useSettings, useSleep } from "@/hooks/queries"
import { ampm, clock, dayLabel, dur, weekday } from "@/lib/format"
import { addDays, toMin } from "@/lib/time"
import { daysSaid, Nights } from "@/settings/SleepTracking"
import { useShell } from "@/shell/ShellContext"
import { Section } from "./Section"

const FROM = 20 * 60 // the timeline runs from 8pm on the night's day…
const SPAN = 17 * 60 // …to 1pm the next day
const TICKS = [21, 24, 27, 30, 33, 36] // 9pm, 12am, 3am, 6am, 9am, 12pm
const WEEKDAY_MORNINGS = ["mon", "tue", "wed", "thu", "fri"]

/** Where a local time falls on a night's timeline, 0–100. */
export function along(date: string, at: string): number {
  const minutes = toMin(at) - toMin(`${date}T00:00`) - FROM
  return Math.max(0, Math.min(100, (minutes / SPAN) * 100))
}

/** The middle of some clock times, kept past midnight for bedtimes (11pm and 1am give midnight). */
export function usual(times: string[], night: boolean): string | null {
  if (!times.length) return null
  const minutes = times.map((t) => toMin(t) - toMin(`${t.slice(0, 10)}T00:00`)).map((m) => (night && m < 12 * 60 ? m + 24 * 60 : m))
  const sorted = [...minutes].sort((a, b) => a - b)
  const mid = Math.round(sorted[Math.floor((sorted.length - 1) / 2)] / 15) * 15 % (24 * 60)
  return `${String(Math.floor(mid / 60)).padStart(2, "0")}:${String(mid % 60).padStart(2, "0")}`
}

export function SleepSection() {
  const settings = useSettings().data as Record<string, { on?: boolean }> | undefined
  const sleep = useSleep().data
  const save = useCommand("settings_set", { label: () => "Saved" })
  const on = !!settings?.sleep_tracking?.on
  const toggle = <Switch on={on} onToggle={() => save({ key: "sleep_tracking", value: { ...settings?.sleep_tracking, on: !on } })} label="Track my sleep" />
  if (!on || !sleep?.on)
    return (
      <Section title="Sleep" note="Off. Turn it on to log your nights here; Friday learns your real bedtime, wake time and morning routine." right={toggle}>
        <span />
      </Section>
    )
  const nights = sleep.nights ?? []
  return (
    <Section title="Sleep" note="Your last two weeks of nights, and what Friday learned from them" right={toggle}>
      <Usual sleep={sleep} />
      {nights.length ? <Timeline nights={nights} /> : <span style={{ color: "var(--color-neutral-400)" }}>No nights yet. Log last night below, or tap “Going to bed” and “I’m up” in the Now bar.</span>}
      <LogNight nights={nights} />
      <LearnedSleep sleep={sleep} />
      {nights.length > 0 && (
        <details>
          <summary className="fr-kicker" style={{ cursor: "pointer", padding: "4px 0" }}>
            Every night, each time to change
          </summary>
          <Nights nights={nights} />
        </details>
      )}
    </Section>
  )
}

function Usual({ sleep }: { sleep: Schemas["SleepOut"] }) {
  const nights = sleep.nights ?? []
  const bed = usual(nights.flatMap((n) => (n.bed ? [n.bed] : [])), true)
  const up = usual(nights.flatMap((n) => (n.up ? [n.up] : [])), false)
  const routines = nights.flatMap((n) => (n.routine_min != null ? [n.routine_min] : []))
  const routine = routines.length ? [...routines].sort((a, b) => a - b)[Math.floor((routines.length - 1) / 2)] : null
  const stats: [string, string][] = [
    [sleep.average_slept_min ? dur(sleep.average_slept_min) : "—", "of sleep a night, lately"],
    [bed ? ampm(bed) : "—", "usually to bed"],
    [up ? ampm(up) : "—", "usually up"],
    [routine != null ? dur(Math.max(15, Math.round(routine / 15) * 15)) : "—", "from up to ready to work"],
  ]
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 20 }}>
      {stats.map(([big, line]) => (
        <div key={line} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <span className="fr-h tnum" style={{ fontSize: 28 }}>
            {big}
          </span>
          <span style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>{line}</span>
        </div>
      ))}
    </div>
  )
}

function Timeline({ nights }: { nights: Schemas["SleepNightOut"][] }) {
  const [hover, setHover] = useState<string | null>(null)
  const shown = nights.find((n) => n.date === hover)
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <div style={{ display: "grid", gridTemplateColumns: "64px minmax(0,1fr) 56px", gap: 10, fontSize: 10.5, color: "var(--color-neutral-500)" }}>
        <span />
        <span style={{ position: "relative", height: 14 }}>
          {TICKS.map((h) => (
            <span key={h} className="tnum" style={{ position: "absolute", left: `${((h * 60 - FROM) / SPAN) * 100}%`, transform: "translateX(-50%)" }}>
              {ampm(`${String(h % 24).padStart(2, "0")}:00`)}
            </span>
          ))}
        </span>
        <span style={{ textAlign: "right" }}>slept</span>
      </div>
      {nights.map((n) => (
        <div
          key={n.date}
          onMouseEnter={() => setHover(n.date)}
          onMouseLeave={() => setHover(null)}
          style={{ display: "grid", gridTemplateColumns: "64px minmax(0,1fr) 56px", gap: 10, alignItems: "center", padding: "3px 0", borderRadius: 4, background: hover === n.date ? "color-mix(in srgb, var(--color-text) 5%, transparent)" : undefined }}
        >
          <span style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>
            {weekday(n.date)} {Number(n.date.slice(8, 10))}
          </span>
          <span style={{ position: "relative", height: 16 }}>
            {TICKS.map((h) => (
              <span key={h} style={{ position: "absolute", top: 0, bottom: 0, width: 1, left: `${((h * 60 - FROM) / SPAN) * 100}%`, background: "var(--fr-hairline)" }} />
            ))}
            {n.planned_bed && n.planned_up && (
              <span title="The bedtime and wake time you set" style={{ position: "absolute", top: 1, bottom: 1, left: `${along(n.date, n.planned_bed)}%`, width: `${along(n.date, n.planned_up) - along(n.date, n.planned_bed)}%`, borderRadius: 4, boxShadow: "inset 0 0 0 1px color-mix(in srgb, var(--color-text) 22%, transparent)" }} />
            )}
            {n.bed && n.up ? (
              <span style={{ position: "absolute", top: 4, bottom: 4, left: `${along(n.date, n.bed)}%`, width: `${Math.max(0.6, along(n.date, n.up) - along(n.date, n.bed))}%`, borderRadius: 4, background: "var(--color-accent)" }} />
            ) : (
              [n.bed, n.up].filter(Boolean).map((at) => <span key={at} style={{ position: "absolute", top: 4, width: 8, height: 8, borderRadius: "50%", left: `calc(${along(n.date, at as string)}% - 4px)`, background: "var(--color-accent)" }} />)
            )}
            {n.ready && <span title="Ready to work" style={{ position: "absolute", top: 0, bottom: 0, width: 2, borderRadius: 1, left: `${along(n.date, n.ready)}%`, background: "var(--color-accent-200)" }} />}
          </span>
          <span className="tnum" style={{ textAlign: "right", fontSize: 12, color: n.slept_min && n.slept_min < n.planned_min - 60 ? "var(--fr-warn)" : "var(--color-neutral-300)" }}>
            {n.slept_min ? dur(n.slept_min) : "—"}
          </span>
        </div>
      ))}
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center", fontSize: 11, color: "var(--color-neutral-500)", paddingTop: 4 }}>
        <span style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
          <span style={{ width: 18, height: 8, borderRadius: 4, background: "var(--color-accent)" }} /> Asleep
        </span>
        <span style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
          <span style={{ width: 18, height: 12, borderRadius: 4, boxShadow: "inset 0 0 0 1px color-mix(in srgb, var(--color-text) 22%, transparent)" }} /> Your schedule
        </span>
        <span style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
          <span style={{ width: 2, height: 12, borderRadius: 1, background: "var(--color-accent-200)" }} /> Ready to work
        </span>
        <span style={{ flex: 1 }} />
        <span className="tnum" style={{ color: "var(--color-neutral-300)" }}>
          {shown ? `${dayLabel(shown.date)}: ${shown.bed ? `bed ${clock(shown.bed)}` : "no bedtime"}, ${shown.up ? `up ${clock(shown.up)}` : "no wake time"}${shown.ready ? `, ready ${clock(shown.ready)}` : ""}${shown.slept_min ? ` · ${dur(shown.slept_min)} asleep, ${dur(shown.planned_min)} planned` : ""}` : "Point at a night for its times"}
        </span>
      </div>
    </div>
  )
}

type Kind = "bed" | "up" | "ready"

/** Last night, or any of the two weeks before: the times to add, or to put right. */
function LogNight({ nights }: { nights: Schemas["SleepNightOut"][] }) {
  const { today } = useShell()
  const sleepSet = (useSettings().data as Record<string, Record<string, { bedtime: string; wake: string }>> | undefined)?.sleep
  const add = useCommand("sleep_mark", { label: (o) => o.result.message ?? "Saved" })
  const edit = useCommand("sleep_mark_edit", { label: (o) => o.result.message ?? "Saved" })
  const evenings = Array.from({ length: 14 }, (_, n) => addDays(today, -1 - n))
  const [evening, setEvening] = useState(evenings[0])
  const night = nights.find((n) => n.date === evening)
  const morning = addDays(evening, 1)
  const key = (d: string) => ["sun", "mon", "tue", "wed", "thu", "fri", "sat"][new Date(`${d}T12:00:00Z`).getUTCDay()]
  const planned = { bed: sleepSet?.[key(evening)]?.bedtime ?? "23:30", up: sleepSet?.[key(morning)]?.wake ?? "08:00" }
  const start = { bed: night?.bed?.slice(11, 16) ?? planned.bed, up: night?.up?.slice(11, 16) ?? planned.up, ready: night?.ready?.slice(11, 16) ?? "" }
  const [times, setTimes] = useState<Record<Kind, string>>(start)
  const [saving, setSaving] = useState(false)
  const pick = (d: string) => {
    setEvening(d)
    const n = nights.find((x) => x.date === d)
    const m = addDays(d, 1)
    setTimes({ bed: n?.bed?.slice(11, 16) ?? sleepSet?.[key(d)]?.bedtime ?? "23:30", up: n?.up?.slice(11, 16) ?? sleepSet?.[key(m)]?.wake ?? "08:00", ready: n?.ready?.slice(11, 16) ?? "" })
  }
  // A bedtime in the small hours is the next morning's date; up and ready are the morning's.
  const at = (kind: Kind, time: string) => `${kind === "bed" && time >= "12:00" ? evening : morning}T${time}`
  const ids: Record<Kind, number | null | undefined> = { bed: night?.bed_id, up: night?.up_id, ready: night?.ready_id }
  const save = async () => {
    setSaving(true)
    for (const kind of ["bed", "up", "ready"] as Kind[]) {
      const time = times[kind]
      if (!time) continue
      const was = { bed: night?.bed, up: night?.up, ready: night?.ready_timed ? null : night?.ready }[kind]
      if (ids[kind] && was?.slice(11, 16) !== time) await edit({ id: ids[kind] as number, at: at(kind, time) })
      else if (!ids[kind] && !(kind === "ready" && night?.ready_timed && night.ready?.slice(11, 16) === time)) await add({ kind, at: at(kind, time) })
    }
    setSaving(false)
  }
  const field = (kind: Kind, label: string) => (
    <label style={{ display: "flex", flexDirection: "column", gap: 3, fontSize: 11, color: "var(--color-neutral-400)" }}>
      {label}
      <input type="time" className="input" value={times[kind]} onChange={(e) => setTimes({ ...times, [kind]: e.target.value })} style={{ width: 120, padding: "4px 8px", minHeight: 0, fontSize: 13 }} />
    </label>
  )
  return (
    <div className="fr-well" style={{ display: "flex", alignItems: "flex-end", gap: 14, flexWrap: "wrap", padding: "12px 14px" }}>
      <label style={{ display: "flex", flexDirection: "column", gap: 3, fontSize: 11, color: "var(--color-neutral-400)" }}>
        Log a night
        <select className="input" value={evening} onChange={(e) => pick(e.target.value)} style={{ width: 170, padding: "4px 8px", minHeight: 0, fontSize: 13 }}>
          {evenings.map((d, n) => (
            <option key={d} value={d}>
              {n === 0 ? `Last night (${weekday(d)})` : `${dayLabel(d)} night`}
            </option>
          ))}
        </select>
      </label>
      {field("bed", "Went to bed")}
      {field("up", "Got up")}
      {field("ready", "Ready to work")}
      <button className="btn btn-primary fr-press" disabled={saving} onClick={save} style={{ fontSize: 12 }}>
        {saving ? <span className="fr-spinner" /> : <Icon name="check" />}
        {night ? "Save changes" : "Log it"}
      </button>
    </div>
  )
}

function LearnedSleep({ sleep }: { sleep: Schemas["SleepOut"] }) {
  const use = useCommand("settings_set", { label: () => "Your bedtimes and wake times are updated" })
  const navigate = useNavigate()
  const left = Math.max(0, (sleep.min_nights ?? 4) - (sleep.recorded_nights ?? 0))
  const routines = Object.entries(sleep.routine_min ?? {})
  const weekdays = routines.find(([d]) => WEEKDAY_MORNINGS.includes(d))?.[1]
  const weekend = routines.find(([d]) => !WEEKDAY_MORNINGS.includes(d))?.[1]
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
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
            <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <button className="btn btn-primary fr-press" onClick={() => use({ key: "sleep", value: sleep.suggested })} style={{ fontSize: 12 }}>
                Use these times
              </button>
              <button className="fr-link" onClick={() => navigate("/settings/schedule")} style={{ fontSize: 12 }}>
                or set them yourself
              </button>
            </span>
          )}
        </div>
      )}
      <span className="fr-kicker" style={{ textWrap: "pretty" }}>
        {left ? `Friday suggests your times after ${left} more night${left === 1 ? "" : "s"} with both a bedtime and a wake time.` : "Friday plans your mornings and late nights from these."}
        {weekdays != null && ` Your weekday mornings take about ${dur(weekdays)} from up to ready; Friday keeps them light.`}
        {weekend != null && ` Weekends, about ${dur(weekend)}.`}
      </span>
    </div>
  )
}
