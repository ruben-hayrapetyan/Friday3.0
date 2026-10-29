// The pieces of setup's stage (Setup.tsx, setup.css): Friday's ring, choice cards with a picture of what each means,
// a bar of hours you fill, a time with steps either side, and the week your answers make.

import { type CSSProperties, type KeyboardEvent, type ReactNode, type Ref, useEffect, useRef, useState } from "react"
import { Icon } from "@/components/fr/controls"
import { TimeInput } from "@/components/fr/TimeInput"
import type { Expect } from "@/lib/ampm"
import { type Bit, FOCUS, shift, VIEW } from "./setupWeek"

const vars = (v: Record<string, string | number | undefined>) => v as CSSProperties

/** Friday's ring, as on its icon: as full as setup has come, closed in gold at the end. */
export function Ring({ progress, closed }: { progress: number; closed: boolean }) {
  const r = 13
  const around = 2 * Math.PI * r
  const level = closed ? 1 : Math.max(0.04, Math.min(0.97, progress))
  return (
    <svg className="st-ring" data-closed={closed || undefined} width={34} height={34} viewBox="0 0 34 34" aria-hidden>
      <circle cx={17} cy={17} r={r} fill="none" stroke="currentColor" strokeOpacity={0.16} strokeWidth={3.2} />
      <circle
        cx={17}
        cy={17}
        r={r}
        fill="none"
        stroke={closed ? "var(--st-gold)" : "var(--st-paper)"}
        strokeWidth={3.2}
        strokeLinecap="round"
        strokeDasharray={around}
        strokeDashoffset={around * (1 - level)}
        transform="rotate(-90 17 17)"
      />
      <text x={17} y={17.5} textAnchor="middle" dominantBaseline="central" fontFamily="ui-rounded, system-ui, sans-serif" fontWeight={800} fontSize={13} fill="currentColor">
        F
      </text>
    </svg>
  )
}

/** One choice: its picture, what it is, a line on what it means, and the tick when it's yours. */
export function Card(props: {
  on: boolean
  glyph: ReactNode
  hue?: string
  title: ReactNode
  note?: ReactNode
  badge?: string
  onPick: () => void
  i?: number
  tabIndex?: number
  onKeyDown?: (e: KeyboardEvent<HTMLButtonElement>) => void
  ref?: Ref<HTMLButtonElement>
}) {
  const { on, glyph, hue, title, note, badge, onPick, i = 0, tabIndex, onKeyDown, ref } = props
  return (
    <button ref={ref} type="button" role="radio" aria-checked={on} className="st-card st-rise" style={vars({ "--i": i })} onClick={onPick} tabIndex={tabIndex} onKeyDown={onKeyDown}>
      <span className="st-glyph" style={vars({ "--hue": hue })}>
        {glyph}
      </span>
      <span style={{ minWidth: 0 }}>
        <span className="st-card-title">
          {title}
          {badge && <span className="st-card-badge">{badge}</span>}
        </span>
        {note && <span className="st-card-note">{note}</span>}
      </span>
      <span className="st-tick" aria-hidden>
        <Icon name="check" size={13} style={{ fontWeight: 700 }} />
      </span>
    </button>
  )
}

export interface Choice<T> {
  value: T
  title: ReactNode
  note?: ReactNode
  glyph: ReactNode
  hue?: string
}

/** A question's choices: one card each, the arrow keys moving between them as between radio buttons. */
export function Choices<T extends string | number>({ label, choices, value, onPick, one, from = 0 }: { label: string; choices: Choice<T>[]; value: T | null; onPick: (v: T) => void; one?: boolean; from?: number }) {
  const refs = useRef<(HTMLButtonElement | null)[]>([])
  const at = choices.findIndex((c) => c.value === value)
  const key = (e: KeyboardEvent<HTMLButtonElement>, i: number) => {
    const move = ({ ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 } as Record<string, number>)[e.key]
    if (!move) return
    e.preventDefault()
    const next = (i + move + choices.length) % choices.length
    refs.current[next]?.focus()
    onPick(choices[next].value)
  }
  return (
    <div className="st-cards" role="radiogroup" aria-label={label} data-one={one || undefined}>
      {choices.map((c, i) => (
        <Card
          key={String(c.value)}
          ref={(el) => {
            refs.current[i] = el
          }}
          on={c.value === value}
          glyph={c.glyph}
          hue={c.hue}
          title={c.title}
          note={c.note}
          onPick={() => onPick(c.value)}
          i={from + i}
          tabIndex={i === (at >= 0 ? at : 0) ? 0 : -1}
          onKeyDown={(e) => key(e, i)}
        />
      ))}
    </div>
  )
}

