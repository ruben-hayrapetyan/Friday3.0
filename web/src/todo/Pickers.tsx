// The field pickers the add box and the item detail share (v22): a list of options, a due date (typed the way you'd
// say it, with quick picks), a length, and a repeat.

import { useEffect, useState } from "react"
import { query } from "@/api/client"
import { Chip, Icon, Seg } from "@/components/fr/controls"
import { useClock } from "@/hooks/useClock"
import { ampm, dur, parseLength, weekday } from "@/lib/format"
import { addDays, fromMin, toMin } from "@/lib/time"

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

// A day's names as typed, Monday first: read here, at once, the way the server reads them (its next one, today
// included), so "today" and Enter, typed quickly, set the day before the server could answer (28 Oct: "sometimes
// when i type today and hit enter quickly it doesn't save").
const DAY_NAMES = [/^mon(day)?$/, /^tue(s|sday)?$/, /^wed(s|nesday)?$/, /^thu(r|rs|rsday)?$/, /^fri(day)?$/, /^sat(urday)?$/, /^sun(day)?$/]

/** "in 3 days", "in 2 hours", "eod", and the plain days ("today", "tomorrow", "fri", "this fri"), each at the end of
 * the day: what's read without asking the server. Null otherwise. */
export function readRelative(text: string, now: string): string | null {
  const t = text.trim().toLowerCase().replace(/\s+/g, " ")
  const today = now.slice(0, 10)
  if (/^(eod|end of (the )?day|tonight|midnight|today|tod)$/.test(t)) return `${today}T23:59`
  if (/^(tomorrow|tmrw|tmr|tom|tmw)$/.test(t)) return `${addDays(today, 1)}T23:59`
  const day = DAY_NAMES.findIndex((name) => name.test(t.replace(/^this /, "")))
  if (day >= 0) return `${addDays(today, (day - dowOf(today) + 7) % 7)}T23:59`
  const m = /^in\s+(\d+(?:\.\d+)?|an?|one)\s*(m|mins?|minutes?|h|hrs?|hours?|d|days?|w|wks?|weeks?)$/.exec(t)
  if (!m) return null
  const n = /^\d/.test(m[1]) ? Number(m[1]) : 1
  const unit = m[2][0]
  if (unit === "d" || unit === "w") return `${addDays(now.slice(0, 10), n * (unit === "w" ? 7 : 1))}T23:59`
  return fromMin(toMin(now) + Math.round(n * (unit === "h" ? 60 : 1)))
}

/** A typed due date as Friday reads it: a local time, null for "none", undefined while it can't be read. */
export function useDueReading(text: string, now: string): { due: string | null | undefined; reading: boolean } {
  const [read, setRead] = useState<{ for: string; due: string | null | undefined }>({ for: "", due: undefined })
  const t = text.trim()
  const local = !t ? null : /^(none|no due( date)?|clear|-)$/i.test(t) ? null : readRelative(t, now)
  useEffect(() => {
    if (!t || local !== null || /^(none|no due( date)?|clear|-)$/i.test(t)) return
    const timer = setTimeout(
      () =>
        query("parse", { text: `x due ${t}` }).then(
          (out) => {
            const f = out.fields as Record<string, unknown>
            const due = (typeof f.due === "string" ? f.due : typeof f.due_local === "string" ? f.due_local : undefined) as string | undefined
            // A bare time already gone today means tomorrow's, as personal read it.
            setRead({ for: t, due: due && toMin(due) < toMin(now) && due.startsWith(now.slice(0, 10)) && !/today/i.test(t) ? fromMin(toMin(due) + 1440) : due })
          },
          () => setRead({ for: t, due: undefined }),
        ),
      150,
    )
    return () => clearTimeout(timer)
  }, [t, local, now])
  if (!t) return { due: undefined, reading: false }
  if (local !== null || /^(none|no due( date)?|clear|-)$/i.test(t)) return { due: local, reading: false }
  return read.for === t ? { due: read.due, reading: false } : { due: undefined, reading: true }
}

