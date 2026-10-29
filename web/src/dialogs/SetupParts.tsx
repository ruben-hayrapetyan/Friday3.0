// The pieces of setup's stage (Setup.tsx, setup.css): choice cards with a picture of what each means, a bar of hours
// you fill block by block, a time with steps either side, and things to bring in. Pixel art since 29 Oct (pixel.tsx);
// the week beside them is SetupBoard.tsx.

import { type CSSProperties, type KeyboardEvent, type ReactNode, type Ref, useEffect, useRef, useState } from "react"
import { Icon } from "@/components/fr/controls"
import { TimeInput } from "@/components/fr/TimeInput"
import type { Expect } from "@/lib/ampm"
import { CHECK, earlyArt, lengthArt, Sprite } from "./pixel"
import { shift } from "./setupWeek"

const vars = (v: Record<string, string | number | undefined>) => v as CSSProperties

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
        <Sprite art={CHECK} scale={2} />
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
 * a heavy one) is drawn solid and the rest checkered. */
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
export function TimeCard({ glyph, hue, label, value, onPick, expect, i = 0 }: { glyph: ReactNode; hue: string; label: string; value: string; onPick: (t: string) => void; expect?: Expect; i?: number }) {
  return (
    <div className="st-time st-rise" style={vars({ "--i": i })}>
      <span className="st-glyph" style={vars({ "--hue": hue })}>
        {glyph}
      </span>
      <span style={{ minWidth: 0 }}>
        <span className="st-time-label">{label}</span>
        <TimeInput className="" step={300} value={value} onChange={(t) => t && onPick(t)} label={label} expect={expect} />
      </span>
      <span className="st-steps">
        <button type="button" className="st-step" aria-label={`${label}, a quarter hour earlier`} onClick={() => onPick(shift(value, -15))}>
          −
        </button>
        <button type="button" className="st-step" aria-label={`${label}, a quarter hour later`} onClick={() => onPick(shift(value, 15))}>
          +
        </button>
      </span>
    </div>
  )
}

/** A sitting's length: as many blocks as it is long, out of four hours. */
export function LengthGlyph({ hours }: { hours: number }) {
  return <Sprite art={lengthArt(hours)} scale={2} />
}

/** Days up to a deadline, its flag on the last; the day the work is done filled in. */
export function EarlyGlyph({ days }: { days: number }) {
  return <Sprite art={earlyArt(days)} scale={2} />
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
