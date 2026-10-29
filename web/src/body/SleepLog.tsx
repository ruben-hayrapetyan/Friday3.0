// Sleep & meals → Sleep: the switch, the Now bar's four taps for when you missed one and Taking a nap, your naps
// (29 Oct) to log, change or delete, and the last two weeks a night a row, each to change, or to log when it wasn't
// recorded, in a card under the row. What they say is above it.

import { useState } from "react"
import type { Schemas } from "@/api/client"
import { Icon, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useSettings, useSleep } from "@/hooks/queries"
import { clock, dayLabel, dur, weekday } from "@/lib/format"
import { addDays, nearestAt } from "@/lib/time"
import { Section } from "@/insights/Section"
import { useShell } from "@/shell/ShellContext"
import { EditCard, minutesBetween, TimeField } from "./Times"
import { NAP_HOURS, SLEEP_HOURS } from "@/lib/ampm"
import { useBreaks } from "@/now/breaks"

const TAPS = [
  { kind: "done", icon: "laptop", button: "Done with work" },
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
      <Section title="Track my sleep" note="Off. Turn it on and the Now bar offers “Done with work”, “Going to bed”, “I’m up” and “Ready to work”; Friday learns your real bedtime, wake time, morning routine and wind-down before bed." right={toggle}>
        <span />
      </Section>
    )
  const nights = sleep.nights ?? []
  return (
    <>
      <Section title="Track my sleep" note="Missed a tap in the Now bar? Make it here." right={toggle}>
        <Taps next={sleep.next ?? null} napping={sleep.napping ?? null} />
      </Section>
      <Naps naps={sleep.naps ?? []} usual={sleep.usual_nap_min ?? null} />
      <Section title="Your nights" note="The last two weeks. Click a night to change its times, or to log one you didn’t tap.">
        <NightRows nights={nights} />
      </Section>
    </>
  )
}

/** The four taps the Now bar offers one at a time; the one it would offer now stands out. Then Taking a nap, or
 * while you nap, I'm up. */
function Taps({ next, napping }: { next: string | null; napping: Schemas["NapOut"] | null }) {
  const mark = useCommand("sleep_mark", { label: (o) => o.result.message ?? "Saved" })
  const up = useCommand("nap_end", { label: (o) => o.result.message ?? "Saved" })
  const breaks = useBreaks()
  const [busy, setBusy] = useState<string | null>(null)
  const run = async (key: string, act: () => Promise<unknown>) => (setBusy(key), await act(), setBusy(null))
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
      {TAPS.map((t) => (
        <button key={t.kind} className={`btn ${next === t.kind ? "btn-primary" : "btn-secondary"} fr-press`} disabled={!!busy} onClick={() => run(t.kind, () => mark({ kind: t.kind }))}>
          {busy === t.kind ? <span className="fr-spinner" /> : <Icon name={t.icon} />}
          {t.button}
        </button>
      ))}
      <span style={{ width: 1, alignSelf: "stretch", margin: "4px 4px", background: "var(--fr-hairline)" }} />
      {napping ? (
        <>
          <span className="tnum" style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>
            Napping since {clock(napping.start)}
          </span>
          <button className="btn btn-primary fr-press" disabled={!!busy} onClick={() => run("nap", () => up({}))}>
            {busy === "nap" ? <span className="fr-spinner" /> : <Icon name="sun" />}
            I’m up
          </button>
        </>
      ) : (
        breaks.nap && (
          <button className="btn btn-secondary fr-press" disabled={!!busy} onClick={() => run("nap", breaks.nap!)} title="The plan keeps the time clear for as long as you usually nap">
            {busy === "nap" ? <span className="fr-spinner" /> : <Icon name="bed" />}
            Taking a nap
          </button>
        )
      )}
    </div>
  )
}

/** Your naps of the last two weeks, newest first, each to change or delete in a card under it; Log a nap opens one
 * for a nap you didn't tap. */
