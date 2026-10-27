// Schedule (v22): the shape of a normal day: when it starts, bedtime and the margin past it, a buffer between blocks, the
// the daily limit, the default pace, the first day of the week, and what happens to a block that passes untimed and
// unmarked (planned again, or counted done). Each sets every day; "By day" sets them one day at a time.

import { useState } from "react"
import { Seg } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { usePaces, useSettings } from "@/hooks/queries"
import { ampm, dur } from "@/lib/format"
import { useNavigate } from "react-router"
import { BUFFER_OPTIONS, bufferLabel, useBuffers } from "./buffers"
import { Field, SectionHead } from "./SettingsPage"
import { TrackMeals, TrackSleep } from "./SleepTracking"
import { TimeInput } from "@/components/fr/TimeInput"
import { SLEEP_HOURS } from "@/lib/ampm"

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
interface Night {
  bedtime: string
  wake: string
  margin_min: number
}
const times = (from: number, to: number) => Array.from({ length: (to - from) * 2 + 1 }, (_, i) => `${String(Math.floor(from + i / 2) % 24).padStart(2, "0")}:${i % 2 ? "30" : "00"}`)

export function Schedule() {
  const settings = useSettings().data as Record<string, unknown> | undefined
  const paces = usePaces().data
  const save = useCommand("settings_set", { label: () => "Saved" })
  const { buffers, set: setBuffers } = useBuffers()
  const navigate = useNavigate()
  const [byDay, setByDay] = useState(false)
  if (!settings) return null
  const sleep = settings.sleep as Record<string, Night>
  const caps = settings.daily_cap as Record<string, number>
  const time = settings.time as { week_start: string }
  const pace = settings.pace as { default: string }
  const planner = settings.planner as { assume_unreviewed: "done" | "not_done" }
  const missed = planner.assume_unreviewed
  const mon = sleep.mon
  const allNights = (change: Partial<Night>) => save({ key: "sleep", value: Object.fromEntries(DAYS.map((d) => [d, { ...sleep[d], ...change }])) })
  const differs = (k: keyof Night) => DAYS.some((d) => sleep[d][k] !== mon[k])
  return (
    <>
      <SectionHead title="Schedule" note="The shape of a normal day. Friday plans inside these limits." />
      <Field name="Day starts" note={`Nothing flexible is planned before this.${differs("wake") ? " Some days differ; this sets them all." : ""}`}>
        <select className="input" value={mon.wake} onChange={(e) => allNights({ wake: e.target.value })} style={{ alignSelf: "flex-start", width: 140 }}>
          {times(5, 11).map((t) => (
            <option key={t} value={t}>
              {ampm(t)}
            </option>
          ))}
        </select>
      </Field>
      <Field name="Bedtime" note={`Friday stops planning here; only a deadline can push past it.${differs("bedtime") ? " Some days differ; this sets them all." : ""}`}>
        <select className="input" value={mon.bedtime} onChange={(e) => allNights({ bedtime: e.target.value })} style={{ alignSelf: "flex-start", width: 140 }}>
          {times(21, 26).map((t) => (
            <option key={t} value={t}>
              {ampm(t)}
            </option>
          ))}
        </select>
      </Field>
      <Field name="Past bedtime, if a deadline needs it" note="The most Friday will run over when there is no other room; it costs a lot, and less sleep makes the next night cost more. The rest of your sleep is never used.">
        <Seg options={[30, 45, 60, 90].map((m) => ({ value: m, label: dur(m) }))} value={mon.margin_min} onPick={(m) => allNights({ margin_min: m })} size="big" />
      </Field>
      <Field name="Buffer between blocks" note="Breathing room so one thing running long doesn’t knock everything else.">
        <Seg options={BUFFER_OPTIONS.map((v) => ({ value: v, label: bufferLabel(v) }))} value={buffers.minutes} onPick={(v) => setBuffers({ minutes: v })} size="big" />
        <button className="fr-link" onClick={() => navigate("/settings/tags")} style={{ alignSelf: "flex-start", fontSize: 12 }}>
          {Object.keys(buffers.by_area).length + Object.keys(buffers.by_preset).length ? "Some tags and kinds have their own →" : "Set one per tag or kind →"}
        </button>
      </Field>
      <Field name="Daily limit" note="The most focused work Friday will plan in a day. Pace can raise or lower it for a while.">
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <input type="range" min={4} max={12} step={0.5} value={caps.mon} onChange={(e) => save({ key: "daily_cap", value: Object.fromEntries(DAYS.map((d) => [d, Number(e.target.value)])) })} aria-label="Daily limit" style={{ flex: 1, maxWidth: 320, accentColor: "var(--color-accent)" }} />
          <span className="fr-h tnum" style={{ fontSize: 20 }}>
            {caps.mon} h
          </span>
        </div>
      </Field>
      <Field name="Default pace" note="Where Friday returns after a temporary pace ends.">
        {paces && <Seg options={Object.keys(paces.paces)} value={pace.default} onPick={(p) => save({ key: "pace", value: { ...pace, default: p } })} size="big" />}
      </Field>
      <Field name="Week starts on">
        <Seg
          options={[
            { value: "mon", label: "Monday" },
            { value: "sun", label: "Sunday" },
          ]}
          value={time.week_start}
          onPick={(d) => save({ key: "time", value: { ...time, week_start: d } })}
          size="big"
        />
      </Field>
      <Field name="When a block passes and you didn’t time it or mark it" note={missed === "not_done" ? "Friday plans that work again, so a missed block moves instead of staying on your plan. Click a missed block to say you did it after all." : "Friday counts it as done until your review says otherwise, so the plan doesn’t move unless you tell it."}>
        <Seg
          options={[
            { value: "not_done", label: "Plan it again" },
            { value: "done", label: "Count it as done" },
          ]}
          value={missed}
          onPick={(v) => save({ key: "planner", value: { ...planner, assume_unreviewed: v } })}
          size="big"
        />
      </Field>
      <TrackSleep />
      <TrackMeals />
      <Field name="By day" note="Different bedtimes, wake times or limits on some days.">
        <button className="fr-link" onClick={() => setByDay(!byDay)} style={{ alignSelf: "flex-start" }}>
          {byDay ? "Hide" : "Set each day"}
        </button>
        {byDay && <ByDay sleep={sleep} caps={caps} />}
      </Field>
    </>
  )
}