/** A due date typed the way you'd say it ("fri 5pm", "tomorrow", "oct 30", "in 3 days", "none"), read as you type and
 * set on Enter; quick picks for the usual ones. personal's DuePicker, in place of a month grid and a time box.
 * `value` is local `YYYY-MM-DDTHH:MM` or null. */
export function DuePicker(props: {
  value: string | null
  today: string
  onPick: (v: string | null) => void
  onDone?: () => void
  stacked?: boolean
  autoFocus?: boolean
  onEnterEmpty?: () => void // Enter with nothing typed
  onSend?: (due: string | null | undefined) => void // Shift-Enter: the due typed, if it reads, and send what it's for
  placeholder?: string
}) {
  const { value, today, onPick, onDone, autoFocus = true, onEnterEmpty, onSend, placeholder } = props
  const now = fromMin(useClock())
  const [text, setText] = useState("")
  const { due, reading } = useDueReading(text, now)
  // Enter pressed while the server is still reading what was typed: kept, and done once it has read it.
  const [waiting, setWaiting] = useState<"enter" | "send" | null>(null)
  useEffect(() => {
    if (!waiting || reading) return
    setWaiting(null)
    if (waiting === "send") onSend?.(due)
    else if (due !== undefined) set(due)
  })
  const friday = addDays(today, (4 - dowOf(today) + 7) % 7 || 7)
  const quick: [string, string | null][] = [
    ["Today", `${today}T23:59`],
    ["Tomorrow", `${addDays(today, 1)}T23:59`],
    [`${weekday(friday)} ${Number(friday.slice(8, 10))}`, `${friday}T23:59`],
    ["In a week", `${addDays(today, 7)}T23:59`],
    ["No due date", null],
  ]
  const set = (v: string | null) => {
    onPick(v)
    setText("")
    onDone?.()
  }
  const readable = text.trim() !== "" && due !== undefined
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 420 }}>
      <input
        className="input"
        autoFocus={autoFocus}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && e.shiftKey && onSend) {
            e.preventDefault()
            e.stopPropagation()
            if (reading) setWaiting("send")
            else onSend(readable ? due : undefined)
          } else if (e.key === "Enter") {
            e.preventDefault()
            if (!text.trim()) onEnterEmpty?.()
            else if (readable) set(due ?? null)
            else if (reading) setWaiting("enter")
          }
          if (e.key === "Escape") (e.stopPropagation(), text ? setText("") : onDone?.())
        }}
        placeholder={placeholder ?? "fri 5pm, tomorrow, oct 30, in 3 days…"}
        aria-label="Due"
        style={{ padding: "6px 10px", minHeight: 0, fontSize: 13 }}
      />
      <span className="tnum" style={{ fontSize: 12, color: text.trim() && !readable && !reading ? "var(--fr-due)" : "var(--color-neutral-400)" }}>
        {!text.trim() ? (value ? `Now: ${dueSummary(value, today)}` : "No due date yet.") : reading ? "Reading…" : readable ? `→ ${dueSummary(due ?? null, today)} · Enter to set` : "Can’t read that. Try “fri 5pm” or “oct 30”."}
      </span>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {quick.map(([label, v]) => (
          <Chip key={label} on={v === null ? value === null : value?.slice(0, 10) === v.slice(0, 10)} onClick={() => set(v === null || !value ? v : `${v.slice(0, 10)}T${value.slice(11, 16)}`)}>
            {label}
          </Chip>
        ))}
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

/** One press of − or + on a length: a quarter hour under 2 hours, half an hour under 5, an hour above, landing on
 * the step (5h 15m and + is 6h). Never under 15 minutes. */
export function stepLength(min: number, up: boolean): number {
  const step = (up ? min < 120 : min <= 120) ? 15 : (up ? min < 300 : min <= 300) ? 30 : 60
  return Math.max(15, up ? Math.floor(min / step) * step + step : Math.ceil(min / step) * step - step)
}

