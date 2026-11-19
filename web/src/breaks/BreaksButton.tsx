// The calendar's title row has a Breaks button where the Inbox's tray was (19 Nov, you: "instead of the yellow inbox
// in the top right corner can we make that a 'breaks' clickable square"; no umbrella: "im confused on why there is an
// umbrella"). It opens your breaks, each to change, and a new one, starting today or from a day you pick, as long as
// you like; or drag across days on the calendar. The Inbox keeps its count in the sidebar and the window's title.

import { useRef, useState } from "react"
import { Icon, useMenuClose } from "@/components/fr/controls"
import { useMenuPlace } from "@/lib/menuPlace"
import { useShell } from "@/shell/ShellContext"
import { useVacations } from "./BreakDialog"
import { BREAK_ICON, modeWords, rangeWords } from "./words"

/** `square`: where the title row is short of room, an icon-sized button (a calendar with an x: days off), its name in
 * its label and tooltip, as the tray it replaced was. */
export function BreaksButton({ square }: { square?: boolean }) {
  const { today, setBreakEdit } = useShell()
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)
  const list = useRef<HTMLDivElement>(null)
  const escape = useMenuClose(open, setOpen, box, button)
  useMenuPlace(open, button, list)
  const coming = (useVacations().data?.vacations ?? []).filter((v) => v.end >= today)
  const pick = (go: () => void) => (setOpen(false), go())
  const said = coming.length === 1 ? "1 break planned" : `${coming.length} breaks planned`
  return (
    <div ref={box} className="fr-menu" onKeyDown={escape} style={{ flex: "none" }}>
      <button
        ref={button}
        className={square ? "btn btn-icon btn-secondary fr-breaks-button" : "btn btn-secondary fr-breaks-button"}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={coming.length ? `Breaks, ${said}` : "Breaks"}
        title={coming.length ? `Breaks: ${said}` : "Breaks: days off or light days"}
        onClick={() => setOpen(!open)}
        style={square ? { position: "relative" } : { gap: 6, padding: "0 11px" }}
      >
        {square ? <Icon name={BREAK_ICON} size={16} /> : "Breaks"}
        {coming.length > 0 && !square && ( // the square says it in its label and its panel
          <span className="tnum" aria-hidden style={{ minWidth: 16, height: 16, padding: "0 4px", borderRadius: 8, background: "var(--fr-break)", color: "var(--fr-ink)", fontSize: 11, fontWeight: 600, lineHeight: "16px" }}>
            {coming.length}
          </span>
        )}
      </button>
      {open && (
        <div ref={list} className="fr-float" role="dialog" aria-label="Breaks" style={{ position: "absolute", zIndex: 40, width: "min(320px, calc(100vw - 24px))", padding: 12, display: "flex", flexDirection: "column", gap: 8, borderRadius: "var(--radius-md)" }}>
          <span style={{ fontSize: 12.5, color: "var(--color-neutral-400)", textWrap: "pretty" }}>Days off or light days: repeating events pause, and a light day lists a few things to do instead of times.</span>
          {coming.length ? (
            <div style={{ display: "flex", flexDirection: "column" }}>
              {coming.map((v) => (
                <button key={v.id} className="fr-plain fr-hover" onClick={() => pick(() => setBreakEdit({ id: v.id }))} style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 1, padding: "6px 8px", borderRadius: "var(--radius-sm)", textAlign: "left", cursor: "pointer" }}>
                  <span style={{ fontWeight: 500, overflowWrap: "anywhere" }}>{v.name}</span>
                  <span className="tnum" style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>
                    {rangeWords(v.start, v.end)} · {modeWords(v.mode, v.work_min)}
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <span style={{ fontSize: 12.5 }}>None planned. Friday also suggests breaks from your calendar, in the Inbox.</span>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: 6, paddingTop: 8, boxShadow: "inset 0 1px 0 color-mix(in srgb, var(--color-text) 8%, transparent)" }}>
            <button className="btn btn-primary" onClick={() => pick(() => setBreakEdit({ start: today }))}>
              New break, starting today
            </button>
            <button className="btn btn-secondary" onClick={() => pick(() => setBreakEdit({ pickDays: true }))}>
              New break, from a day you pick…
            </button>
            <span style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>Or drag across days on the calendar.</span>
          </div>
        </div>
      )}
    </div>
  )
}