function Naps({ naps, usual }: { naps: Schemas["NapOut"][]; usual: number | null }) {
  const { today } = useShell()
  const [open, setOpen] = useState<number | "new" | null>(null)
  const said = naps.length ? `The last two weeks${usual ? `; you usually nap ${dur(usual)}` : ""}. Click a nap to change it.` : "None in the last two weeks."
  return (
    <Section
      title="Your naps"
      note={said}
      right={
        <button className="fr-link" onClick={() => setOpen(open === "new" ? null : "new")} style={{ fontSize: 12, display: "inline-flex", gap: 4, alignItems: "center" }}>
          <Icon name="plus" size={11} />
          Log a nap
        </button>
      }
    >
      {open === "new" && <NapCard key="new" onClose={() => setOpen(null)} />}
      {naps.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column" }}>
          {naps.map((nap) => {
            const on = open === nap.id
            return (
              <div key={nap.id} className="fr-row" style={{ padding: "2px 0", fontSize: 12 }}>
                <button
                  className="fr-plain fr-hover-text tnum"
                  onClick={() => setOpen(on ? null : nap.id)}
                  aria-expanded={on}
                  title="Change this nap"
                  style={{ display: "grid", gridTemplateColumns: "110px minmax(0,1fr) 64px 16px", gap: 8, alignItems: "center", width: "100%", textAlign: "left", padding: "4px 6px", borderRadius: 6, background: on ? "color-mix(in srgb, var(--color-accent) 12%, transparent)" : undefined }}
                >
                  <span style={{ color: "var(--color-neutral-400)" }}>{nap.date === today ? "Today" : dayLabel(nap.date)}</span>
                  <span style={{ color: "var(--color-neutral-200)" }}>
                    {clock(nap.start)}–{nap.end ? clock(nap.end) : "now"}
                  </span>
                  <span style={{ textAlign: "right", color: "var(--color-neutral-300)" }}>{nap.minutes ? dur(nap.minutes) : "—"}</span>
                  <Icon name={on ? "caret-up" : "pencil-simple"} size={11} style={{ color: "var(--color-neutral-600)" }} />
                </button>
                {on && <NapCard key={nap.id} nap={nap} onClose={() => setOpen(null)} />}
              </div>
            )
          })}
        </div>
      )}
    </Section>
  )
}

/** One nap's card: the day (for a new one), when you lay down and got up, and how long that is; Save, Delete and
 * Cancel. */
function NapCard({ nap, onClose }: { nap?: Schemas["NapOut"]; onClose: () => void }) {
  const { today } = useShell()
  const dayStart = (useSettings().data as Record<string, { day_start?: string }> | undefined)?.time?.day_start ?? "04:00"
  const log = useCommand("nap_log", { label: (o) => o.result.message ?? "Saved" })
  const edit = useCommand("nap_edit", { label: (o) => o.result.message ?? "Saved" })
  const remove = useCommand("nap_remove", { label: (o) => o.result.message ?? "Removed" })
  const [day, setDay] = useState(nap?.date ?? today)
  const [from, setFrom] = useState(nap?.start.slice(11, 16) ?? "15:00")
  const [to, setTo] = useState(nap?.end?.slice(11, 16) ?? "15:30")
  const [busy, setBusy] = useState(false)
  const minutes = minutesBetween(from, to)
  // A nap in the small hours (before your day starts) is the night of its day: the next date.
  const at = (time: string) => `${time < dayStart ? addDays(day, 1) : day}T${time}`
  const run = async (act: () => Promise<unknown>) => {
    setBusy(true)
    const ok = await act()
    setBusy(false)
    if (ok !== undefined) onClose()
  }
  const save = () =>
    run(async () => {
      if (!nap) return log({ start: at(from), end: at(to) })
      const start = from !== nap.start.slice(11, 16) ? nearestAt(nap.start, from) : undefined
      const end = to && to !== nap.end?.slice(11, 16) ? nearestAt(nap.end ?? nap.start, to) : undefined
      return start || end ? edit({ id: nap.id, start, end }) : true
    })
  const days = Array.from({ length: 7 }, (_, n) => addDays(today, -n))
  return (
    <EditCard
      title={nap ? `Nap · ${dayLabel(nap.date)}` : "Log a nap"}
      said={minutes ? dur(minutes) : undefined}
      saveLabel={nap ? "Save" : "Log it"}
      canSave={!!from && !!to && minutes !== null && minutes > 0 && minutes <= 240}
      busy={busy}
      onSave={save}
      onCancel={onClose}
      extra={
        nap ? (
          <button className="btn btn-ghost" disabled={busy} onClick={() => run(() => remove({ id: nap.id }))} style={{ fontSize: 12, color: "var(--fr-due)" }}>
            <Icon name="trash" size={12} />
            Delete this nap
          </button>
        ) : null
      }
    >
      {!nap && (
        <label style={{ display: "flex", flexDirection: "column", gap: 3, fontSize: 11, color: "var(--color-neutral-400)" }}>
          Day
          <select className="input" value={day} onChange={(e) => setDay(e.target.value)} style={{ width: 140, padding: "4px 8px", minHeight: 0, fontSize: 13 }}>
            {days.map((d, n) => (
              <option key={d} value={d}>
                {n === 0 ? "Today" : n === 1 ? "Yesterday" : dayLabel(d)}
              </option>
            ))}
          </select>
        </label>
      )}
      <TimeField label="Lay down" value={from} onChange={setFrom} expect={{ hours: NAP_HOURS }} />
      <TimeField label="Got up" value={to} onChange={setTo} expect={{ after: from }} />
    </EditCard>
  )
}

