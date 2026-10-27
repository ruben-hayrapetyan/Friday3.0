// What a meal's and a night's editors share (27 Oct: editing one was a click on small text that turned into bare time
// boxes and unlabelled icons): a labelled time with a way to clear it, and the card it sits in, opened under the row
// you clicked, with Save, a way to delete and Cancel in words.

import type { ReactNode } from "react"
import { Icon } from "@/components/fr/controls"
import { TimeInput } from "@/components/fr/TimeInput"
import type { Expect } from "@/lib/ampm"

export function TimeField({ label, value, onChange, onClear, expect }: { label: string; value: string; onChange: (v: string) => void; onClear?: () => void; expect?: Expect }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 3, fontSize: 11, color: "var(--color-neutral-400)" }}>
      {label}
      <span style={{ display: "flex", alignItems: "center", gap: 2 }}>
        <TimeInput label={label} value={value} onChange={onChange} expect={expect} style={{ width: 118, padding: "4px 8px", minHeight: 0, fontSize: 13 }} />
        {onClear && value && (
          <button type="button" className="btn btn-icon btn-ghost" onClick={onClear} aria-label={`Clear ${label.toLowerCase()}`} title="Clear" style={{ width: 22, height: 22 }}>
            <Icon name="x" size={11} />
          </button>
        )}
      </span>
    </label>
  )
}

export function EditCard(props: { title: string; said?: ReactNode; children: ReactNode; saveLabel: string; canSave: boolean; busy: boolean; onSave: () => void; onCancel: () => void; extra?: ReactNode }) {
  const { title, said, children, saveLabel, canSave, busy, onSave, onCancel, extra } = props
  return (
    <div
      className="fr-well"
      role="group"
      aria-label={title}
      onKeyDown={(e) => (e.key === "Escape" ? onCancel() : e.key === "Enter" && canSave && !busy && onSave())}
      style={{ display: "flex", flexDirection: "column", gap: 10, padding: "12px 14px", margin: "4px 0 8px" }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
        <span style={{ fontWeight: 600 }}>{title}</span>
        {said && <span className="tnum" style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>{said}</span>}
      </div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 14, flexWrap: "wrap" }}>{children}</div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <button className="btn btn-primary fr-press" disabled={!canSave || busy} onClick={onSave} style={{ fontSize: 12 }}>
          {busy ? <span className="fr-spinner" /> : <Icon name="check" />}
          {saveLabel}
        </button>
        <button className="btn btn-ghost" disabled={busy} onClick={onCancel} style={{ fontSize: 12 }}>
          Cancel
        </button>
        <span style={{ flex: 1 }} />
        {extra}
      </div>
    </div>
  )
}

/** Minutes from one "HH:MM" to the next, over midnight when it ends earlier. */
export function minutesBetween(from: string, to: string): number | null {
  if (!from || !to) return null
  const m = (t: string) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5))
  return (m(to) - m(from) + 1440) % 1440
}
