// Insights → Meals: the switch, "Eating now" and "Done eating" (the Now bar's taps, for when you missed one), and
// the last two weeks a day a row: each meal to change or delete, and a meal not recorded to log or say skipped, in a
// card under the row. Eating or skipping a meal ticks off that day's Lunch or Dinner routine. What they say is above.

import { useState } from "react"
import type { Schemas } from "@/api/client"
import { Icon, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useMeals, useSettings } from "@/hooks/queries"
import { clock, dayLabel, dur } from "@/lib/format"
import { addDays, nearestAt } from "@/lib/time"
import { Section } from "@/insights/Section"
import { EditCard, minutesBetween, TimeField } from "./Times"
import { MEAL_HOURS } from "@/lib/ampm"
import { useShell } from "@/shell/ShellContext"
import { addable, mealLabel } from "./mealNames"

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
      <Section title="Your meals" note="The last two weeks. Click a meal to change it, or + to log one you didn’t tap (or skipped).">
        <Days days={days} />
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
          Eating {mealLabel(meals.eating.kind, meals.eating.nth ?? 1).toLowerCase()} since {clock(meals.eating.start ?? "")}
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

/** The last two weeks, a row a day: each meal as a chip, and a faint "+ Lunch" for a meal not recorded; a chip
 * clicked opens its card under the row (`MealCard`). */
function Days({ days }: { days: Schemas["MealDayOut"][] }) {
  const { today } = useShell()
  // "<date>/<meal id>", "<date>/+<kind>" for a meal not recorded, or "<date>/*<kind>" for another of one eaten
  const [open, setOpen] = useState<string | null>(null)
  const [shown, setShown] = useState<string | null>(null) // a day with nothing recorded, its "+" choices out
  const [more, setMore] = useState<string | null>(null) // a day whose "Another…" choices are out
  const byDate = new Map(days.map((d) => [d.date, d.meals ?? []]))
  const dates = Array.from({ length: 14 }, (_, n) => addDays(today, -n))
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {dates.map((date) => {
        const meals = [...(byDate.get(date) ?? [])].sort((a, b) => (a.start ?? "").localeCompare(b.start ?? ""))
        const { missing, another } = addable(meals)
        const here = open?.startsWith(`${date}/`) ? open.slice(date.length + 1) : null
        const adding = !!here && (here.startsWith("+") || here.startsWith("*"))
        const meal = here && !adding ? meals.find((m) => String(m.id) === here) : undefined
        const kind = adding ? (here!.slice(1) as MealKind) : meal ? (meal.kind as MealKind) : null
        const nth = here?.startsWith("*") ? (another.find((a) => a.kind === kind)?.nth ?? 2) : (meal?.nth ?? 1)
        return (
          <div key={date} className="fr-row" style={{ padding: "6px 0", fontSize: 12 }}>
            <div style={{ display: "grid", gridTemplateColumns: "92px minmax(0,1fr)", gap: 8, alignItems: "center" }}>
              <span style={{ color: "var(--color-neutral-400)" }}>{date === today ? "Today" : dayLabel(date)}</span>
              <span style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                {meals.map((m) => (
                  <MealChip key={m.id} meal={m} on={here === String(m.id)} onClick={() => setOpen(here === String(m.id) ? null : `${date}/${m.id}`)} />
                ))}
                {!meals.length && shown !== date && (
                  <>
                    <span style={{ color: "var(--color-neutral-500)" }}>Nothing recorded</span>
                    <button className="fr-link" onClick={() => setShown(date)} style={{ fontSize: 12 }}>
                      Log a meal
                    </button>
                  </>
                )}
                {(meals.length > 0 || shown === date) &&
                  [...missing, "snack" as const].map((k) => (
                    <AddChip key={k} label={named(k)} on={here === `+${k}`} title={k === "snack" ? "Log a snack" : `Log ${k}, or that you skipped it`} onClick={() => setOpen(here === `+${k}` ? null : `${date}/+${k}`)} />
                  ))}
                {meals.length > 0 && another.length > 0 && more !== date && (
                  <button className="fr-link" onClick={() => setMore(date)} title="Log another of a meal you had: a second dinner" style={{ fontSize: 12 }}>
                    Another…
                  </button>
                )}
                {more === date &&
                  another.map((a) => (
                    <AddChip key={`*${a.kind}`} label={mealLabel(a.kind, a.nth)} on={here === `*${a.kind}`} title={`Log a ${mealLabel(a.kind, a.nth).toLowerCase()}`} onClick={() => setOpen(here === `*${a.kind}` ? null : `${date}/*${a.kind}`)} />
                  ))}
              </span>
            </div>
            {kind && <MealCard key={open} date={date} kind={kind} nth={nth} meal={meal} onClose={() => (setOpen(null), setMore(null))} />}
          </div>
        )
      })}
    </div>
  )
}

function AddChip({ label, on, title, onClick }: { label: string; on: boolean; title: string; onClick: () => void }) {
  return (
    <button
      className="fr-plain fr-hover-text"
      onClick={onClick}
      title={title}
      style={{ display: "inline-flex", gap: 4, alignItems: "center", padding: "3px 8px", borderRadius: 999, color: on ? "var(--color-text)" : "var(--color-neutral-500)", boxShadow: "inset 0 0 0 1px color-mix(in srgb, var(--color-text) 10%, transparent)" }}
    >
      <Icon name="plus" size={11} />
      {label}
    </button>
  )
}