type Kind = "done" | "bed" | "up" | "ready"
const KINDS: { kind: Kind; label: string; short: string }[] = [
  { kind: "done", label: "Done with work", short: "Done" },
  { kind: "bed", label: "Went to bed", short: "Bed" },
  { kind: "up", label: "Got up", short: "Up" },
  { kind: "ready", label: "Ready to work", short: "Ready" },
]

const dow = (d: string) => ["sun", "mon", "tue", "wed", "thu", "fri", "sat"][new Date(`${d}T12:00:00Z`).getUTCDay()]

/** The last two weeks of nights, one a row: its four times and how long you slept; a night not recorded too. A row
 * clicked opens its card under it (`NightCard`). */
function NightRows({ nights }: { nights: Schemas["SleepNightOut"][] }) {
  const { today } = useShell()
  const [open, setOpen] = useState<string | null>(null)
  const byDate = new Map(nights.map((n) => [n.date, n]))
  const evenings = Array.from({ length: 14 }, (_, n) => addDays(today, -1 - n))
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {evenings.map((date, n) => {
        const night = byDate.get(date)
        const on = open === date
        return (
          <div key={date} className="fr-row" style={{ padding: "4px 0", fontSize: 12 }}>
            <button
              className="fr-plain fr-hover-text"
              onClick={() => setOpen(on ? null : date)}
              aria-expanded={on}
              title="Change this night"
              style={{ display: "grid", gridTemplateColumns: "110px repeat(4, minmax(0,1fr)) 64px 16px", gap: 8, alignItems: "center", width: "100%", textAlign: "left", padding: "4px 6px", borderRadius: 6, background: on ? "color-mix(in srgb, var(--color-accent) 12%, transparent)" : undefined }}
            >
              <span style={{ color: "var(--color-neutral-400)" }}>{n === 0 ? `Last night (${weekday(date)})` : `${dayLabel(date)} night`}</span>
              {night ? (
                <>
                  {KINDS.map(({ kind, short }) => {
                    const at = night[kind]
                    const timed = (kind === "done" && night.done_timed) || (kind === "ready" && night.ready_timed)
                    return (
                      <span key={kind} className="tnum" style={{ color: at ? "var(--color-neutral-200)" : "var(--color-neutral-600)" }}>
                        {short} {at ? clock(at) : "—"}
                        {timed && <span style={{ color: "var(--color-neutral-500)" }}> (timer)</span>}
                      </span>
                    )
                  })}
                  <span className="tnum" title={`You plan for ${dur(night.planned_min)}`} style={{ textAlign: "right", color: night.slept_min && night.slept_min < night.planned_min - 60 ? "var(--fr-warn)" : "var(--color-neutral-300)" }}>
                    {night.slept_min ? dur(night.slept_min) : "—"}
                  </span>
                </>
              ) : (
                <span style={{ gridColumn: "2 / span 5", color: "var(--color-neutral-600)" }}>Not recorded: click to log it</span>
              )}
              <Icon name={on ? "caret-up" : "pencil-simple"} size={11} style={{ color: "var(--color-neutral-600)" }} />
            </button>
            {on && <NightCard key={date} evening={date} night={night} onClose={() => setOpen(null)} />}
          </div>
        )
      })}
    </div>
  )
}

