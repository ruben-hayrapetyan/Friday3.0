// Schedule (v22): the shape of a normal day: when it starts, bedtime and the margin past it, a buffer between blocks, the
// the daily limit, the default pace, the first day of the week, and what happens to a block that passes untimed and
// unmarked (planned again, or counted done). Each sets every day; "By day" sets them one day at a time.

import { useState } from "react"
import { Seg } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { usePaces, useSettings } from "@/hooks/queries"
import { clockTime, dur } from "@/lib/format"
import { useNavigate } from "react-router"
import { BUFFER_OPTIONS, bufferLabel, useBuffers } from "./buffers"
import { Field, SectionHead } from "./SettingsPage"
import { TrackMeals, TrackSleep } from "./SleepTracking"
import { TimeInput } from "@/components/fr/TimeInput"
import { SLEEP_HOURS } from "@/lib/ampm"
import { useBriefSwitch } from "@/dialogs/Dialogs"
import { HeldNumber, HeldRange } from "./Held"

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
interface Night {
  bedtime: string
  wake: string
  margin_min: number
}
const times = (from: number, to: number) => Array.from({ length: (to - from) * 2 + 1 }, (_, i) => `${String(Math.floor(from + i / 2) % 24).padStart(2, "0")}:${i % 2 ? "30" : "00"}`)

/** The half-hours to pick from, with the time saved among them when it's another (a 7:15am wake set day by day): the
 * box showed nothing for it, or the first time as if that were saved (audit, 12 Nov). */
export function timesWith(from: number, to: number, saved: string): string[] {
  const all = times(from, to)
  if (!saved || all.includes(saved)) return all
  const key = (t: string) => ((Number(t.slice(0, 2)) - from + 36) % 24) * 60 + Number(t.slice(3, 5)) // from 12 hours before the first
  return [...all, saved].sort((a, b) => key(a) - key(b))
}

export function Schedule() {
  const settings = useSettings().data as Record<string, unknown> | undefined
  const paces = usePaces().data
  const save = useCommand("settings_set", { label: () => "Saved" })
  const { buffers, set: setBuffers } = useBuffers()
  const navigate = useNavigate()
  const [byDay, setByDay] = useState(false)
  const [brief, setBrief] = useBriefSwitch()
  if (!settings) return null
  const sleep = settings.sleep as Record<string, Night>
  const caps = settings.daily_cap as Record<string, number>
  const time = settings.time as { week_start: string }
  const pace = settings.pace as { default: string }
  const planner = settings.planner as { assume_unreviewed: "done" | "not_done" }
  const missed = planner.assume_unreviewed
  const sittings = settings.sittings as { one_go: boolean; split_first: string[]; factor: number }
  const mon = sleep.mon
  const allNights = (change: Partial<Night>) => save({ key: "sleep", value: Object.fromEntries(DAYS.map((d) => [d, { ...sleep[d], ...change }])) })
  const differs = (k: keyof Night) => DAYS.some((d) => sleep[d][k] !== mon[k])
  return (
    <>
      <SectionHead title="Schedule" note="The shape of a normal day. Friday plans inside these limits." />
      <Field name="Day starts" note={`Nothing flexible is planned before this.${differs("wake") ? " Some days differ; this sets them all." : ""}`}>
        <select className="input" value={mon.wake} onChange={(e) => allNights({ wake: e.target.value })} style={{ alignSelf: "flex-start", width: 140 }}>
          {timesWith(5, 11, mon.wake).map((t) => (
            <option key={t} value={t}>
              {clockTime(t)}
            </option>
          ))}
        </select>
      </Field>
      <Field name="Bedtime" note={`Friday stops planning here; only a deadline can push past it.${differs("bedtime") ? " Some days differ; this sets them all." : ""}`}>
        <select className="input" value={mon.bedtime} onChange={(e) => allNights({ bedtime: e.target.value })} style={{ alignSelf: "flex-start", width: 140 }}>
          {timesWith(21, 26, mon.bedtime).map((t) => (
            <option key={t} value={t}>
              {clockTime(t)}
            </option>
          ))}
        </select>
      </Field>
      <Field name="Past bedtime, if a deadline needs it" note="The most Friday will plan past bedtime when there’s no other room, and only as a last resort.">
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
          <HeldRange min={4} max={12} step={0.5} value={caps.mon} onSave={(v) => save({ key: "daily_cap", value: Object.fromEntries(DAYS.map((d) => [d, v])) })} aria-label="Daily limit" style={{ flex: 1, maxWidth: 320, accentColor: "var(--color-accent)" }} />
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
      <Field name="When a block passes and you didn’t time it or mark it" note={missed === "not_done" ? "Friday plans the work again and the Inbox doesn’t ask. Click a missed block if you did it after all." : "Friday counts it as done, and the Inbox asks how much you actually did."}>
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
      {/* Yours since COMBINED.md 38 but only settable by hand: a new user had no way to it (9 Nov, "what do I have that
          a user who just downloaded the app does not"). */}
      <Field name="Sittings" note="Whether Friday may split a task across sittings. In one go keeps each task together where it can.">
        <Seg
          options={[
            { value: "split", label: "Split as needed" },
            { value: "one_go", label: "In one go" },
          ]}
          value={sittings.one_go ? "one_go" : "split"}
          onPick={(v) => save({ key: "sittings", value: { ...sittings, one_go: v === "one_go" } })}
          size="big"
        />
      </Field>
      <Field name="Morning brief" note="Today’s plan and what matters most, when you first open Friday before noon. It’s always in the Plan menu too.">
        <Seg
          options={[
            { value: "on", label: "Show it" },
            { value: "off", label: "Don't" },
          ]}
          value={brief === false ? "off" : "on"}
          onPick={(v) => setBrief(v === "on")}
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
          <HeldNumber className="input" min={0} max={240} step={15} value={sleep[d].margin_min} onSave={(margin_min) => night(d, { margin_min })} aria-label={`${d} past bedtime`} style={input} />
          <HeldNumber className="input" min={0} max={16} step={0.5} value={caps[d]} onSave={(cap) => save({ key: "daily_cap", value: { ...caps, [d]: cap } })} aria-label={`${d} limit`} style={input} />
        </Row>
      ))}
    </div>
  )
}

function Row({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