function MealChip({ meal, on, onClick }: { meal: Schemas["MealOut"]; on: boolean; onClick: () => void }) {
  const label = mealLabel(meal.kind, meal.nth ?? 1)
  return (
    <button
      className="fr-plain tnum"
      onClick={onClick}
      title="Change it"
      aria-expanded={on}
      style={{ display: "inline-flex", gap: 6, alignItems: "center", padding: "3px 9px", borderRadius: 999, background: on ? "color-mix(in srgb, var(--color-accent) 18%, transparent)" : "color-mix(in srgb, var(--color-text) 6%, transparent)", color: "var(--color-neutral-200)" }}
    >
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
      <Icon name="pencil-simple" size={11} style={{ color: "var(--color-neutral-600)" }} />
    </button>
  )
}

const USUAL: Record<MealKind, [string, string]> = { breakfast: ["08:30", "08:50"], lunch: ["12:30", "13:00"], dinner: ["19:00", "19:40"], snack: ["16:00", "16:10"] }

/** One meal's card: when you started and finished, with how long that is; Save, Delete and Cancel. A meal you skipped
 * can be eaten after all; one not recorded can be logged, or said skipped. */
function MealCard({ date, kind, nth = 1, meal, onClose }: { date: string; kind: MealKind; nth?: number; meal?: Schemas["MealOut"]; onClose: () => void }) {
  const settings = useSettings().data as Record<string, { day_start?: string }> | undefined
  const dayStart = settings?.time?.day_start ?? "04:00"
  const log = useCommand("meal_log", { label: (o) => o.result.message ?? "Saved" })
  const edit = useCommand("meal_edit", { label: (o) => o.result.message ?? "Saved" })
  const remove = useCommand("meal_remove", { label: (o) => o.result.message ?? "Removed" })
  const skip = useCommand("meal_skip", { label: (o) => o.result.message ?? "Saved" })
  const eaten = meal && !meal.skipped ? meal : undefined
  const [from, setFrom] = useState(eaten?.start?.slice(11, 16) ?? USUAL[kind][0])
  const [to, setTo] = useState(eaten?.end?.slice(11, 16) ?? USUAL[kind][1])
  const [busy, setBusy] = useState(false)
  const label = mealLabel(kind, nth)
  const minutes = minutesBetween(from, to)
  // A meal in the small hours (before your day starts) is the night of its day: the next date.
  const at = (time: string) => `${time < dayStart ? addDays(date, 1) : date}T${time}`
  const run = async (act: () => Promise<unknown>) => {
    setBusy(true)
    const ok = await act()
    setBusy(false)
    if (ok !== undefined) onClose()
  }
  const save = () =>
    run(async () => {
      if (eaten?.start && eaten.end) {
        const start = from !== eaten.start.slice(11, 16) ? nearestAt(eaten.start, from) : undefined
        const end = to !== eaten.end.slice(11, 16) ? nearestAt(eaten.end, to) : undefined
        return start || end ? edit({ id: eaten.id, start, end }) : true
      }
      if (eaten) return edit({ id: eaten.id, start: nearestAt(eaten.start ?? at(from), from) })
      // Eaten after all: the skip goes, the meal is logged.
      if (meal?.skipped && !(await remove({ id: meal.id }))) return undefined
      return log({ kind, start: at(from), end: at(to) })
    })
  const title = `${label} · ${dayLabel(date)}`
  return (
    <EditCard
      title={title}
      said={meal?.skipped ? "You said you skipped it" : minutes ? `${dur(minutes)}` : undefined}
      saveLabel={eaten ? "Save" : meal?.skipped ? "I ate it after all" : "Log it"}
      canSave={!!from && (!!to || (!!eaten && !eaten.end)) && (minutes === null || (minutes > 0 && minutes <= 240))}
      busy={busy}
      onSave={save}
      onCancel={onClose}
      extra={
        meal ? (
          <button className="btn btn-ghost" disabled={busy} onClick={() => run(() => remove({ id: meal.id }))} style={{ fontSize: 12, color: "var(--fr-due)" }}>
            <Icon name="trash" size={12} />
            {meal.skipped ? "Not skipped after all" : "Delete this meal"}
          </button>
        ) : kind !== "snack" && nth === 1 ? ( // another dinner isn't one to skip: you had the first
          <button className="btn btn-ghost" disabled={busy} onClick={() => run(() => skip({ kind, date }))} style={{ fontSize: 12 }}>
            I skipped it
          </button>
        ) : null
      }
    >
      <TimeField label="Started" value={from} onChange={setFrom} expect={kind === "snack" || nth > 1 ? undefined : { hours: MEAL_HOURS[kind] }} />
      {(!eaten || eaten.end) && <TimeField label="Finished" value={to} onChange={setTo} expect={{ after: from }} />}
      {eaten && !eaten.end && <span style={{ fontSize: 12, color: "var(--color-neutral-400)", paddingBottom: 6 }}>Still eating: “Done eating” ends it</span>}
    </EditCard>
  )
}
