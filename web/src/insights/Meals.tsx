// Meals (Insights → Meals, above the meals to log or put right): what your tracked meals say, while tracking is
// on (the switch is below it). When you usually eat each meal, how much that moves, how long it takes and how often you skip it,
// weekdays and weekends apart; the last two weeks on one timeline from 6am to 2am; and what's learned offered with one
// click each: a routine's length when you take longer or shorter, its window when you eat well outside it, and a meal
// planned when you have it most days (or no longer, when you mostly skip it). Meals a rule leaves to Friday ("Let
// Friday decide breakfast") get no button: Friday applies those itself that night, and says so.

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

/** `here`: on Insights → Meals itself, with no link to it, and nothing while tracking is off (its switch is below). */
export function MealsSection({ here = false }: { here?: boolean }) {
  const meals = useMeals().data
  const navigate = useNavigate()
  const log = here ? undefined : (
    <button className="fr-link" onClick={() => navigate("/insights?tab=meals")} style={{ fontSize: 12 }}>
      {meals?.on ? "Log or fix a meal" : "Turn it on in Insights → Meals"}
    </button>
  )
  if (!meals?.on && here) return null
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
      {days.length ? <Timeline days={days} /> : <span style={{ color: "var(--color-neutral-400)" }}>No meals yet. Tap “Eating now” in the Now bar around a mealtime, or log one {here ? "below" : <>in Insights → Meals</>}.</span>}
      <Offers meals={meals} />
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
      <div style={{ display: "grid", gridTemplateColumns: "64px minmax(0,1fr)", gap: 10, fontSize: 11.5, color: "var(--color-neutral-500)" }}>
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

function Offers({ meals }: { meals: Schemas["MealsOut"] }) {
  const length = useCommand("meal_use_length", { label: (o) => o.result.message ?? "Saved" })
  const time = useCommand("meal_use_time", { label: (o) => o.result.message ?? "Saved" })
  const plan = useCommand("meal_plan", { label: (o) => o.result.message ?? "Saved" })
  const changes = meals.changes ?? []
  const times = meals.times ?? []
  const plans = meals.plans ?? []
  if (!changes.length && !times.length && !plans.length) return null
  type Kind = "breakfast" | "lunch" | "dinner"
  const row = { display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", fontSize: 13 } as const
  const button = { fontSize: 12, padding: "2px 10px" }
  const decided = new Set(meals.decided ?? [])
  // A meal you let Friday decide: what's offered happens tonight, without a click.
  const act = (kind: string, label: string, onClick: () => void) =>
    decided.has(kind) ? (
      <span className="fr-kicker">Friday does this tonight</span>
    ) : (
      <button className="btn btn-secondary fr-press" onClick={onClick} style={button}>
        {label}
      </button>
    )
  return (
    <div className="fr-well" style={{ display: "flex", flexDirection: "column", gap: 8, padding: "12px 14px" }}>
      <span style={{ display: "flex", gap: 8, alignItems: "center", fontWeight: 500 }}>
        <Icon name="sparkle" size={14} style={{ color: "var(--color-accent-300)" }} />
        What Friday learned from your meals
      </span>
      {changes.map((c) => (
        <span key={`length-${c.kind}`} style={row}>
          <span>
            {named(c.kind)} takes you about <b style={{ fontWeight: 500 }}>{dur(c.usual_min)}</b>
            <span style={{ color: "var(--color-neutral-500)" }}>; Friday plans {dur(c.planned_min)}</span>
          </span>
          {act(c.kind, `Plan ${dur(Math.max(15, Math.round(c.usual_min / 15) * 15))}`, () => length({ kind: c.kind as Kind }))}
        </span>
      ))}
      {times.map((t) => (
        <span key={`time-${t.kind}`} style={row}>
          <span>
            You usually have {t.kind} around <b style={{ fontWeight: 500 }}>{ampm(t.usual_start)}</b>
            <span style={{ color: "var(--color-neutral-500)" }}>; it's planned {ampm(t.start)}–{ampm(t.end)}</span>
          </span>
          {act(t.kind, `Plan ${ampm(t.new_start)}–${ampm(t.new_end)}`, () => time({ kind: t.kind as Kind }))}
        </span>
      ))}
      {plans.map((p) => (
        <span key={`plan-${p.kind}`} style={row}>
          {p.plan ? (
            <span>
              You have {p.kind} most days, around <b style={{ fontWeight: 500 }}>{ampm(p.usual_start ?? "08:00")}</b>
              <span style={{ color: "var(--color-neutral-500)" }}>; Friday doesn't plan it</span>
            </span>
          ) : (
            <span>
              You usually skip {p.kind}
              <span style={{ color: "var(--color-neutral-500)" }}>; Friday still plans it</span>
            </span>
          )}
          {act(p.kind, p.plan ? `Plan ${p.kind}` : "Stop planning it", () => plan({ kind: p.kind as Kind, plan: p.plan }))}
        </span>
      ))}
    </div>
  )
}
