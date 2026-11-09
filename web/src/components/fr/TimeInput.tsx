// A time box you type a time into the way you'd say it ("11", "1130", "11:30", "11:30p", "noon"), read as the half of
// the day it means (lib/ampm.ts): lunch retyped as 11 is 11am, not the 11pm a 12-hour box's pm would make it. The am
// or pm Friday reads is filled in, in grey, as you type, in every box, an empty one too (28 Oct: "the AM/PM doesn't
// autofill in all time boxes": a native time box left the half blank until it was typed); type a or p to choose the
// other. The time is set on Enter or Tab or when you leave the box; Escape puts back what was there; the arrow keys
// move it by the box's step.

import { type CSSProperties, type KeyboardEvent, useLayoutEffect, useRef, useState } from "react"
import { flushSync } from "react-dom"
import { DAY_HOURS, type Expect, typedTime } from "@/lib/ampm"
import { ampm } from "@/lib/time"

const TIME = /^([01]\d|2[0-3]):[0-5]\d$/
const pad = (n: number) => String(n).padStart(2, "0")
const clock = (m: number) => {
  const day = ((m % 1440) + 1440) % 1440
  return `${pad(Math.floor(day / 60))}:${pad(day % 60)}`
}
let measure: CanvasRenderingContext2D | null = null

/** Where the arrows start in an empty box: near what it expects, else just after what it comes after (an end after its
 * start), else the time it is now (9 Nov: they started from 9am, so a stop after a 5:34pm start went to 8:50am). */
export function nudgeFrom(expect: Expect | undefined, now: Date = new Date()): string {
  if (expect?.near && TIME.test(expect.near)) return expect.near
  if (expect?.after && TIME.test(expect.after)) return expect.after
  return `${pad(now.getHours())}:${pad(Math.floor(now.getMinutes() / 5) * 5)}`
}

export function TimeInput(props: {
  value: string
  onChange: (time: string) => void
  expect?: Expect
  label?: string
  step?: number // seconds, as a time input's: what the arrow keys move it by
  placeholder?: string
  className?: string
  style?: CSSProperties
}) {
  const { value, onChange, expect, label, step, placeholder = "e.g. 9:30", className = "input", style } = props
  const shown = TIME.test(value) ? ampm(value) : ""
  const [text, setText] = useState<string | null>(null) // what's typed, while it differs from the time set
  const box = useRef<HTMLInputElement>(null)
  const [ghostAt, setGhostAt] = useState({ left: 0, font: "" })
  const editing = text !== null
  const read = editing && text.trim() ? typedTime(text, value, expect) : null
  // The half Friday filled in, drawn just after what's typed.
  const ghost = read?.guessed ? (Number(read.time.slice(0, 2)) < 12 ? "am" : "pm") : null
  useLayoutEffect(() => {
    const el = box.current
    if (!el || !ghost || text === null) return
    const css = getComputedStyle(el)
    measure ??= document.createElement("canvas").getContext("2d")
    if (!measure) return
    measure.font = css.font
    const left = parseFloat(css.paddingLeft) + parseFloat(css.borderLeftWidth) + measure.measureText(text.replace(/\s+$/, "")).width - el.scrollLeft
    setGhostAt({ left, font: css.font })
  }, [ghost, text])

  /** Sets what's typed, if it reads as a time (a cleared box clears it); else puts back the time there was. */
  const commit = () => {
    if (text === null) return
    setText(null)
    if (!text.trim()) return value && onChange("")
    if (read && read.time !== value) onChange(read.time)
  }
  const nudge = (by: number) => {
    const from = read?.time ?? (TIME.test(value) ? value : nudgeFrom(expect))
    const unit = Math.max(1, Math.round((step ?? 300) / 60))
    const minute = Number(from.slice(0, 2)) * 60 + Number(from.slice(3, 5))
    const next = clock(by > 0 ? Math.floor(minute / unit) * unit + unit : Math.ceil(minute / unit) * unit - unit)
    setText(ampm(next))
  }
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowUp" || e.key === "ArrowDown") {
      e.preventDefault()
      nudge(e.key === "ArrowUp" ? 1 : -1)
    } else if (e.key === "Escape" && editing && text !== shown) {
      e.stopPropagation() // the first Escape puts the time back; the next one closes what it's in
      setText(null)
    } else if (e.key === "Enter" && editing) {
      // Set the time first, then let the Enter go on (a card's Save on Enter), so what's saved is the time typed.
      e.preventDefault()
      e.stopPropagation()
      const el = e.currentTarget
      const { metaKey, ctrlKey, shiftKey, altKey } = e
      flushSync(commit)
      el.dispatchEvent(new globalThis.KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true, metaKey, ctrlKey, shiftKey, altKey }))
    }
  }
  return (
    <span style={{ position: "relative", display: "inline-flex", minWidth: 0, flex: style?.flex, width: style?.flex ? undefined : style?.width }}>
      <input
        ref={box}
        type="text"
        inputMode="text"
        autoComplete="off"
        spellCheck={false}
        className={className}
        value={editing ? text : shown}
        placeholder={placeholder}
        aria-label={label}
        aria-invalid={editing && !!text.trim() && !read ? true : undefined}
        title={editing && text.trim() && !read ? "Type a time, like 9:30, 11pm or noon" : undefined}
        onFocus={(e) => e.currentTarget.select()}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={commit}
        style={{
          ...style,
          ...(style?.flex ? { flex: 1, width: "100%" } : {}),
          ...(editing && text.trim() && !read ? { boxShadow: "0 0 0 1px var(--fr-due)" } : {}),
        }}
      />
      {ghost && (
        <span
          aria-hidden
          className="tnum"
          style={{ position: "absolute", left: ghostAt.left + 3, top: 0, bottom: 0, display: "flex", alignItems: "center", pointerEvents: "none", font: ghostAt.font, color: "var(--color-neutral-500)" }}
        >
          {ghost}
        </span>
      )}
    </span>
  )
}

/** A day and a time ("YYYY-MM-DDTHH:MM", or null when empty): a date box beside a time box that reads a typed time as
 * above, in the day unless `expect` says otherwise. A time typed with no day yet is today's; a day picked with no time yet is at `time` (the end of the day for a
 * due). */
export function DateTimeInput(props: { value: string | null; onChange: (value: string | null) => void; expect?: Expect; time?: string; label?: string; style?: CSSProperties }) {
  const { value, onChange, expect = { hours: DAY_HOURS }, time: dayTime = "23:59", label = "", style } = props
  const at = value && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(value) ? value : null
  const day = at?.slice(0, 10) ?? ""
  const time = at?.slice(11, 16) ?? ""
  const today = () => {
    const d = new Date()
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
  }
  return (
    <span style={{ display: "inline-flex", gap: 6, alignItems: "center", minWidth: 0, ...style }}>
      <input
        type="date"
        className="input tnum"
        value={day}
        aria-label={`${label} day`.trim()}
        onChange={(e) => onChange(e.target.value ? `${e.target.value}T${time || dayTime}` : null)}
        style={{ width: 150, padding: "4px 8px", minHeight: 0 }}
      />
      <TimeInput
        value={time}
        onChange={(t) => onChange(t ? `${day || today()}T${t}` : day ? `${day}T${dayTime}` : null)}
        expect={expect}
        label={`${label} time`.trim()}
        className="input tnum"
        style={{ width: 100, padding: "4px 8px", minHeight: 0 }}
      />
    </span>
  )
}
