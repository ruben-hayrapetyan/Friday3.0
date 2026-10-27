// A time box that reads a typed time as the half of the day it means (lib/ampm.ts): lunch retyped as 11 is 11am, not
// the 11pm the box's pm made it. When it reads one the other way, a note under the box says so, with a way to keep
// the time as typed; it goes when you leave the box.

import { type CSSProperties, useState } from "react"
import { type Expect, meant, readAs } from "@/lib/ampm"

export function TimeInput(props: {
  value: string
  onChange: (time: string) => void
  expect?: Expect
  label?: string
  step?: number
  className?: string
  style?: CSSProperties
}) {
  const { value, onChange, expect, label, step, className = "input", style } = props
  const [note, setNote] = useState<{ typed: string; as: string } | null>(null)
  const said = note && note.as === value ? readAs(note.typed, note.as) : null
  return (
    <span style={{ position: "relative", display: "inline-flex", minWidth: 0, flex: style?.flex, width: style?.flex ? undefined : style?.width }}>
      <input
        type="time"
        className={className}
        step={step}
        value={value}
        aria-label={label}
        onChange={(e) => {
          const typed = e.target.value
          const as = meant(typed, value, expect)
          setNote(as === typed ? null : { typed, as })
          onChange(as)
        }}
        onBlur={() => setNote(null)}
        style={{ ...style, ...(style?.flex ? { flex: 1, width: "100%" } : {}) }}
      />
      {said && note && (
        <span
          role="status"
          className="tnum"
          style={{
            position: "absolute",
            top: "calc(100% + 4px)",
            left: 0,
            zIndex: 5,
            pointerEvents: "none", // a click on it reaches what's under it (Save, say); only "keep" takes one
            whiteSpace: "nowrap",
            fontSize: 11,
            padding: "3px 8px",
            borderRadius: 6,
            color: "var(--color-neutral-300)",
            background: "var(--color-surface)",
            boxShadow: "0 0 0 1px color-mix(in srgb, var(--color-accent) 40%, transparent), 0 4px 12px color-mix(in srgb, #000 25%, transparent)",
          }}
        >
          Made it {said.made} ·{" "}
          <button
            type="button"
            className="fr-link"
            // Kept from taking the focus, so the box doesn't lose it and the note with it before the click lands.
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => (setNote(null), onChange(note.typed))}
            style={{ fontSize: 11, pointerEvents: "auto" }}
          >
            keep {said.keep}
          </button>
        </span>
      )}
    </span>
  )
}
