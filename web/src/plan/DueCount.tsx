// A day's deadlines as one red button in its header (3 Nov: "a count in the header… make this a little fancier then
// just the count - like it should be red and should be intuitively clickable"): a flag, how many, and a caret, which
// opens the day's deadlines; each opens its item. The header's room is for whole-day events.

import { useEffect, useRef, useState } from "react"
import type { Block, Schemas } from "@/api/client"
import { Icon } from "@/components/fr/controls"
import { clock } from "@/lib/format"
import { useOnScreen } from "@/lib/onScreen"

/** A due marker, as the selected "block" the popover reads. */
export function dueBlock(d: Schemas["DueMarker"]): Block {
  return { key: `D${d.item_id}`, item_id: d.item_id, title: d.title, start: d.due, end: d.due }
}

export function dueCountLabel(n: number): string {
  return `${n} due`
}

export function DueCount({ dues, onPick }: { dues: Schemas["DueMarker"][]; onPick: (d: Schemas["DueMarker"]) => void }) {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLSpanElement>(null)
  const list = useOnScreen<HTMLDivElement>(open) // on a phone it would run off the right
  useEffect(() => {
    if (!open) return
    const away = (e: PointerEvent) => !box.current?.contains(e.target as Node) && setOpen(false)
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false)
    document.addEventListener("pointerdown", away)
    window.addEventListener("keydown", esc)
    return () => (document.removeEventListener("pointerdown", away), window.removeEventListener("keydown", esc))
  }, [open])
  if (!dues.length) return null
  const names = dues.map((d) => d.title).join(", ")
  return (
    <span ref={box} style={{ position: "relative", flex: "none" }}>
      <button
        className="fr-due-count"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={`${dueCountLabel(dues.length)}: ${names}`}
        title={`Due: ${names}`}
      >
        <Icon name="flag" size={12} fill />
        <span className="tnum">{dueCountLabel(dues.length)}</span>
        <Icon name="caret-down" size={10} />
      </button>
      {open && (
        <div ref={list} role="menu" className="fr-float" style={{ position: "absolute", top: "calc(100% + 6px)", left: 0, zIndex: 20, width: "min(280px, calc(100vw - 24px))", maxHeight: "min(420px, 60vh)", overflowY: "auto", overflowX: "hidden", whiteSpace: "normal", padding: 6, display: "flex", flexDirection: "column", gap: 1 }}>
          {dues.map((d) => (
            <button
              key={d.item_id}
              role="menuitem"
              className="fr-plain fr-hover"
              onClick={() => (setOpen(false), onPick(d))}
              style={{ display: "grid", gridTemplateColumns: "14px minmax(0,1fr) auto", gap: 8, alignItems: "baseline", width: "100%", minWidth: 0, padding: "7px 8px", borderRadius: "var(--radius-md)", textAlign: "left" }}
            >
              <Icon name="flag" size={12} fill style={{ color: "var(--fr-now)" }} />
              <span style={{ minWidth: 0, overflowWrap: "anywhere" }}>{d.title}</span>
              <span className="tnum" style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>{d.due.endsWith("T23:59") ? "end of day" : clock(d.due)}</span>
            </button>
          ))}
        </div>
      )}
    </span>
  )
}
