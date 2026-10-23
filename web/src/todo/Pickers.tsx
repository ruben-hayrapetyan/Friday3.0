// The field pickers the add box and the item detail share (v22): a list of options, a due date (month grid, quick
// picks and a time), a length, and a repeat.

import { useState } from "react"
import { Chip, Icon, Seg } from "@/components/fr/controls"
import { ampm, dur, parseLength, weekday } from "@/lib/format"
import { addDays, toMin } from "@/lib/time"

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
const DOWS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

export interface PickOption<T> {
  value: T
  label: string
  swatch?: string
}

export function ListPicker<T>({ options, value, onPick }: { options: PickOption<T>[]; value: T; onPick: (v: T) => void }) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
      {options.map((o) => (
        <Chip key={o.label} on={o.value === value} swatch={o.swatch} onClick={() => onPick(o.value)}>
          {o.label}
        </Chip>
      ))}
    </div>
  )
}

const dowOf = (date: string) => (new Date(toMin(date) * 60000).getUTCDay() + 6) % 7 // Monday is 0

/** A due date and time; `value` is local `YYYY-MM-DDTHH:MM` or null. */
export function DuePicker({ value, today, onPick, stacked }: { value: string | null; today: string; onPick: (v: string | null) => void; stacked?: boolean }) {
  const [month, setMonth] = useState((value ?? today).slice(0, 7))
  const time = value?.slice(11, 16) ?? "23:59"
  const date = value?.slice(0, 10) ?? null
  const first = `${month}-01`
  const lead = dowOf(first)
  const cells = Array.from({ length: 42 }, (_, i) => addDays(first, i - lead)).filter((d, i) => i < 35 || d.startsWith(month))
  const weeks = Array.from({ length: cells.length / 7 }, (_, w) => cells.slice(w * 7, w * 7 + 7))
  const pick = (d: string) => onPick(`${d}T${time}`)
  const friday = addDays(today, (4 - dowOf(today) + 7) % 7 || 7)
  const quick: [string, string | null][] = [
    ["Today", today],
    ["Tomorrow", addDays(today, 1)],
    [`${weekday(friday)} ${Number(friday.slice(8, 10))}`, friday],
    ["In a week", addDays(today, 7)],
    ["No due date", null],
  ]
  const shift = (by: number) => {
    const [y, m] = month.split("-").map(Number)
    const d = new Date(Date.UTC(y, m - 1 + by, 1))
    setMonth(d.toISOString().slice(0, 7))
  }
  return (
    <div style={{ display: "grid", gridTemplateColumns: stacked ? "1fr" : "auto minmax(0,1fr)", gap: 18, alignItems: "start" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", paddingBottom: 4, width: 7 * 35 }}>
          <button className="btn btn-icon btn-ghost" onClick={() => shift(-1)} disabled={month <= today.slice(0, 7)} aria-label="Previous month" style={{ width: 26, height: 26, color: "var(--color-neutral-300)" }}>
            <Icon name="caret-left" />
          </button>
          <span style={{ fontSize: 13, fontWeight: 500 }}>
            {MONTHS[Number(month.slice(5, 7)) - 1]} {month.slice(0, 4)}
          </span>
          <button className="btn btn-icon btn-ghost" onClick={() => shift(1)} aria-label="Next month" style={{ width: 26, height: 26, color: "var(--color-neutral-300)" }}>
            <Icon name="caret-right" />
          </button>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 32px)", gap: 3, fontSize: 11, color: "var(--color-neutral-500)", textAlign: "center" }}>
          {DOWS.map((d) => (
            <span key={d}>{d.slice(0, 2)}</span>
          ))}
        </div>
        {weeks.map((w) => (
          <div key={w[0]} style={{ display: "grid", gridTemplateColumns: "repeat(7, 32px)", gap: 3 }}>
            {w.map((d) => {
              const on = d === date
              const past = d < today
              return (
                <button
                  key={d}
                  className="tnum"
                  disabled={past}
                  onClick={() => pick(d)}
                  title={d}
                  style={{
                    opacity: past ? 0.3 : d.startsWith(month) ? 1 : 0.45,
                    height: 30,
                    border: 0,
                    borderRadius: 6,
                    background: on ? "var(--color-accent)" : "transparent",
                    color: on ? "var(--fr-ink)" : "var(--color-text)",
                    boxShadow: d === today && !on ? "inset 0 0 0 1px var(--color-accent-500)" : "none",
                    font: "inherit",
                    fontSize: 12,
                    cursor: past ? "default" : "pointer",
                  }}
                >
                  {Number(d.slice(8, 10))}
                </button>
              )
            })}
          </div>
        ))}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 12, minWidth: 0 }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {quick.map(([label, d]) => (
            <Chip key={label} on={d === date} onClick={() => (d ? pick(d) : onPick(null))}>
              {label}
            </Chip>
          ))}
        </div>
        <label style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12, color: "var(--color-neutral-400)" }}>
          Time
          <input type="time" step={900} className="input" value={time} disabled={!date} onChange={(e) => date && onPick(`${date}T${e.target.value || "23:59"}`)} style={{ width: 120, padding: "4px 8px", minHeight: 0 }} />
        </label>
        <span style={{ fontSize: 13 }}>{dueSummary(value, today)}</span>
      </div>
    </div>
  )
}

