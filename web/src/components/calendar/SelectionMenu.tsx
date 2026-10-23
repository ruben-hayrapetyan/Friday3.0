// Selected empty time (DESIGN §18.4): Shove it, add a fixed item there, or show what fits and pin one.

import { useEffect, useRef, useState } from "react"
import { query, type Schemas } from "@/api/client"
import { Icon } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import type { Selection } from "@/hooks/useDrop"
import { clock, dur, when } from "@/lib/format"
import { fromMin, toMin } from "@/lib/time"
import { draftAt } from "@/shell/EventPane"
import { useShell } from "@/shell/ShellContext"

interface Props {
  selection: Selection
  today: string
  onShove: (range: string) => void
  onClose: () => void
}

export function SelectionMenu({ selection, today, onShove, onClose }: Props) {
  const { start, end } = selection
  const minutes = toMin(end) - toMin(start)
  const [mode, setMode] = useState<"menu" | "fits">("menu")
  const { setEvent } = useShell()
  const [fits, setFits] = useState<Schemas["Swap"][] | null>(null)
  const pin = useCommand("pin")
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const away = (e: PointerEvent) => box.current && !box.current.contains(e.target as Node) && onClose()
    const escape = (e: KeyboardEvent) => e.key === "Escape" && onClose()
    window.addEventListener("pointerdown", away)
    window.addEventListener("keydown", escape)
    return () => {
      window.removeEventListener("pointerdown", away)
      window.removeEventListener("keydown", escape)
    }
  }, [onClose])
  const run = async (promise: Promise<unknown>) => {
    if (await promise) onClose()
  }
  const showFits = async () => {
    setMode("fits")
    setFits(await query("fits", { minutes }).catch(() => []))
  }
  return (
    <div
      ref={box}
      className="fr-float"
      style={{ position: "fixed", zIndex: 50, width: 260, padding: 8, display: "flex", flexDirection: "column", gap: 2, left: Math.min(selection.x, window.innerWidth - 270), top: Math.min(selection.y, window.innerHeight - 220) }}
    >
      <div className="tnum fr-kicker" style={{ padding: "2px 6px 6px" }}>
        {when(start, today)}–{clock(end)} · {dur(minutes)}
      </div>
      {mode === "menu" && (
        <>
          <Item icon="hand-palm" onClick={() => onShove(`${clock(start)}-${clock(end)} ${start.slice(0, 10)}`)}>
            Shove this time
          </Item>
          <Item icon="calendar-plus" onClick={() => (setEvent(draftAt(start, end)), onClose())}>
            Add a fixed event here
          </Item>
          <Item icon="list-magnifying-glass" onClick={showFits}>
            Show what fits
          </Item>
        </>
      )}
      {mode === "fits" &&
        (fits === null ? (
          <div className="fr-kicker" style={{ padding: "4px 6px" }}>
            Looking…
          </div>
        ) : fits.length === 0 ? (
          <div className="fr-kicker" style={{ padding: "4px 6px" }}>
            Nothing fits without something going late.
          </div>
        ) : (
          fits.map((f) => (
            <Item
              key={f.item_id}
              onClick={() =>
                run(pin({ id: f.item_id, start, end: fromMin(toMin(start) + Math.min(minutes, f.minutes)), kind: "preferred" }))
              }
            >
              <span style={{ flex: 1 }}>{f.title}</span>
              <span className="tnum fr-kicker">{dur(f.minutes)}</span>
            </Item>
          ))
        ))}
    </div>
  )
}

function Item({ icon, onClick, children }: { icon?: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button className="fr-plain fr-hover-accent" onClick={onClick} style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 8px", borderRadius: "var(--radius-md)" }}>
      {icon && <Icon name={icon} size={15} style={{ color: "var(--color-neutral-300)" }} />}
      {children}
    </button>
  )
}