/** Another amount, typed: shown when asked for (or when the amount is none of the choices), read as `read` reads it. */
export function Other(props: { value: number; picked: boolean; read: (t: string) => number | null; say: (v: number) => string; min: number; max: number; example: string; ask: string; label: string; onPick: (v: number) => void }) {
  const { value, picked, read, say, min, max, example, ask, label, onPick } = props
  const [open, setOpen] = useState(!picked)
  const [text, setText] = useState(picked ? "" : say(value))
  const [problem, setProblem] = useState<string | null>(null)
  useEffect(() => {
    // a card was chosen, or the other question moved this one: the box follows
    if (text.trim() && read(text) !== value && !problem) setText(picked ? "" : say(value))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])
  if (!open)
    return (
      <button type="button" className="st-link st-rise" style={vars({ "--i": 7 })} onClick={() => setOpen(true)}>
        {ask}
      </button>
    )
  const type = (t: string) => {
    setText(t)
    if (!t.trim()) return setProblem(null)
    const v = read(t)
    if (v === null) return setProblem(`Type it like ${example}`)
    if (v < min || v > max) return setProblem(`Between ${say(min)} and ${say(max)}`)
    setProblem(null)
    onPick(v)
  }
  return (
    <span className="st-other">
      <input autoFocus={!picked || undefined} value={text} onChange={(e) => type(e.target.value)} placeholder={example} aria-label={label} data-bad={problem ? "" : undefined} />
      {problem ? <span className="st-problem">{problem}</span> : <span className="st-hours-say">{text.trim() ? "" : "or choose above"}</span>}
    </span>
  )
}

/** Hours as a bar you fill: a click or a drag sets whole hours, the arrow keys half hours; `base` (a normal day, under
 * a heavy one) is drawn solid and the rest hatched. */
export function HourBar(props: { label: string; value: number; min: number; segments: number; onPick: (v: number) => void; say: (v: number) => string; names?: Record<number, string>; hue?: string; base?: number; i?: number }) {
  const { label, value, min, segments, onPick, say, names, hue, base, i = 0 } = props
  const bar = useRef<HTMLDivElement>(null)
  const held = useRef(false)
  const at = (x: number) => {
    const box = bar.current?.getBoundingClientRect()
    if (!box) return
    const raw = ((x - box.left) / box.width) * segments
    const v = min === 0 && raw < 0.4 ? 0 : Math.max(min, Math.min(segments, Math.ceil(raw)))
    if (v !== value) onPick(v)
  }
  const key = (e: KeyboardEvent<HTMLDivElement>) => {
    const steps: Record<string, number> = { ArrowRight: 0.5, ArrowUp: 0.5, ArrowLeft: -0.5, ArrowDown: -0.5, PageUp: 1, PageDown: -1 }
    let v: number | null = e.key in steps ? value + steps[e.key] : e.key === "Home" ? min : e.key === "End" ? segments : null
    if (v === null) return
    e.preventDefault()
    v = Math.max(min, Math.min(segments, v))
    if (v !== value) onPick(v)
  }
  const named = names?.[value]
  return (
    <div className="st-hours st-rise" style={vars({ "--i": i })}>
      <span className="st-label">{label}</span>
      <span className="st-hours-head">
        <span key={value} className="st-big">
          {named ?? (
            <>
              {say(value).replace(/[hm]$/, "")}
              <small>{say(value).endsWith("m") ? "min" : value === 1 ? "hour" : "hours"}</small>
            </>
          )}
        </span>
      </span>
      <div
        ref={bar}
        className="st-bar"
        role="slider"
        tabIndex={0}
        aria-label={label}
        aria-valuemin={min}
        aria-valuemax={segments}
        aria-valuenow={value}
        aria-valuetext={named ?? say(value)}
        style={vars({ "--hue": hue })}
        onKeyDown={key}
        onPointerDown={(e) => {
          held.current = true
          e.currentTarget.setPointerCapture(e.pointerId)
          at(e.clientX)
        }}
        onPointerMove={(e) => held.current && at(e.clientX)}
        onPointerUp={() => (held.current = false)}
        onPointerCancel={() => (held.current = false)}
      >
        {Array.from({ length: segments }, (_, k) => (
          <span key={k} className="st-seg" data-extra={base !== undefined && k >= base ? "" : undefined}>
            <i style={vars({ "--fill": Math.max(0, Math.min(1, value - k)), "--k": k })} />
          </span>
        ))}
      </div>
      <span className="st-scale" aria-hidden>
        <span>{names?.[min] ?? say(min)}</span>
        <span>{names?.[segments] ?? say(segments)}</span>
      </span>
    </div>
  )
}

/** A time of day, typed or stepped a quarter hour at a time. */
export function TimeCard({ icon, hue, label, value, onPick, expect, i = 0 }: { icon: string; hue: string; label: string; value: string; onPick: (t: string) => void; expect?: Expect; i?: number }) {
  return (
    <div className="st-time st-rise" style={vars({ "--i": i })}>
      <span className="st-glyph" style={vars({ "--hue": hue })}>
        <Icon name={icon} fill size={22} />
      </span>
      <span style={{ minWidth: 0 }}>
        <span className="st-time-label">{label}</span>
        <TimeInput className="" step={300} value={value} onChange={(t) => t && onPick(t)} label={label} expect={expect} />
      </span>
      <span className="st-steps">
        <button type="button" className="st-step" aria-label={`${label}, a quarter hour earlier`} onClick={() => onPick(shift(value, -15))}>
          <Icon name="minus" size={15} />
        </button>
        <button type="button" className="st-step" aria-label={`${label}, a quarter hour later`} onClick={() => onPick(shift(value, 15))}>
          <Icon name="plus" size={15} />
        </button>
      </span>
    </div>
  )
}