export function dueSummary(value: string | null, today: string): string {
  if (!value) return "No due date. Friday fits it in where it costs least."
  const date = value.slice(0, 10)
  const days = Math.round((toMin(date) - toMin(today)) / 1440)
  const away = days === 0 ? "today" : days === 1 ? "tomorrow" : `in ${days} days`
  return `Due ${weekday(date)} ${Number(date.slice(8, 10))} ${MONTHS[Number(date.slice(5, 7)) - 1].slice(0, 3)}, ${ampm(value)} (${away})`
}

/** A length typed as people say it ("45", "1h30", "an hour and a half", "2–3 hours"; personal's reader, COMBINED.md
 * 42), with a live reading under it; it settles on Enter or leaving the box. */
export function LengthInput({ value, onPick, width = 110 }: { value: number | null; onPick: (v: number | null) => void; width?: number }) {
  const [text, setText] = useState<string | null>(null)
  const typed = text === null ? null : parseLength(text)
  const settle = () => {
    if (text !== null && typed !== null) onPick(typed)
    setText(null)
  }
  return (
    <span style={{ display: "inline-flex", flexDirection: "column", gap: 2 }}>
      <input
        className="input tnum"
        value={text ?? (value == null ? "" : dur(value))}
        placeholder="e.g. an hour and a half"
        aria-label="Length"
        aria-invalid={text !== null && text.trim() !== "" && typed === null}
        onChange={(e) => setText(e.target.value)}
        onBlur={settle}
        onKeyDown={(e) => e.key === "Enter" && settle()}
        style={{ width, padding: "4px 8px", minHeight: 0 }}
      />
      {text !== null && text.trim() !== "" && (
        <span className="tnum" style={{ fontSize: 11, color: typed === null ? "var(--fr-due)" : "var(--color-neutral-500)" }}>
          {typed === null ? "Can't read that as a length" : `→ ${dur(typed)}`}
        </span>
      )}
    </span>
  )
}

/** A length in minutes; null leaves it to Friday's estimate. Under 15 minutes still takes one 15-minute slot. */
export function LengthPicker({ value, onPick }: { value: number | null; onPick: (v: number | null) => void }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 12, color: "var(--color-neutral-400)" }}>
        <LengthInput value={value} onPick={onPick} />
        <span className="fr-h tnum" style={{ fontSize: 22, color: "var(--color-text)" }}>
          {value === null ? "Friday decides" : dur(value)}
        </span>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {[5, 15, 30, 60, 120, 180].map((v) => (
          <Chip key={v} on={value === v} onClick={() => onPick(v)}>
            {dur(v)}
          </Chip>
        ))}
        <Chip on={value === null} onClick={() => onPick(null)}>
          Friday decides
        </Chip>
      </div>
      {value !== null && value < 15 && <span style={{ fontSize: 12, color: "var(--color-neutral-500)" }}>Planned in a 15-minute slot, the smallest Friday places.</span>}
    </div>
  )
}

export interface Repeat {
  every: string | null // the add command's shorthand or `rrule:…`; null is once
  perWindow: number | null // "3 times a week": Friday picks the days
}

const RRULE_DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
const NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

