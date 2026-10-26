// Sleep & meals → Meals: the switch, "Eating now" and "Done eating" (the Now bar's taps, for when you missed one), a
// meal to log after the fact or a skipped one, and every meal of the last two weeks with its times to change or take
// back. Eating or skipping a meal ticks off that day's Lunch or Dinner routine. What they say is in Insights.

import { useState } from "react"
import type { Schemas } from "@/api/client"
import { Icon, Seg, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useMeals, useSettings } from "@/hooks/queries"
import { clock, dayLabel, dur, weekday } from "@/lib/format"
import { addDays, nearestAt } from "@/lib/time"
import { Section } from "@/insights/Section"
import { useShell } from "@/shell/ShellContext"

export const KINDS = ["breakfast", "lunch", "dinner", "snack"] as const
export type MealKind = (typeof KINDS)[number]
export const MEAL_ICON: Record<string, string> = { breakfast: "coffee", lunch: "bowl-food", dinner: "fork-knife", snack: "cookie" }
export const named = (kind: string) => kind[0].toUpperCase() + kind.slice(1)

export function MealLog() {
  const settings = useSettings().data as Record<string, { on?: boolean }> | undefined
  const meals = useMeals().data
  const save = useCommand("settings_set", { label: () => "Saved" })
  const on = !!settings?.meal_tracking?.on
  const toggle = (
    <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <span style={{ color: on ? "var(--color-text)" : "var(--color-neutral-400)", fontSize: 12 }}>{on ? "On" : "Off"}</span>
      <Switch on={on} onToggle={() => save({ key: "meal_tracking", value: { ...settings?.meal_tracking, on: !on } })} label="Track my meals" />
    </span>
  )
  if (!on || !meals?.on)
    return (
      <Section title="Track my meals" note="Off. Turn it on and the Now bar offers “Eating now” around mealtimes; Friday learns when you eat, for how long and what you skip, and keeps your meal free of work while you eat." right={toggle}>
        <span />
      </Section>
    )
  const days = meals.days ?? []
  return (
    <>
      <Section title="Track my meals" note="Missed a tap in the Now bar? Make it here." right={toggle}>
        <Now meals={meals} />
      </Section>
      <Section title="Log a meal" note="One you ate without tapping, or one you skipped">
        <LogMeal />
      </Section>
      <Section title="Your meals" note="The last two weeks. Click a meal to change its times or take it back.">
        {days.length ? <Days days={days} /> : <span style={{ color: "var(--color-neutral-400)" }}>No meals yet.</span>}
      </Section>
    </>
  )
}

/** Eating now (the meal it's time for stands out), or the meal you're eating and Done eating. */
function Now({ meals }: { meals: Schemas["MealsOut"] }) {
  const start = useCommand("meal_start", { label: (o) => o.result.message ?? "Saved" })
  const end = useCommand("meal_end", { label: (o) => o.result.message ?? "Saved" })
  const skip = useCommand("meal_skip", { label: (o) => o.result.message ?? "Saved" })
  const [busy, setBusy] = useState<string | null>(null)
  const run = async (key: string, act: () => Promise<unknown>) => (setBusy(key), await act(), setBusy(null))
  const spin = (key: string, icon: string) => (busy === key ? <span className="fr-spinner" /> : <Icon name={icon} />)
  if (meals.eating)
    return (
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <span>
          Eating {meals.eating.kind} since {clock(meals.eating.start ?? "")}
        </span>
        <button className="btn btn-primary fr-press" disabled={!!busy} onClick={() => run("end", () => end({}))}>
          {spin("end", "check")}
          Done eating
        </button>
      </div>
    )
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
      <span style={{ color: "var(--color-neutral-400)", marginRight: 4 }}>Eating now:</span>
      {KINDS.map((k) => (
        <button key={k} className={`btn ${meals.next === k ? "btn-primary" : "btn-secondary"} fr-press`} disabled={!!busy} onClick={() => run(k, () => start({ kind: k }))}>
          {spin(k, MEAL_ICON[k])}
          {named(k)}
        </button>
      ))}
      {meals.next && (
        <button className="fr-link" disabled={!!busy} onClick={() => run("skip", () => skip({ kind: meals.next as MealKind }))} style={{ fontSize: 12, marginLeft: 6 }}>
          I’m skipping {meals.next}
        </button>
      )}
    </div>
  )
}