/** A sitting's length: the bar is as long as the sitting, out of four hours. */
export function LengthGlyph({ hours }: { hours: number }) {
  const w = 3 + 23 * Math.min(1, hours / 4)
  return (
    <svg width={30} height={30} viewBox="0 0 30 30" aria-hidden>
      <rect x={2} y={12.5} width={26} height={5} rx={2.5} fill="currentColor" opacity={0.22} />
      <rect x={2} y={12.5} width={w} height={5} rx={2.5} fill="currentColor" />
    </svg>
  )
}

/** Days up to a deadline, its flag at the end; the dot is the day the work is done. */
export function EarlyGlyph({ days }: { days: number }) {
  const xs = [4, 11, 18, 25]
  const done = xs[3 - Math.max(0, Math.min(3, days))]
  return (
    <svg width={30} height={30} viewBox="0 0 30 30" aria-hidden>
      <line x1={3} y1={21} x2={27} y2={21} stroke="currentColor" strokeOpacity={0.3} strokeWidth={2} strokeLinecap="round" />
      {xs.map((x) => (
        <circle key={x} cx={x} cy={21} r={1.5} fill="currentColor" opacity={0.5} />
      ))}
      <path d="M25 21V7.5l5 2.4-5 2.4" fill="none" stroke="var(--st-gold)" strokeWidth={1.8} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={done} cy={21} r={3.8} fill="currentColor" />
    </svg>
  )
}

const DAYS = ["M", "T", "W", "T", "F", "S", "S"]
const MARKS: [number, string][] = [
  [6 * 60, "6am"],
  [12 * 60, "noon"],
  [18 * 60, "6pm"],
  [24 * 60, "12am"],
]
const LEGEND: [string, string][] = [
  ["Sleep", "var(--st-sleep)"],
  ["Classes (an example)", "color-mix(in srgb, var(--st-class) 60%, transparent)"],
  ["Work", "color-mix(in srgb, var(--st-work) 70%, transparent)"],
  ["Free time", "color-mix(in srgb, var(--st-free) 50%, transparent)"],
]

/** The week, Monday to Sunday, 6 AM to 2 AM: what the question on screen changes drawn brightest. */
export function WeekPanel({ bits, stage, readout, legend }: { bits: Bit[]; stage: string; readout: ReactNode; legend: boolean }) {
  const lit = FOCUS[stage]
  const span = VIEW.to - VIEW.from
  const pct = (t: number) => ((Math.min(Math.max(t, VIEW.from), VIEW.to) - VIEW.from) / span) * 100
  return (
    <div>
      <div className="st-week-title">Your week</div>
      <div className="st-week" data-focus={lit ? "" : undefined} aria-hidden>
        <div className="st-week-head">
          {DAYS.map((d, i) => (
            <span key={i}>{d}</span>
          ))}
        </div>
        <div className="st-week-grid">
          {MARKS.map(([t, name]) => (
            <span key={t} className="st-axis" style={{ top: `${pct(t)}%` }}>
              {name}
            </span>
          ))}
          {DAYS.map((_, day) => (
            <div key={day} className="st-day">
              {bits
                .filter((b) => b.day === day)
                .map((b, k) => (
                  <span key={b.id} className="st-bit" data-kind={b.kind} data-lit={lit?.includes(b.kind) || undefined} style={vars({ top: `${pct(b.start)}%`, height: `${pct(b.end) - pct(b.start)}%`, "--k": k })} />
                ))}
            </div>
          ))}
        </div>
      </div>
      <p className="st-readout" aria-live="polite">
        {readout}
      </p>
      {legend && (
        <div className="st-legend" aria-hidden>
          {LEGEND.map(([name, swatch]) => (
            <span key={name}>
              <i style={vars({ "--sw": swatch })} />
              {name}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

/** Something to bring in, on a card: its picture, what it is, and its controls. */
export function Source({ icon, hue, title, note, children, i = 0 }: { icon: string; hue: string; title: string; note: string; children: ReactNode; i?: number }) {
  return (
    <div className="st-source st-rise" style={vars({ "--i": i })}>
      <span className="st-glyph" style={vars({ "--hue": hue })}>
        <Icon name={icon} fill size={22} />
      </span>
      <div style={{ display: "flex", flexDirection: "column", gap: 8, minWidth: 0 }}>
        <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <span className="st-source-title">{title}</span>
          <span className="st-source-note">{note}</span>
        </span>
        {children}
      </div>
    </div>
  )
}