/** How often it comes back: a few quick picks, chosen days, or a number of times a week. */
export function RepeatPicker({ value, onPick }: { value: Repeat; onPick: (v: Repeat) => void }) {
  const [mode, setMode] = useState<"days" | "times">(value.perWindow ? "times" : "days")
  const [ends, setEnds] = useState<number | null>(countOf(value.every))
  const days = daysOf(value.every)
  const times = value.perWindow ?? 3
  const withEnd = (every: string | null, count: number | null): string | null => {
    if (!every || !count) return every
    const rule = toRrule(every)
    return rule ? `rrule:${rule};COUNT=${count}` : every
  }
  const setDays = (next: number[]) => onPick({ every: next.length ? withEnd(next.map((d) => NAMES[d]).join(","), ends) : null, perWindow: null })
  const quick: [string, Repeat][] = [
    ["Once", { every: null, perWindow: null }],
    ["Every day", { every: "day", perWindow: null }],
    ["Weekdays", { every: "weekdays", perWindow: null }],
    ["Every week", { every: "week", perWindow: null }],
    ["3× a week", { every: "week", perWindow: 3 }],
  ]
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {quick.map(([label, r]) => (
          <Chip key={label} on={r.every === stripCount(value.every) && r.perWindow === value.perWindow} onClick={() => onPick({ ...r, every: withEnd(r.every, ends) })}>
            {label}
          </Chip>
        ))}
      </div>
      <Seg
        options={[
          { value: "days", label: "On days" },
          { value: "times", label: "Times a week" },
        ]}
        value={mode}
        onPick={setMode}
        onBg
      />
      {mode === "days" ? (
        <div style={{ display: "flex", gap: 4 }}>
          {DOWS.map((d, i) => {
            const on = days.includes(i)
            return (
              <button
                key={d}
                onClick={() => setDays(on ? days.filter((x) => x !== i) : [...days, i].sort())}
                style={{ width: 32, height: 32, border: 0, borderRadius: "50%", background: on ? "var(--color-accent)" : "transparent", color: on ? "var(--fr-ink)" : "var(--color-text)", boxShadow: on ? "none" : "inset 0 0 0 1px color-mix(in srgb, var(--color-text) 10%, transparent)", font: "inherit", fontSize: 12, cursor: "pointer" }}
              >
                {d.slice(0, 1)}
              </button>
            )
          })}
        </div>
      ) : (
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button className="btn btn-icon btn-secondary" onClick={() => onPick({ every: "week", perWindow: Math.max(1, times - 1) })} aria-label="Fewer" style={{ width: 26, height: 26 }}>
            <Icon name="minus" />
          </button>
          <span style={{ minWidth: 90, textAlign: "center" }}>{times} times a week</span>
          <button className="btn btn-icon btn-secondary" onClick={() => onPick({ every: "week", perWindow: Math.min(7, times + 1) })} aria-label="More" style={{ width: 26, height: 26 }}>
            <Icon name="plus" />
          </button>
          <span style={{ fontSize: 12, color: "var(--color-neutral-500)" }}>Friday picks the days</span>
        </div>
      )}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>Ends</span>
        {[null, 5, 10, 20].map((n) => (
          <Chip
            key={String(n)}
            on={ends === n}
            onClick={() => {
              setEnds(n)
              onPick({ every: withEnd(stripCount(value.every), n), perWindow: value.perWindow })
            }}
          >
            {n ? `After ${n} times` : "Never"}
          </Chip>
        ))}
      </div>
      <span style={{ fontSize: 13 }}>{repeatSummary(value)}</span>
    </div>
  )
}

function stripCount(every: string | null): string | null {
  if (!every?.startsWith("rrule:")) return every
  const rule = every.slice(6).replace(/;COUNT=\d+/, "")
  const days = /^FREQ=WEEKLY;BYDAY=([A-Z,]+)$/.exec(rule)
  if (rule === "FREQ=DAILY") return "day"
  if (rule === "FREQ=WEEKLY") return "week"
  if (days) return days[1] === "MO,TU,WE,TH,FR" ? "weekdays" : days[1].split(",").map((d) => NAMES[RRULE_DAYS.indexOf(d)]).join(",")
  return `rrule:${rule}`
}

function toRrule(every: string): string | null {
  if (every === "day") return "FREQ=DAILY"
  if (every === "week") return "FREQ=WEEKLY"
  if (every === "weekdays") return "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
  const names = every.split(",")
  if (names.every((n) => NAMES.includes(n))) return `FREQ=WEEKLY;BYDAY=${names.map((n) => RRULE_DAYS[NAMES.indexOf(n)]).join(",")}`
  return every.startsWith("rrule:") ? every.slice(6) : null
}

function countOf(every: string | null): number | null {
  const m = every ? /COUNT=(\d+)/.exec(every) : null
  return m ? Number(m[1]) : null
}

function daysOf(every: string | null): number[] {
  const plain = stripCount(every)
  if (plain === "weekdays") return [0, 1, 2, 3, 4]
  if (plain === "day") return [0, 1, 2, 3, 4, 5, 6]
  return (plain ?? "")
    .split(",")
    .map((n) => NAMES.indexOf(n))
    .filter((i) => i >= 0)
}

export function repeatSummary(r: Repeat): string {
  if (!r.every) return "Once."
  const count = countOf(r.every)
  const end = count ? `, ${count} times` : ""
  if (r.perWindow) return `${r.perWindow} times a week${end}. Friday picks the days.`
  const plain = stripCount(r.every)
  if (plain === "day") return `Every day${end}.`
  if (plain === "week") return `Every week${end}.`
  if (plain === "weekdays") return `Every weekday${end}.`
  const days = daysOf(r.every)
  return days.length ? `Every ${days.map((d) => DOWS[d]).join(", ")}${end}.` : "Repeats."
}

export function repeatLabel(r: Repeat): string {
  if (!r.every) return "Once"
  if (r.perWindow) return `${r.perWindow}× a week`
  return repeatSummary(r).replace(/\.$/, "").replace(". Friday picks the days", "")
}
