// The new layout's editing, as To-do details does it (16 Nov, the user: inline buttons and boxes were "super
// unintuitive"): rows, each a setting's name, its value in words, and a click that opens a short list of choices,
// each saying what it does. What the Projects page opens (a project, an exam, an ongoing project) opens in a popup in
// the middle of the screen, over the shelves (17 Nov: "i think everything should be a center popup rather than a
// sidebar or its own page").

import { createContext, type ReactNode, useContext, useRef, useState } from "react"
import { Icon, useMenuClose } from "@/components/fr/controls"
import { useDialogKeys } from "@/dialogs/Dialogs"
import { useMenuPlace } from "@/lib/menuPlace"
import { useShell } from "@/shell/ShellContext"

/** How big a popup gets: `width` across, and about `tall` high, for where its top sits. */
export const POPUP = { project: { width: 1000, tall: 860 }, panel: { width: 640, tall: 720 } } as const

/** A dropdown of the popup's (a length, a date, a menu) is open: Escape closes that first, not the popup. */
export const menuOpenIn = (box: HTMLElement | null) => !!box?.querySelector(".fr-menu [aria-expanded='true']")

/** Where a popup's top sits: where one `tall` high would sit centered, never nearer the top than `least`. It grows
 * down from there, so opening a row in it never moves what's above (a button doesn't move under the pointer). */
export const popupTop = (tall: number, least: number) => `max(${least}px, calc((100vh - ${tall}px) / 2))`

const Strip = createContext<HTMLElement | null>(null)
/** The popup's top strip, beside its ✕, for what it shows to put its own tools in (a project's Save as template and
 * its Project menu); null outside a popup. */
export const usePopupStrip = () => useContext(Strip)

/** A popup in the middle of the screen, over the page dimmed behind it, above the Now bar; ✕, Escape or a click on
 * the dimmed page closes it. It scrolls inside itself; on a phone it takes nearly the whole screen. What it shows can
 * change (another project picked in it) without it closing. */
export function Popup({ label, onClose, size = "panel", children }: { label: string; onClose: () => void; size?: keyof typeof POPUP; children: ReactNode }) {
  const { layout } = useShell()
  const box = useDialogKeys(() => !menuOpenIn(box.current) && onClose())
  const { width, tall } = POPUP[size]
  const phone = layout.tight
  const [strip, setStrip] = useState<HTMLElement | null>(null)
  return (
    <div className="fr-scrim" data-popup={size} style={{ alignItems: "flex-start", padding: phone ? 8 : `${popupTop(tall, 24)} 24px 24px` }}>
      <div onClick={onClose} style={{ position: "absolute", inset: 0 }} />
      <div
        ref={box}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        className="fr-float"
        style={{ position: "relative", width: `min(${width}px, 100%)`, height: phone ? "100%" : undefined, maxHeight: "100%", display: "flex", flexDirection: "column", outline: "none", overflow: "hidden" }}
      >
        {/* its close on a strip at the top, with what it shows's own tools: what scrolls passes under the strip, never
            under the ✕ */}
        <div style={{ flex: "none", minHeight: phone ? 44 : 50, display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 10, padding: phone ? "6px 8px 6px 14px" : "8px 14px 8px 26px" }}>
          <div ref={setStrip} style={{ flex: 1, minWidth: 0, display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 12, flexWrap: "wrap" }} />
          <button className="btn btn-icon btn-ghost" onClick={onClose} aria-label="Close" title="Close (Esc)" style={{ width: 28, height: 28, flex: "none", color: "var(--color-neutral-400)" }}>
            <Icon name="x" />
          </button>
        </div>
        <div className="fr-scroll-column" style={{ overflowY: "auto", minHeight: 0, flex: "1 1 auto", padding: phone ? "0 14px 20px" : "0 26px 26px", display: "flex", flexDirection: "column", gap: 18 }}>
          <Strip.Provider value={strip}>{children}</Strip.Provider>
        </div>
      </div>
    </div>
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
  // its panel scrolls inside its own height: placed menus are held to 280px (lib/menuPlace), and a long list (New
  // exam's exam focus, 19 Nov) ran out of it, over the window
  return (
    <div ref={box} className="fr-menu" onKeyDown={escape}>
      <button ref={button} className="fr-menu-button tnum" aria-haspopup="dialog" aria-expanded={open} aria-label={`${label}: ${value}`} onClick={() => setOpen(!open)}>
        <span>{value}</span>
        <Icon name="caret-down" size={12} />
      </button>
      {open && (
        <div ref={panel} className="fr-float" role="dialog" aria-label={label} style={{ position: "absolute", zIndex: 40, top: "calc(100% + 4px)", right: 0, width: "min(300px, calc(100vw - 24px))", padding: 10, borderRadius: "var(--radius-md)", overflowY: "auto", overscrollBehavior: "contain" }}>
          {children(close)}
        </div>
      )}
    </div>
  )
}
