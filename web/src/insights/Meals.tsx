// Meals (Insights): what your tracked meals say, while tracking is on (Sleep & meals has the switch, and the meals to
// log or put right). When you usually eat each meal, how much that moves, how long it takes and how often you skip it,
// weekdays and weekends apart; the last two weeks on one timeline from 6am to 2am; and a routine planned well off the
// length you take, offered the length you take with one click.

import { useState } from "react"
import { useNavigate } from "react-router"
import type { Schemas } from "@/api/client"
import { Icon } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useMeals } from "@/hooks/queries"
import { ampm, clock, dayLabel, dur, weekday } from "@/lib/format"
import { toMin } from "@/lib/time"
import { useLook } from "@/theme/LookProvider"
import { Section } from "./Section"

const FROM = 6 * 60 // the timeline runs from 6am on the day…
const SPAN = 20 * 60 // …to 2am the next
const TICKS = [8, 12, 16, 20, 24] // 8am, 12pm, 4pm, 8pm, 12am
const ORDER = ["breakfast", "lunch", "dinner", "snack"]
const named = (kind: string) => kind[0].toUpperCase() + kind.slice(1)

/** Where a local time falls on a day's meal timeline, 0–100. */
export function mealAlong(date: string, at: string): number {
  const minutes = toMin(at) - toMin(`${date}T00:00`) - FROM
  return Math.max(0, Math.min(100, (minutes / SPAN) * 100))
}

/** "skipped 1 day in 4", "never skipped", or nothing when there's no share yet. */
export function skipSaid(share: number | null | undefined): string {
  if (share == null) return ""
  if (share === 0) return "never skipped"
  if (share >= 0.95) return "always skipped"
  const one = Math.max(2, Math.round(1 / share))
  return share > 0.4 ? `skipped ${Math.round(share * 100)}% of days` : `skipped about 1 day in ${one}`
}

export function MealsSection() {
  const meals = useMeals().data
  const navigate = useNavigate()
  const log = (
    <button className="fr-link" onClick={() => navigate("/body?tab=meals")} style={{ fontSize: 12 }}>
      {meals?.on ? "Log or fix a meal" : "Turn it on in Sleep & meals"}
    </button>
  )
  if (!meals?.on)
    return (
      <Section title="Meals" note="Not tracked. Track your meals and Friday learns when you eat, for how long and what you skip." right={log}>
        <span />
      </Section>
    )
  const days = meals.days ?? []
  return (
    <Section title="Meals" note="When you eat, for how long, and what you skip" right={log}>
      <Usual learned={meals.learned ?? []} minDays={meals.min_days ?? 4} />
      {days.length ? <Timeline days={days} /> : <span style={{ color: "var(--color-neutral-400)" }}>No meals yet. Tap “Eating now” in the Now bar around a mealtime, or log one in Sleep &amp; meals.</span>}
      <Lengths changes={meals.changes ?? []} />
    </Section>
  )
}

function Usual({ learned, minDays }: { learned: Schemas["MealLearnedOut"][]; minDays: number }) {
  const kinds = ORDER.filter((k) => learned.some((x) => x.kind === k))
  if (!kinds.length) return <span className="fr-kicker">Friday says what’s usual for a meal once it has {minDays} days of it (eaten or skipped), weekdays and weekends apart.</span>
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 20 }}>
      {kinds.map((k) => {
        const mine = learned.filter((x) => x.kind === k)
        const main = mine.find((x) => x.group === "weekdays") ?? mine[0]
        const other = mine.find((x) => x !== main)
        return (
          <div key={k} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span className="fr-h tnum" style={{ fontSize: 28 }}>
              {main.usual_start ? ampm(main.usual_start) : "—"}
            </span>
            <span style={{ fontSize: 12, color: "var(--color-neutral-300)" }}>
              {named(k)} on {main.group}
              {main.usual_min ? `, ${dur(main.usual_min)}` : ""}
            </span>
            <span style={{ fontSize: 12, color: "var(--color-neutral-500)", textWrap: "pretty" }}>
              {[main.start_spread_min != null ? (main.start_spread_min <= 20 ? "at a regular time" : `give or take ${dur(Math.round(main.start_spread_min / 2 / 5) * 5 || 5)}`) : "", skipSaid(main.skip_share)].filter(Boolean).join(", ")}
              {other?.usual_start ? `. ${named(other.group)}: ${ampm(other.usual_start)}${other.usual_min ? `, ${dur(other.usual_min)}` : ""}` : ""}
            </span>
          </div>
        )
      })}
    </div>
  )
}

