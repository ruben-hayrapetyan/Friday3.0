// A day's deadlines as a row under its date (13 Nov, replacing the to-do lane down each column: "the todo lane is
// super impractical to use and the tasks just get squished"; you chose this row, at most 3 a day, from a picture).
// Each day's tasks sit at its column's full width, ticked off or opened in place; a busy day shows its 3 most pressing
// (late first, then by when they're due) and "+N more", which opens the whole day. The hours below keep their width.

import { useQueryClient } from "@tanstack/react-query"
import { useEffect, useRef, useState } from "react"
import type { Schemas } from "@/api/client"
import { useToast } from "@/components/Toasts"
import { useClock } from "@/hooks/useClock"
import { runCommand } from "@/hooks/useCommand"
import { clock } from "@/lib/format"
import { useOnScreen } from "@/lib/onScreen"
import { toMin } from "@/lib/time"
import { useShell } from "@/shell/ShellContext"
import { dueBlock } from "./DueCount"

type Due = Schemas["DueMarker"]

export const DUE_ROW_MAX = 3

/** A day's deadlines as the row shows them: late first, then by when they're due; at most DUE_ROW_MAX, and how many
 * more. `now` in minutes, as the clock counts them. */
export function dayDues(dues: Due[], date: string, now: number): { shown: Due[]; all: Due[]; more: number } {
  const late = (d: Due) => toMin(d.due) < now
  const all = dues
    .filter((d) => d.due.startsWith(date))
    .sort((a, b) => Number(late(b)) - Number(late(a)) || a.due.localeCompare(b.due) || a.title.localeCompare(b.title))
  const shown = all.slice(0, all.length > DUE_ROW_MAX ? DUE_ROW_MAX : all.length)
  return { shown, all, more: all.length - shown.length }
}

/** "5pm", or "end of day" for a due at the day's last minute. */
export const dueAt = (d: Due) => (d.due.endsWith("T23:59") ? "end of day" : clock(d.due))

export function DueRow({ dues, dates, cols }: { dues: Due[]; dates: string[]; cols: string }) {
  const now = useClock()
  const days = dates.map((date) => ({ date, ...dayDues(dues, date, now) }))
  if (!days.some((d) => d.all.length)) return null
  return (
    <div aria-label="Due under the dates" style={{ gridColumn: "1 / -1", display: "grid", gridTemplateColumns: cols, borderTop: "1px solid var(--fr-hairline)", background: "color-mix(in srgb, var(--color-text) 2.5%, var(--color-surface))" }}>
      <span className="fr-eyebrow" style={{ padding: "8px 6px 0 8px" }}>
        Due
      </span>
      {days.map((d) => (
        <DueDay key={d.date} date={d.date} shown={d.shown} all={d.all} more={d.more} now={now} />
      ))}
    </div>
  )
}

function DueDay({ date, shown, all, more, now }: { date: string; shown: Due[]; all: Due[]; more: number; now: number }) {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const list = useOnScreen<HTMLDivElement>(open)
  useEffect(() => {
    if (!open) return
    const away = (e: PointerEvent) => !box.current?.contains(e.target as Node) && setOpen(false)
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false)
    document.addEventListener("pointerdown", away)
    window.addEventListener("keydown", esc)
    return () => (document.removeEventListener("pointerdown", away), window.removeEventListener("keydown", esc))
  }, [open])
  return (
    <div ref={box} aria-label={`Due ${date}`} style={{ position: "relative", minWidth: 0, display: "flex", flexDirection: "column", gap: 1, padding: "5px 4px 6px", boxShadow: "inset 1px 0 0 var(--fr-hairline)" }}>
      {shown.map((d) => (
        <DueLine key={d.item_id} due={d} late={toMin(d.due) < now} />
      ))}
      {more > 0 && (
        <button className="fr-plain fr-link" aria-expanded={open} onClick={() => setOpen(!open)} style={{ alignSelf: "flex-start", fontSize: 11.5, padding: "1px 4px" }}>
          +{more} more
        </button>
      )}
      {open && (
        <div ref={list} role="dialog" aria-label={`Everything due ${date}`} className="fr-float" style={{ position: "absolute", top: "calc(100% + 4px)", left: 0, zIndex: 20, width: "min(280px, calc(100vw - 24px))", maxHeight: "min(420px, 60vh)", overflowY: "auto", padding: 6, display: "flex", flexDirection: "column", gap: 1 }}>
          <span className="fr-eyebrow" style={{ padding: "2px 6px 6px" }}>
            {all.length} due
          </span>
          {all.map((d) => (
            <DueLine key={d.item_id} due={d} late={toMin(d.due) < now} roomy />
          ))}
        </div>
      )}
    </div>
  )
}

/** One deadline: tick it off, or open it; its title on one line, its time at the right. */
function DueLine({ due, late, roomy = false }: { due: Due; late: boolean; roomy?: boolean }) {
  const { select } = useShell()
  const client = useQueryClient()
  const toast = useToast()
  const color = late ? "var(--fr-now)" : undefined
  return (
    <div className="fr-hover" title={`${due.title}, due ${dueAt(due)}`} style={{ display: "grid", gridTemplateColumns: "15px minmax(0,1fr) auto", alignItems: "center", gap: 6, padding: roomy ? "5px 6px" : "2px 4px", borderRadius: "var(--radius-sm)", minWidth: 0 }}>
      <button className="fr-check" role="checkbox" aria-checked="false" aria-label={`Mark ${due.title} done`} onClick={() => runCommand(client, toast, "done", { id: due.item_id })} style={{ width: 13, height: 13, ...(late ? { borderColor: "var(--fr-now)" } : {}) }} />
      <button className="fr-plain" onClick={() => select(dueBlock(due))} style={{ minWidth: 0, textAlign: "left", fontSize: roomy ? 13 : 12, lineHeight: 1.3, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", color }}>
        {due.title}
      </button>
      {/* in the row, a time only when it isn't the day's end: "end of day" took a week column's room from the title */}
      {(roomy || !due.due.endsWith("T23:59")) && (
        <span className="tnum" style={{ fontSize: 10.5, color: color ?? "var(--color-neutral-500)", whiteSpace: "nowrap" }}>
          {dueAt(due)}
        </span>
      )}
    </div>
  )
}
