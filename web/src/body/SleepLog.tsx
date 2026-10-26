// Sleep & meals → Sleep: the switch, the Now bar's three taps for when you missed one, a night to log after the fact
// or put right, and every night of the last two weeks with each time to change. What they say is in Insights.

import { useState } from "react"
import type { Schemas } from "@/api/client"
import { Icon, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useSettings, useSleep } from "@/hooks/queries"
import { dayLabel, weekday } from "@/lib/format"
import { addDays } from "@/lib/time"
import { Section } from "@/insights/Section"
import { Nights } from "@/settings/SleepTracking"
import { useShell } from "@/shell/ShellContext"

const TAPS = [
  { kind: "bed", icon: "moon", button: "Going to bed" },
  { kind: "up", icon: "sun-horizon", button: "I'm up" },
  { kind: "ready", icon: "coffee", button: "Ready to work" },
] as const

export function SleepLog() {
  const settings = useSettings().data as Record<string, { on?: boolean }> | undefined
  const sleep = useSleep().data
  const save = useCommand("settings_set", { label: () => "Saved" })
  const on = !!settings?.sleep_tracking?.on
  const toggle = (
    <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <span style={{ color: on ? "var(--color-text)" : "var(--color-neutral-400)", fontSize: 12 }}>{on ? "On" : "Off"}</span>
      <Switch on={on} onToggle={() => save({ key: "sleep_tracking", value: { ...settings?.sleep_tracking, on: !on } })} label="Track my sleep" />
    </span>
  )
  if (!on || !sleep?.on)
    return (
      <Section title="Track my sleep" note="Off. Turn it on and the Now bar offers “Going to bed”, “I’m up” and “Ready to work”; Friday learns your real bedtime, wake time and morning routine." right={toggle}>
        <span />
      </Section>
    )
  const nights = sleep.nights ?? []
  return (
    <>
      <Section title="Track my sleep" note="Missed a tap in the Now bar? Make it here." right={toggle}>
        <Taps next={sleep.next ?? null} />
      </Section>
      <Section title="Log a night" note="After the fact, or to put one right">
        <LogNight nights={nights} />
      </Section>
      <Section title="Your nights" note="The last two weeks. Click a time to change it or take it back.">
        {nights.length ? <Nights nights={nights} /> : <span style={{ color: "var(--color-neutral-400)" }}>No nights yet.</span>}
      </Section>
    </>
  )
}

/** The three taps the Now bar offers one at a time; the one it would offer now stands out. */
function Taps({ next }: { next: string | null }) {
  const mark = useCommand("sleep_mark", { label: (o) => o.result.message ?? "Saved" })
  const [busy, setBusy] = useState<string | null>(null)
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
      {TAPS.map((t) => (
        <button key={t.kind} className={`btn ${next === t.kind ? "btn-primary" : "btn-secondary"} fr-press`} disabled={!!busy} onClick={async () => (setBusy(t.kind), await mark({ kind: t.kind }), setBusy(null))}>
          {busy === t.kind ? <span className="fr-spinner" /> : <Icon name={t.icon} />}
          {t.button}
        </button>
      ))}
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
        Night
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