/** − and + on a length. Presses add up at once and are saved together when you stop (27 Oct: each press read the
 * length before the last one had saved, so six presses made 5h into 5h 15m). */
export function LengthStepper({ value, onSave }: { value: number | null; onSave: (min: number) => void }) {
  const [pending, setPending] = useState<number | null>(null)
  const shown = pending ?? value
  useEffect(() => {
    if (pending === null) return
    const timer = setTimeout(() => (onSave(pending), setPending(null)), SAVE_AFTER_MS)
    return () => clearTimeout(timer)
  }, [pending, onSave])
  const press = (up: boolean) => shown && setPending(stepLength(shown, up))
  return (
    <>
      <button className="btn btn-icon btn-secondary" disabled={!shown || shown <= 15} onClick={() => press(false)} aria-label={shown ? `Less: ${dur(stepLength(shown, false))}` : "Less time"} title={shown ? dur(stepLength(shown, false)) : undefined} style={{ width: 26, height: 26 }}>
        <Icon name="minus" />
      </button>
      <span className="tnum" style={{ minWidth: 56, textAlign: "center", color: pending !== null ? "var(--color-accent-300)" : undefined }}>
        {shown ? dur(shown) : "—"}
      </span>
      <button className="btn btn-icon btn-secondary" disabled={!shown} onClick={() => press(true)} aria-label={shown ? `More: ${dur(stepLength(shown, true))}` : "More time"} title={shown ? dur(stepLength(shown, true)) : undefined} style={{ width: 26, height: 26 }}>
        <Icon name="plus" />
      </button>
    </>
  )
}

const SAVE_AFTER_MS = 600

/** A length in minutes; null leaves it to Friday's estimate. Under 15 minutes still takes one 15-minute slot. For
 * several tasks (`group`), null is lengths that differ, and there's no leaving it to Friday. */
export function LengthPicker({ value, onPick, group }: { value: number | null; onPick: (v: number | null) => void; group?: boolean }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 12, color: "var(--color-neutral-400)" }}>
        <LengthInput value={value} onPick={onPick} />
        <span className="fr-h tnum" style={{ fontSize: 22, color: "var(--color-text)" }}>
          {value === null ? (group ? "Each its own" : "Friday decides") : dur(value)}
        </span>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {[5, 15, 30, 60, 120, 180].map((v) => (
          <Chip key={v} on={value === v} onClick={() => onPick(v)}>
            {dur(v)}
          </Chip>
        ))}
        {!group && (
          <Chip on={value === null} onClick={() => onPick(null)}>
            Friday decides
          </Chip>
        )}
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
    ["Every other week", { every: "rrule:FREQ=WEEKLY;INTERVAL=2", perWindow: null }],
    ["Every month", { every: "rrule:FREQ=MONTHLY", perWindow: null }],
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
  if (days.length) return `Every ${days.map((d) => DOWS[d]).join(", ")}${end}.`
  return `${everyN(plain ?? "") ?? "Repeats"}${end}.`
}

/** "Every other week", "Every 4 weeks", "Every month", "Every 3 days" for a rule with no days named. */
export function everyN(every: string): string | null {
  const m = /^rrule:FREQ=(DAILY|WEEKLY|MONTHLY|YEARLY)(?:;INTERVAL=(\d+))?$/.exec(every)
  if (!m) return null
  const unit = { DAILY: "day", WEEKLY: "week", MONTHLY: "month", YEARLY: "year" }[m[1] as "DAILY"]
  const n = Number(m[2] ?? 1)
  return n === 1 ? `Every ${unit}` : n === 2 ? `Every other ${unit}` : `Every ${n} ${unit}s`
}

export function repeatLabel(r: Repeat): string {
  if (!r.every) return "Once"
  if (r.perWindow) return `${r.perWindow}× a week`
  return repeatSummary(r).replace(/\.$/, "").replace(". Friday picks the days", "")
}