/** Today or any of the two weeks before: a meal from when you started to when you finished, or skipped. */
function LogMeal() {
  const { today } = useShell()
  const settings = useSettings().data as Record<string, { day_start?: string }> | undefined
  const dayStart = settings?.time?.day_start ?? "04:00"
  const log = useCommand("meal_log", { label: (o) => o.result.message ?? "Saved" })
  const skip = useCommand("meal_skip", { label: (o) => o.result.message ?? "Saved" })
  const days = Array.from({ length: 15 }, (_, n) => addDays(today, -n))
  const [day, setDay] = useState(today)
  const [kind, setKind] = useState<MealKind>("lunch")
  const [from, setFrom] = useState("12:30")
  const [to, setTo] = useState("13:00")
  const [busy, setBusy] = useState(false)
  // A meal in the small hours (before your day starts) is the night of the day picked: the next date.
  const at = (time: string) => `${time < dayStart ? addDays(day, 1) : day}T${time}`
  const field = (label: string, value: string, set: (v: string) => void) => (
    <label style={{ display: "flex", flexDirection: "column", gap: 3, fontSize: 11, color: "var(--color-neutral-400)" }}>
      {label}
      <input type="time" className="input" value={value} onChange={(e) => set(e.target.value)} style={{ width: 120, padding: "4px 8px", minHeight: 0, fontSize: 13 }} />
    </label>
  )
  return (
    <div className="fr-well" style={{ display: "flex", alignItems: "flex-end", gap: 14, flexWrap: "wrap", padding: "12px 14px" }}>
      <label style={{ display: "flex", flexDirection: "column", gap: 3, fontSize: 11, color: "var(--color-neutral-400)" }}>
        Day
        <select className="input" value={day} onChange={(e) => setDay(e.target.value)} style={{ width: 150, padding: "4px 8px", minHeight: 0, fontSize: 13 }}>
          {days.map((d, n) => (
            <option key={d} value={d}>
              {n === 0 ? "Today" : n === 1 ? `Yesterday (${weekday(d)})` : dayLabel(d)}
            </option>
          ))}
        </select>
      </label>
      <label style={{ display: "flex", flexDirection: "column", gap: 3, fontSize: 11, color: "var(--color-neutral-400)" }}>
        Meal
        <Seg options={KINDS.map((k) => ({ value: k, label: named(k) }))} value={kind} onPick={setKind} />
      </label>
      {field("Started", from, setFrom)}
      {field("Finished", to, setTo)}
      <button className="btn btn-primary fr-press" disabled={busy || !from || !to} onClick={async () => (setBusy(true), await log({ kind, start: at(from), end: at(to) }), setBusy(false))} style={{ fontSize: 12 }}>
        {busy ? <span className="fr-spinner" /> : <Icon name="check" />}
        Log it
      </button>
      {kind !== "snack" && (
        <button className="btn btn-secondary fr-press" disabled={busy} onClick={async () => (setBusy(true), await skip({ kind, date: day }), setBusy(false))} style={{ fontSize: 12 }}>
          Skipped it
        </button>
      )}
    </div>
  )
}

function Days({ days }: { days: Schemas["MealDayOut"][] }) {
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {days.map((d) => (
        <div key={d.date} className="fr-row" style={{ display: "grid", gridTemplateColumns: "92px minmax(0,1fr)", gap: 8, alignItems: "center", padding: "6px 0", fontSize: 12 }}>
          <span style={{ color: "var(--color-neutral-400)" }}>{dayLabel(d.date)}</span>
          <span style={{ display: "flex", gap: 14, flexWrap: "wrap", alignItems: "center" }}>
            {(d.meals ?? []).map((m) => (
              <MealTimes key={m.id} meal={m} />
            ))}
          </span>
        </div>
      ))}
    </div>
  )
}

/** One meal: its times, or (clicked) the times to change and the bin. */
function MealTimes({ meal }: { meal: Schemas["MealOut"] }) {
  const edit = useCommand("meal_edit", { label: (o) => o.result.message ?? "Moved" })
  const remove = useCommand("meal_remove", { label: (o) => o.result.message ?? "Removed" })
  const [editing, setEditing] = useState(false)
  const [from, setFrom] = useState(meal.start?.slice(11, 16) ?? "")
  const [to, setTo] = useState(meal.end?.slice(11, 16) ?? "")
  const label = named(meal.kind)
  if (editing)
    return (
      <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
        <span style={{ color: "var(--color-neutral-400)" }}>{label}</span>
        {!meal.skipped && (
          <>
            <input type="time" aria-label={`${label} start`} className="input" value={from} onChange={(e) => setFrom(e.target.value)} style={{ width: 96, padding: "2px 6px", minHeight: 0, fontSize: 12 }} />
            {meal.end && <input type="time" aria-label={`${label} end`} className="input" value={to} onChange={(e) => setTo(e.target.value)} style={{ width: 96, padding: "2px 6px", minHeight: 0, fontSize: 12 }} />}
            <button
              className="btn btn-icon btn-ghost"
              aria-label="Save"
              onClick={() => {
                const start = meal.start && from !== meal.start.slice(11, 16) ? nearestAt(meal.start, from) : undefined
                const end = meal.end && to !== meal.end.slice(11, 16) ? nearestAt(meal.end, to) : undefined
                if (start || end) edit({ id: meal.id, start, end })
                setEditing(false)
              }}
              style={{ width: 22, height: 22 }}
            >
              <Icon name="check" size={12} />
            </button>
          </>
        )}
        <button className="btn btn-icon btn-ghost" onClick={() => (remove({ id: meal.id }), setEditing(false))} aria-label={`Remove ${meal.kind}`} style={{ width: 22, height: 22 }}>
          <Icon name="trash" size={12} />
        </button>
        <button className="btn btn-icon btn-ghost" onClick={() => setEditing(false)} aria-label="Cancel" style={{ width: 22, height: 22 }}>
          <Icon name="x" size={12} />
        </button>
      </span>
    )
  return (
    <button className="fr-plain fr-hover-text tnum" onClick={() => setEditing(true)} title="Click to change" style={{ display: "inline-flex", gap: 6, alignItems: "center", color: "var(--color-neutral-300)" }}>
      <Icon name={MEAL_ICON[meal.kind] ?? "fork-knife"} size={13} style={{ color: "var(--color-neutral-500)" }} />
      {meal.skipped ? (
        <span style={{ color: "var(--color-neutral-500)" }}>{label} skipped</span>
      ) : (
        <span>
          {label} {clock(meal.start ?? "")}
          {meal.end ? `–${clock(meal.end)}` : " (eating)"}
          {meal.minutes ? <span style={{ color: "var(--color-neutral-500)" }}> · {dur(meal.minutes)}</span> : null}
        </span>
      )}
    </button>
  )
}
