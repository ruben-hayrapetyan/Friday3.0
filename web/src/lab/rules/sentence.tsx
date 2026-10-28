// A rule as a sentence with its parameters editable in place, by rule type. Types without a template fall back to
// the sentence the Rules page already shows.

import type { CSSProperties, ReactNode } from "react"
import { TimeInput } from "@/components/fr/TimeInput"
import { hours } from "@/lib/format"
import type { RuleSpec } from "./model"

const INLINE: CSSProperties = {
  font: "inherit",
  color: "var(--color-accent-300)",
  background: "transparent",
  border: 0,
  borderBottom: "1px dashed var(--color-accent-300)",
  padding: "0 2px",
  minHeight: 0,
}

export function Sentence({ rule, said, onEdit }: { rule: RuleSpec; said?: string; onEdit: (r: RuleSpec) => void }) {
  const p = rule.params
  const set = (k: string, v: unknown) => onEdit({ ...rule, params: { ...p, [k]: v } })
  const time = (k: string, fallback = "") => <TimeField value={String(p[k] ?? fallback)} onChange={(v) => set(k, v)} />
  const span = (k: string, fallback: string) => <HoursField value={String(p[k] ?? fallback)} onChange={(v) => set(k, v)} />
  switch (rule.type) {
    case "late_night":
      return <>Start winding down at {time("gradient_start", "22:00")}; work past bedtime costs much more</>
    case "deep_run":
      return <>No more than {span("threshold", "3h")} of focused work in a row</>
    case "reserve":
      return (
        <>
          Keep {span("free", "2h")} free between {time("start", "18:00")} and {time("end", "23:00")} on <DaysField params={p} onEdit={(params) => onEdit({ ...rule, params })} />
        </>
      )
    case "daily_load":
      return <>Aim for at most {span("threshold", "8h")} of work a day</>
    case "even_load":
      return <>Spread hard work evenly before it’s due, but no thinner than {span("floor", "3h")} a day</>
    case "finish_early":
      return (
        <>
          Finish work <NumberField value={Number(p.days ?? 2)} min={0} max={14} onChange={(v) => set("days", v)} /> {Number(p.days ?? 2) === 1 ? "day" : "days"} before it’s due
          {exceptions(rule)}
        </>
      )
    case "buffer":
      return (
        <>
          Leave <NumberField value={minutes(String(p.minutes ?? "0m"))} min={0} max={120} step={5} onChange={(v) => set("minutes", `${v}m`)} /> minutes between blocks
        </>
      )
    case "time_preference":
      return (
        <>
          <select value={p.price === "forbid" ? "forbid" : "avoid"} onChange={(e) => set("price", e.target.value === "forbid" ? "forbid" : 1)} style={INLINE}>
            <option value="avoid">Avoid</option>
            <option value="forbid">Never plan</option>
          </select>{" "}
          {subject(rule)}
          {p.start !== undefined && p.start !== null && (
            <>
              {" "}
              from {time("start")} to {time("end")}
            </>
          )}{" "}
          on <DaysField params={p} onEdit={(params) => onEdit({ ...rule, params })} />
        </>
      )
    default:
      return <>{said ?? rule.name.replace(/_/g, " ")}</>
  }
}

function exceptions(rule: RuleSpec): ReactNode {
  const except = (rule.scope?.except_preset as string[] | undefined) ?? []
  return except.length ? <span style={{ color: "var(--color-neutral-500)" }}>, except {except.join(", ")}</span> : null
}

function subject(rule: RuleSpec): string {
  const scope = rule.scope ?? {}
  const named = [scope.tags, scope.area, scope.preset, scope.title].flat().filter(Boolean)
  return named.length ? named.join(" or ") : "work"
}

const minutes = (text: string) => Math.round(hours(text) * 60)

function TimeField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return <TimeInput step={900} value={value} onChange={(t) => t && onChange(t)} className="" style={{ ...INLINE, width: 90 }} />
}

function HoursField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <>
      <NumberField value={hours(value)} min={0.5} max={16} step={0.5} onChange={(v) => onChange(`${v}h`)} /> h
    </>
  )
}

function NumberField({ value, min, max, step = 1, onChange }: { value: number; min: number; max: number; step?: number; onChange: (v: number) => void }) {
  return (
    <input
      type="number"
      value={value}
      min={min}
      max={max}
      step={step}
      onChange={(e) => {
        const v = Number(e.target.value)
        if (e.target.value !== "" && v >= min && v <= max) onChange(v)
      }}
      style={{ ...INLINE, width: 54, textAlign: "center" }}
    />
  )
}

const WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
const WEEKEND = ["sat", "sun"]
const same = (a: unknown, b: string[]) => JSON.stringify(a) === JSON.stringify(b)

/** `days` and `days_except` read as one choice; a mix the menu can't say is kept and shown as it is. */
export function daysChoice(p: Record<string, unknown>): string {
  if (!p.days && !p.days_except) return "every"
  if (same(p.days_except, WEEKEND)) return "weekdays"
  if (same(p.days, WEEKEND)) return "weekends"
  if (Array.isArray(p.days) && p.days.length === 1) return String(p.days[0])
  return "custom"
}

export function withDays(p: Record<string, unknown>, choice: string): Record<string, unknown> {
  const rest = { ...p, days: null, days_except: null }
  if (choice === "weekdays") return { ...rest, days_except: WEEKEND }
  if (choice === "weekends") return { ...rest, days: WEEKEND }
  if (WEEKDAYS.includes(choice)) return { ...rest, days: [choice] }
  return rest
}

function DaysField({ params, onEdit }: { params: Record<string, unknown>; onEdit: (p: Record<string, unknown>) => void }) {
  const choice = daysChoice(params)
  return (
    <select value={choice} onChange={(e) => onEdit(withDays(params, e.target.value))} style={INLINE}>
      <option value="every">every day</option>
      <option value="weekdays">weekdays</option>
      <option value="weekends">weekends</option>
      {WEEKDAYS.map((d) => (
        <option key={d} value={d}>
          {d[0].toUpperCase() + d.slice(1)}s
        </option>
      ))}
      {choice === "custom" && <option value="custom">{[params.days ?? `all but ${params.days_except}`].flat().join(", ")}</option>}
    </select>
  )
}