function Timeline({ days }: { days: Schemas["MealDayOut"][] }) {
  const { color } = useLook()
  const paint = color(null, "Routine") // meals are yellow
  const [hover, setHover] = useState<string | null>(null)
  const shown = days.find((d) => d.date === hover)
  const said = (m: Schemas["MealOut"]) => (m.skipped ? `${m.kind} skipped` : `${m.kind} ${clock(m.start ?? "")}${m.end ? `–${clock(m.end)}` : ""}`)
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <div style={{ display: "grid", gridTemplateColumns: "64px minmax(0,1fr)", gap: 10, fontSize: 10.5, color: "var(--color-neutral-500)" }}>
        <span />
        <span style={{ position: "relative", height: 14 }}>
          {TICKS.map((h) => (
            <span key={h} className="tnum" style={{ position: "absolute", left: `${((h * 60 - FROM) / SPAN) * 100}%`, transform: "translateX(-50%)" }}>
              {ampm(`${String(h % 24).padStart(2, "0")}:00`)}
            </span>
          ))}
        </span>
      </div>
      {days.map((d) => (
        <div
          key={d.date}
          onMouseEnter={() => setHover(d.date)}
          onMouseLeave={() => setHover(null)}
          style={{ display: "grid", gridTemplateColumns: "64px minmax(0,1fr)", gap: 10, alignItems: "center", padding: "3px 0", borderRadius: 4, background: hover === d.date ? "color-mix(in srgb, var(--color-text) 5%, transparent)" : undefined }}
        >
          <span style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>
            {weekday(d.date)} {Number(d.date.slice(8, 10))}
          </span>
          <span style={{ position: "relative", height: 16 }}>
            {TICKS.map((h) => (
              <span key={h} style={{ position: "absolute", top: 0, bottom: 0, width: 1, left: `${((h * 60 - FROM) / SPAN) * 100}%`, background: "var(--fr-hairline)" }} />
            ))}
            {(d.meals ?? [])
              .filter((m) => m.start)
              .map((m) => {
                const left = mealAlong(d.date, m.start as string)
                const right = m.end ? mealAlong(d.date, m.end) : left
                return <span key={m.id} title={said(m)} style={{ position: "absolute", top: 4, bottom: 4, left: `${left}%`, width: `max(6px, ${right - left}%)`, borderRadius: 4, background: paint, opacity: m.kind === "snack" ? 0.55 : 1 }} />
              })}
          </span>
        </div>
      ))}
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center", fontSize: 11, color: "var(--color-neutral-500)", paddingTop: 4 }}>
        <span style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
          <span style={{ width: 18, height: 8, borderRadius: 4, background: paint }} /> A meal
        </span>
        <span style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
          <span style={{ width: 18, height: 8, borderRadius: 4, background: paint, opacity: 0.55 }} /> A snack
        </span>
        <span style={{ flex: 1 }} />
        <span className="tnum" style={{ color: "var(--color-neutral-300)" }}>
          {shown ? `${dayLabel(shown.date)}: ${(shown.meals ?? []).map(said).join(", ") || "nothing recorded"}` : "Point at a day for its meals"}
        </span>
      </div>
    </div>
  )
}

function Lengths({ changes }: { changes: Schemas["MealChangeOut"][] }) {
  const use = useCommand("meal_use_length", { label: (o) => o.result.message ?? "Saved" })
  if (!changes.length) return null
  return (
    <div className="fr-well" style={{ display: "flex", flexDirection: "column", gap: 8, padding: "12px 14px" }}>
      <span style={{ display: "flex", gap: 8, alignItems: "center", fontWeight: 500 }}>
        <Icon name="sparkle" size={14} style={{ color: "var(--color-accent-300)" }} />
        Your meals take a different time from what Friday plans
      </span>
      {changes.map((c) => {
        const length = Math.max(15, Math.round(c.usual_min / 15) * 15)
        return (
          <span key={c.kind} style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", fontSize: 13 }}>
            <span>
              {named(c.kind)} takes you about <b style={{ fontWeight: 500 }}>{dur(c.usual_min)}</b>
              <span style={{ color: "var(--color-neutral-500)" }}>; Friday plans {dur(c.planned_min)}</span>
            </span>
            <button className="btn btn-secondary fr-press" onClick={() => use({ kind: c.kind as "breakfast" | "lunch" | "dinner" })} style={{ fontSize: 12, padding: "2px 10px" }}>
              Plan {dur(length)}
            </button>
          </span>
        )
      })}
    </div>
  )
}