/** One night's card: the four times, each to change or clear, and how long that is asleep; Save and Cancel. */
function NightCard({ evening, night, onClose }: { evening: string; night?: Schemas["SleepNightOut"]; onClose: () => void }) {
  const sleepSet = (useSettings().data as Record<string, Record<string, { bedtime: string; wake: string }>> | undefined)?.sleep
  const add = useCommand("sleep_mark", { label: (o) => o.result.message ?? "Saved" })
  const edit = useCommand("sleep_mark_edit", { label: (o) => o.result.message ?? "Saved" })
  const remove = useCommand("sleep_mark_remove", { label: (o) => o.result.message ?? "Removed" })
  const morning = addDays(evening, 1)
  const recorded: Record<Kind, string> = {
    done: night?.done?.slice(11, 16) ?? "",
    bed: night?.bed?.slice(11, 16) ?? "",
    up: night?.up?.slice(11, 16) ?? "",
    ready: night?.ready?.slice(11, 16) ?? "",
  }
  // A night not recorded starts from your usual bedtime and wake time, to log in one click; one recorded in part
  // leaves what's missing empty, so Save doesn't log a time you didn't give.
  const usual = { ...recorded, bed: sleepSet?.[dow(evening)]?.bedtime ?? "23:30", up: sleepSet?.[dow(morning)]?.wake ?? "08:00" }
  const [times, setTimes] = useState(night ? recorded : usual)
  const [busy, setBusy] = useState(false)
  // A bedtime (or the end of work) in the small hours is the next morning's date; up and ready are the morning's.
  const at = (kind: Kind, time: string) => `${(kind === "bed" || kind === "done") && time >= "12:00" ? evening : morning}T${time}`
  const ids: Record<Kind, number | null | undefined> = { done: night?.done_id, bed: night?.bed_id, up: night?.up_id, ready: night?.ready_id }
  const slept = minutesBetween(times.bed, times.up)
  const changed = KINDS.some(({ kind }) => times[kind] !== recorded[kind])
  const fromTimer = (kind: Kind) => (kind === "done" && !!night?.done_timed) || (kind === "ready" && !!night?.ready_timed)
  const save = async () => {
    setBusy(true)
    let ok = true
    for (const { kind } of KINDS) {
      const time = times[kind]
      const id = ids[kind]
      if (time === recorded[kind]) continue
      // A time from a timer (the first you started, the last you stopped) isn't a tap: a new one is.
      const out = !time ? (id ? await remove({ id }) : true) : id ? await edit({ id, at: at(kind, time) }) : await add({ kind, at: at(kind, time) })
      ok = ok && out !== undefined
    }
    setBusy(false)
    if (ok) onClose()
  }
  return (
    <EditCard
      title={`${dayLabel(evening)} night`}
      said={slept !== null ? `${dur(slept)} asleep${night?.planned_min ? `, of ${dur(night.planned_min)} planned` : ""}` : undefined}
      saveLabel={night ? "Save changes" : "Log it"}
      canSave={changed}
      busy={busy}
      onSave={save}
      onCancel={onClose}
    >
      {KINDS.map(({ kind, label }) => (
        <TimeField
          key={kind}
          label={fromTimer(kind) && times[kind] === recorded[kind] ? `${label} (timer)` : label}
          value={times[kind]}
          onChange={(v) => setTimes({ ...times, [kind]: v })}
          expect={{ hours: SLEEP_HOURS[kind], after: kind === "ready" ? times.up : undefined }}
          // A time from a timer isn't a tap to take back: type over it instead.
          onClear={fromTimer(kind) && !ids[kind] ? undefined : () => setTimes({ ...times, [kind]: "" })}
        />
      ))}
    </EditCard>
  )
}
