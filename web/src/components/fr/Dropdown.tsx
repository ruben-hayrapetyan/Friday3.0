// A button that opens a small menu below it (the Plan page's Plan and Show menus, the To-do page's view options):
// words on the button when the title row has room, an icon otherwise.

import { type CSSProperties, type ReactNode, useEffect, useRef, useState } from "react"
import { useShell } from "@/shell/ShellContext"
import { Icon } from "./controls"

/** A button that opens a small panel below it; a click outside or Escape closes it. */
export function Dropdown(props: { tour?: string; icon: string; label: string; badge?: ReactNode; tone?: CSSProperties; wide?: boolean; children: (close: () => void) => ReactNode }) {
  const { layout } = useShell()
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLSpanElement>(null)
  useEffect(() => {
    if (!open) return
    const away = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false)
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false)
    document.addEventListener("mousedown", away)
    window.addEventListener("keydown", esc)
    return () => (document.removeEventListener("mousedown", away), window.removeEventListener("keydown", esc))
  }, [open])
  const words = props.wide ?? layout.labels
  return (
    <span ref={box} style={{ position: "relative", flex: "none", minWidth: 0 }}>
      <button
        className={words ? "btn btn-secondary" : "btn btn-icon btn-ghost"}
        data-tour={props.tour}
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-label={props.label}
        title={props.label}
        style={{ whiteSpace: "nowrap", color: words ? undefined : "var(--color-neutral-300)", ...props.tone }}
      >
        <Icon name={props.icon} size={words ? 15 : 17} />
        {words && props.label}
        {props.badge}
        {words && <Icon name="caret-down" size={11} style={{ opacity: 0.6 }} />}
      </button>
      {open && (
        <div className="fr-float" style={{ position: "absolute", top: "calc(100% + 6px)", right: 0, zIndex: 20, width: "min(300px, calc(100vw - 24px))", padding: 6, display: "flex", flexDirection: "column", gap: 1 }}>
          {props.children(() => setOpen(false))}
        </div>
      )}
    </span>
  )
}

export function MenuRow({ icon, label, note, onClick }: { icon: string; label: string; note?: string; onClick: () => void }) {
  return (
    <button className="fr-plain fr-hover" onClick={onClick} style={{ display: "grid", gridTemplateColumns: "20px minmax(0,1fr)", gap: "1px 10px", alignItems: "center", padding: "8px 10px", borderRadius: "var(--radius-md)", textAlign: "left" }}>
      <Icon name={icon} size={16} style={{ color: "var(--color-neutral-300)" }} />
      <span>{label}</span>
      {note && (
        <>
          <span />
          <span style={{ fontSize: 12, color: "var(--color-neutral-500)" }}>{note}</span>
        </>
      )}
    </button>
  )
}
