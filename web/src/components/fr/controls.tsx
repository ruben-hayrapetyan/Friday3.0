// The small controls v22 repeats everywhere (theme/friday.css draws them).

import { type CSSProperties, type KeyboardEvent as ReactKeyboardEvent, type ReactNode, type RefObject, useEffect, useRef, useState } from "react"
import { useOnScreen } from "@/lib/onScreen"

/** A Phosphor icon by name, e.g. `gear-six`; `fill` for the filled set. */
export function Icon({ name, size, fill, style }: { name: string; size?: number; fill?: boolean; style?: CSSProperties }) {
  return <i className={`${fill ? "ph-fill" : "ph"} ph-${name}`} style={{ fontSize: size, ...style }} aria-hidden />
}

export interface Option<T> {
  value: T
  label: ReactNode
}

/** A segmented control: one of a few options. */
export function Seg<T extends string | number>(props: {
  options: readonly (Option<T> | T)[]
  value: T | null
  onPick: (value: T) => void
  size?: "small" | "big"
  onBg?: boolean
  label?: string
}) {
  const { options, value, onPick, size, onBg, label } = props
  return (
    <div className={`fr-seg ${size ?? ""} ${onBg ? "on-bg" : ""}`} role="group" aria-label={label}>
      {options.map((o) => {
        const option = typeof o === "object" ? o : { value: o, label: String(o) }
        return (
          <button key={String(option.value)} aria-pressed={option.value === value} onClick={() => onPick(option.value)}>
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

/** A dropdown: the value on a button, the options in a floating list; Escape or a click elsewhere closes it. */
export function Menu<T extends string>(props: { options: readonly Option<T>[]; value: T; onPick: (value: T) => void; label: string; disabled?: boolean }) {
  const { options, value, onPick, label, disabled } = props
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)
  const escape = useMenuClose(open, setOpen, box, button)
  const list = useOnScreen<HTMLDivElement>(open) // right-aligned, on a phone it could run off the left
  return (
    <div ref={box} className="fr-menu" onKeyDown={escape}>
      <button ref={button} className="fr-menu-button" aria-haspopup="listbox" aria-expanded={open} aria-label={label} disabled={disabled} onClick={() => setOpen(!open)}>
        <span>{options.find((o) => o.value === value)?.label ?? value}</span>
        <Icon name="caret-down" size={12} />
      </button>
      {open && (
        <div ref={list} className="fr-float fr-menu-list" role="listbox" aria-label={label}>
          {options.map((o) => (
            <button
              key={o.value}
              role="option"
              aria-selected={o.value === value}
              onClick={() => {
                onPick(o.value)
                setOpen(false)
                button.current?.focus()
              }}
            >
              <span>{o.label}</span>
              {o.value === value && <Icon name="check" size={13} />}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

/** An open menu's list closes on Escape or a press outside `box`; Escape puts the focus back on its `button` (the audit,
 * 12 Nov: the pigment menu had no Escape). Returns the menu's own key handler: an Escape that closes the list goes no
 * further, not to the pane or dialog it's in (the audit, 31 Oct), while one pressed with it closed does. The window
 * hears Escape too, for when the focus is nowhere (a click in Safari doesn't focus a button). */
export function useMenuClose(open: boolean, setOpen: (open: boolean) => void, box: RefObject<HTMLElement | null>, button: RefObject<HTMLButtonElement | null>): (e: ReactKeyboardEvent) => void {
  const shut = useRef(setOpen)
  shut.current = setOpen
  useEffect(() => {
    if (!open) return
    const away = (e: PointerEvent) => box.current && !box.current.contains(e.target as Node) && shut.current(false)
    const escape = (e: KeyboardEvent) => e.key === "Escape" && (shut.current(false), button.current?.focus())
    window.addEventListener("pointerdown", away)
    window.addEventListener("keydown", escape)
    return () => {
      window.removeEventListener("pointerdown", away)
      window.removeEventListener("keydown", escape)
    }
  }, [open, box, button])
  return (e) => {
    if (!open || e.key !== "Escape") return
    e.stopPropagation()
    shut.current(false)
    button.current?.focus()
  }
}

export function Switch({ on, onToggle, label }: { on: boolean; onToggle: () => void; label: string }) {
  return (
    <button
      className="fr-switch"
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={(e) => {
        e.stopPropagation()
        onToggle()
      }}
    >
      <span />
    </button>
  )
}

export function Chip(props: { on?: boolean; swatch?: string; onClick: () => void; children: ReactNode; title?: string }) {
  return (
    <button className="fr-chip" aria-pressed={props.on ?? false} onClick={props.onClick} title={props.title}>
      {props.swatch && <span className="fr-swatch" style={{ background: props.swatch }} />}
      {props.children}
    </button>
  )
}

/** A round check for to-dos. */
export function Check({ done, onToggle, small }: { done: boolean; onToggle: () => void; small?: boolean }) {
  const size = small ? 15 : 18
  return (
    <button
      className="fr-check"
      role="checkbox"
      aria-checked={done}
      aria-label={done ? "Mark not done" : "Mark done"}
      style={{ width: size, height: size }}
      onClick={(e) => {
        e.stopPropagation()
        onToggle()
      }}
    >
      {done && <Icon name="check" size={small ? 9 : 11} />}
    </button>
  )
}

/** A square check inside a list of choices. */
export function Box({ on }: { on: boolean }) {
  return (
    <span className="fr-box" role="checkbox" aria-checked={on}>
      {on && <Icon name="check" size={11} />}
    </span>
  )
}

/** A heading in the design's display face. */
export function H({ size, children, style }: { size: number; children: ReactNode; style?: CSSProperties }) {
  return (
    <span className="fr-h" style={{ fontSize: size, lineHeight: size >= 26 ? 1 : 1.2, ...style }}>
      {children}
    </span>
  )
}
