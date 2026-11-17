// The new layout's editing, as To-do details does it (16 Nov, the user: inline buttons and boxes were "super
// unintuitive"): a side panel over the page's right, and in it rows, each a setting's name, its value in words, and a
// click that opens a short list of choices, each saying what it does.

import { type ReactNode, useEffect, useRef, useState } from "react"
import { Icon, useMenuClose } from "@/components/fr/controls"
import { useMenuPlace } from "@/lib/menuPlace"
import { dockRoom } from "@/now/dockRoom"

/** A panel over the page's right side, the list still in view on the left; ✕ or Escape closes it. */
export function SidePanel({ label, onClose, children }: { label: string; onClose: () => void; children: ReactNode }) {
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && !e.defaultPrevented && onClose()
    window.addEventListener("keydown", esc)
    return () => window.removeEventListener("keydown", esc)
  }, [onClose])
  return (
    <aside
      ref={box}
      aria-label={label}
      className="fr-float fr-scroll-column"
      style={{ position: "absolute", top: 0, right: 0, bottom: 0, width: "min(480px, 100%)", zIndex: 6, overflowY: "auto", borderRadius: 0, padding: `20px 22px ${dockRoom(140)}`, display: "flex", flexDirection: "column", gap: 18, boxShadow: "-16px 0 40px color-mix(in srgb, #000 30%, transparent)" }}
    >
      <button className="btn btn-icon btn-ghost" onClick={onClose} aria-label="Close" title="Close (Esc)" style={{ position: "absolute", top: 14, right: 14, width: 28, height: 28, color: "var(--color-neutral-400)" }}>
        <Icon name="x" />
      </button>
      {children}
    </aside>
  )
}

/** Rows of settings: names in a narrow column, values beside them. */
export function Rows({ children }: { children: ReactNode }) {
  return <div style={{ display: "grid", gridTemplateColumns: "112px minmax(0,1fr)", gap: "12px 14px", alignItems: "center" }}>{children}</div>
}

/** One setting: its name, its value in words on a button, and, opened, its choices under it across the row. */
export function SettingRow(props: { label: string; value: ReactNode; open: boolean; onToggle: () => void; note?: ReactNode; children: ReactNode }) {
  const { label, value, open, onToggle, note, children } = props
  return (
    <>
      <span className="fr-kicker">{label}</span>
      <span style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
        <button
          className="fr-plain fr-well tnum"
          onClick={onToggle}
          aria-expanded={open}
          aria-label={`${label}: ${typeof value === "string" ? value : ""}`.replace(/: $/, "")}
          style={{ justifySelf: "start", alignSelf: "flex-start", display: "inline-flex", gap: 6, alignItems: "center", padding: "4px 10px", borderRadius: "var(--radius-sm)", fontSize: 12, maxWidth: "100%", textAlign: "left" }}
        >
          <span style={{ minWidth: 0, overflowWrap: "anywhere" }}>{value}</span>
          <Icon name="caret-down" size={10} style={{ opacity: 0.6, flex: "none" }} />
        </button>
        {note && <span className="fr-kicker" style={{ textWrap: "pretty" }}>{note}</span>}
      </span>
      {open && (
        <div className="fr-well" role="group" aria-label={label} style={{ gridColumn: "1 / -1", padding: 10 }}>
          {children}
        </div>
      )}
    </>
  )
}

export interface Choice<T> {
  value: T
  label: string
  desc?: string // what it does, in words
}

/** Choices one under the other, each with what it does; the one set now is marked. */
export function Choices<T>({ options, value, onPick, label }: { options: Choice<T>[]; value: T; onPick: (v: T) => void; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      {options.map((o) => {
        const on = o.value === value
        return (
          <button
            key={o.label}
            role="radio"
            aria-checked={on}
            className="fr-plain fr-hover"
            onClick={() => onPick(o.value)}
            style={{ display: "grid", gridTemplateColumns: "16px minmax(0,1fr)", gap: 8, alignItems: "start", padding: "6px 8px", borderRadius: "var(--radius-sm)", textAlign: "left", background: on ? "color-mix(in srgb, var(--color-accent) 12%, transparent)" : undefined }}
          >
            <Icon name={on ? "radio-button" : "circle"} size={14} fill={on} style={{ marginTop: 2, color: on ? "var(--color-accent-300)" : "var(--color-neutral-400)" }} />
            <span style={{ display: "flex", flexDirection: "column", gap: 1, minWidth: 0 }}>
              <span style={{ fontSize: 13 }}>{o.label}</span>
              {o.desc && <span style={{ fontSize: 12, color: "var(--color-neutral-400)", textWrap: "pretty" }}>{o.desc}</span>}
            </span>
          </button>
        )
      })}
    </div>
  )
}

/** A value on a button, like Friday's other dropdowns, opening a panel of its choices beside it (never cut off). */
export function DropField({ label, value, children }: { label: string; value: string; children: (close: () => void) => ReactNode }) {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)
  const panel = useRef<HTMLDivElement>(null)
  const escape = useMenuClose(open, setOpen, box, button)
  useMenuPlace(open, button, panel)
  const close = () => (setOpen(false), button.current?.focus())
  return (
    <div ref={box} className="fr-menu" onKeyDown={escape}>
      <button ref={button} className="fr-menu-button tnum" aria-haspopup="dialog" aria-expanded={open} aria-label={`${label}: ${value}`} onClick={() => setOpen(!open)}>
        <span>{value}</span>
        <Icon name="caret-down" size={12} />
      </button>
      {open && (
        <div ref={panel} className="fr-float" role="dialog" aria-label={label} style={{ position: "absolute", zIndex: 40, top: "calc(100% + 4px)", right: 0, width: "min(300px, calc(100vw - 24px))", padding: 10, borderRadius: "var(--radius-md)" }}>
          {children(close)}
        </div>
      )}
    </div>
  )
}
