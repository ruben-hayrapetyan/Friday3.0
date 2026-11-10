// Sleep (Insights → Sleep, above the nights to log or put right): what your tracked nights say, while tracking
// is on (the switch is below it). Your last two weeks of nights on one timeline from 8pm to the next noon (a bar from bed to up,
// the schedule you set as an outline behind it, ticks where you were done with work and ready to work), your usual
// times, your wind-down and morning routine, your naps, and what Friday learned, to take with one click.

import { useState } from "react"
import { useNavigate } from "react-router"
import type { Schemas } from "@/api/client"
import { Icon } from "@/components/fr/controls"
import { useSleep } from "@/hooks/queries"
import { useAsks } from "@/inbox/asks"
import { ampm, clock, dayLabel, dur, weekday } from "@/lib/format"
import { toMin } from "@/lib/time"
import { daysSaid } from "@/settings/SleepTracking"
import { InboxLink } from "./Learned"
import { Section } from "./Section"

const FROM = 20 * 60 // the timeline runs from 8pm on the night's day…
const SPAN = 17 * 60 // …to 1pm the next day
const TICKS = [21, 24, 27, 30, 33, 36] // 9pm, 12am, 3am, 6am, 9am, 12pm
const WEEKDAY_MORNINGS = ["mon", "tue", "wed", "thu", "fri"]
const SCHOOL_NIGHTS = ["sun", "mon", "tue", "wed", "thu"]

/** The middle value, or null for none. */
const middle = (values: number[]): number | null => (values.length ? [...values].sort((a, b) => a - b)[Math.floor((values.length - 1) / 2)] : null)

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

/** `here`: on Insights → Sleep itself, with no link to it, and nothing while tracking is off (its switch is below). */
export function SleepSection({ here = false }: { here?: boolean }) {
  const sleep = useSleep().data
  const navigate = useNavigate()
  const log = here ? undefined : (
    <button className="fr-link" onClick={() => navigate("/insights?tab=sleep")} style={{ fontSize: 12 }}>
      {sleep?.on ? "Log or fix a night" : "Turn it on in Insights → Sleep"}
    </button>
  )
  if (!sleep?.on && here) return null
  if (!sleep?.on)
    return (
      <Section title="Sleep" note="Not tracked. Track your sleep and Friday learns your real bedtime, wake time and morning routine." right={log}>
        <span />
      </Section>
    )
  const nights = sleep.nights ?? []
  return (
    <Section title="Sleep" note="Your last two weeks of nights, and what Friday learned from them" right={log}>
      <Usual sleep={sleep} />
      {nights.length ? <Timeline nights={nights} /> : <span style={{ color: "var(--color-neutral-400)" }}>No nights yet. Tap “Going to bed” and “I’m up” in the Now bar, or log last night {here ? "below" : <>in Insights → Sleep</>}.</span>}
      <LearnedSleep sleep={sleep} />
    </Section>
  )
}

function Usual({ sleep }: { sleep: Schemas["SleepOut"] }) {
  const nights = sleep.nights ?? []
  const bed = usual(nights.flatMap((n) => (n.bed ? [n.bed] : [])), true)
  const up = usual(nights.flatMap((n) => (n.up ? [n.up] : [])), false)
  const routine = middle(nights.flatMap((n) => (n.routine_min != null ? [n.routine_min] : [])))
  const wind = middle(nights.flatMap((n) => (n.wind_down_min != null ? [n.wind_down_min] : [])))
  const quarter = (m: number) => dur(Math.max(15, Math.round(m / 15) * 15))
  const stats: [string, string][] = [
    [sleep.average_slept_min ? dur(sleep.average_slept_min) : "—", "of sleep a night, lately"],
    [bed ? ampm(bed) : "—", "usually to bed"],
    [up ? ampm(up) : "—", "usually up"],
    [wind != null ? quarter(wind) : "—", "from done with work to bed"],
    [routine != null ? quarter(routine) : "—", "from up to ready to work"],
  ]
  // Naps (29 Oct), once there are any: how many lately, and how long you usually nap.
  const naps = sleep.naps ?? []
  if (naps.length) stats.push([sleep.usual_nap_min ? dur(sleep.usual_nap_min) : String(naps.length), sleep.usual_nap_min ? `a nap, usually (${naps.length} in two weeks)` : `nap${naps.length === 1 ? "" : "s"} in two weeks`])
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
      <div style={{ display: "grid", gridTemplateColumns: "64px minmax(0,1fr) 56px", gap: 10, fontSize: 11.5, color: "var(--color-neutral-500)" }}>
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
            {n.done && <span title="Done with work" style={{ position: "absolute", top: 0, bottom: 0, width: 2, borderRadius: 1, left: `${along(n.date, n.done)}%`, background: "var(--color-neutral-400)" }} />}
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
          <span style={{ width: 2, height: 12, borderRadius: 1, background: "var(--color-neutral-400)" }} /> Done with work
        </span>
        <span style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
          <span style={{ width: 2, height: 12, borderRadius: 1, background: "var(--color-accent-200)" }} /> Ready to work
        </span>
        <span style={{ flex: 1 }} />
        <span className="tnum" style={{ color: "var(--color-neutral-300)" }}>
          {shown ? `${dayLabel(shown.date)}: ${shown.done ? `done ${clock(shown.done)}, ` : ""}${shown.bed ? `bed ${clock(shown.bed)}` : "no bedtime"}, ${shown.up ? `up ${clock(shown.up)}` : "no wake time"}${shown.ready ? `, ready ${clock(shown.ready)}` : ""}${shown.slept_min ? ` · ${dur(shown.slept_min)} asleep, ${dur(shown.planned_min)} planned` : ""}` : "Point at a night for its times"}
        </span>
      </div>
    </div>
  )
}

function LearnedSleep({ sleep }: { sleep: Schemas["SleepOut"] }) {
  const asks = useAsks().filter((a) => a.key === "sleep-times").length // asked in the Inbox (C75)
  const navigate = useNavigate()
  const left = Math.max(0, (sleep.min_nights ?? 4) - (sleep.recorded_nights ?? 0))
  const routines = Object.entries(sleep.routine_min ?? {})
  const weekdays = routines.find(([d]) => WEEKDAY_MORNINGS.includes(d))?.[1]
  const weekend = routines.find(([d]) => !WEEKDAY_MORNINGS.includes(d))?.[1]
  const winds = Object.entries(sleep.wind_down_min ?? {})
  const schoolNight = winds.find(([d]) => SCHOOL_NIGHTS.includes(d))?.[1]
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
          {(sleep.against ?? []).map((a) => (
            <span key={a} style={{ display: "flex", gap: 6, fontSize: 12, color: "var(--fr-warn)" }}>
              <Icon name="warning" size={13} style={{ flex: "none", marginTop: 2 }} />
              <span>{a}. Taking these times leaves a question in your Inbox: your bedtime or the rule.</span>
            </span>
          ))}
          {sleep.suggested && (
            <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <InboxLink n={asks} what="about these times" />
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
        {schoolNight != null && ` Evenings take about ${dur(schoolNight)} from done with work to bed; Friday keeps that time light.`}
      </span>
    </div>
  )
}