function ByDay({ sleep, caps }: { sleep: Record<string, Night>; caps: Record<string, number> }) {
  const save = useCommand("settings_set", { label: () => "Saved" })
  const night = (d: string, change: Partial<Night>) => save({ key: "sleep", value: { ...sleep, [d]: { ...sleep[d], ...change } } })
  const input = { padding: "3px 6px", minHeight: 0, fontSize: 12 }
  return (
    <div style={{ display: "grid", gridTemplateColumns: "48px repeat(4, minmax(0, 1fr))", gap: "6px 8px", alignItems: "center" }}>
      {["", "Wake", "Bedtime", "Past bedtime", "Limit"].map((h) => (
        <span key={h} className="fr-kicker">
          {h}
        </span>
      ))}
      {DAYS.map((d) => (
        <Row key={d}>
          <span style={{ textTransform: "capitalize" }}>{d}</span>
          <TimeInput value={sleep[d].wake} onChange={(wake) => night(d, { wake })} expect={{ hours: SLEEP_HOURS.up }} label={`${d} wake`} style={input} />
          <TimeInput value={sleep[d].bedtime} onChange={(bedtime) => night(d, { bedtime })} expect={{ hours: SLEEP_HOURS.bed }} label={`${d} bedtime`} style={input} />
          <input type="number" className="input" min={0} max={240} step={15} value={sleep[d].margin_min} onChange={(e) => night(d, { margin_min: Number(e.target.value) })} style={input} />
          <input type="number" className="input" min={0} max={16} step={0.5} value={caps[d]} onChange={(e) => save({ key: "daily_cap", value: { ...caps, [d]: Number(e.target.value) } })} style={input} />
        </Row>
      ))}
    </div>
  )
}

function Row({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
