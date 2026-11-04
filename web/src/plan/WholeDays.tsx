// The week's whole-day events (birthdays, holidays, a break), under the day headers: one bar per event across the days
// it covers, painted as the grid's events are (its pigment as a spine, an 11% wash), and opened by a click.

import { useState } from "react"
import type { Item } from "@/api/client"
import { eventPaint, wash } from "@/lib/pigments"
import { useShell } from "@/shell/ShellContext"
import { useLook } from "@/theme/LookProvider"
import { asBlock } from "./Pieces"
import { bars, folded, MAX_ROWS } from "./wholeDay"

type Event = Item & { start: string; end: string }

export function WholeDays({ events, dates }: { events: Event[]; dates: string[] }) {
  const { select } = useShell()
  const { light } = useLook()
  const [open, setOpen] = useState(false)
  const placed = bars(events, dates)
  if (!placed.length) return null
  // A pile of them keeps to three rows, the rest a count under each day that opens them all (3 Nov, stress test).
  const { shown, more } = open ? { shown: placed, more: [] as number[] } : folded(placed, dates.length)
  const folding = !open && more.some((n) => n > 0)
  const rows = placed.reduce((n, b) => Math.max(n, b.row + 1), 0)
  return (
    <div style={{ gridColumn: "2 / -1", display: "grid", gridTemplateColumns: `repeat(${dates.length}, minmax(0,1fr))`, gap: "3px 0", padding: "0 0 8px" }}>
      {shown.map(({ event, from, to, row, clippedStart, clippedEnd }) => {
        const paint = eventPaint(event, light)
        return (
          <button
            key={event.id}
            className="fr-plain fr-whole-day"
            onClick={() => select(asBlock(event))}
            title={event.title}
            style={{
              gridColumn: `${from + 1} / ${to + 2}`,
              gridRow: row + 1,
              margin: `0 ${clippedEnd ? 0 : 6}px 0 ${clippedStart ? 0 : 6}px`,
              background: wash(paint, light),
              borderLeft: clippedStart ? "none" : `3px solid ${paint}`,
              borderRadius: `${clippedStart ? 0 : 4}px ${clippedEnd ? 0 : 4}px ${clippedEnd ? 0 : 4}px ${clippedStart ? 0 : 4}px`,
            }}
          >
            {clippedStart && <span aria-hidden>‹ </span>}
            {event.title}
            {clippedEnd && <span aria-hidden> ›</span>}
          </button>
        )
      })}
      {folding &&
        more.map((n, c) =>
          n ? (
            <button key={`more${c}`} className="fr-plain fr-whole-more" onClick={() => setOpen(true)} style={{ gridColumn: c + 1, gridRow: MAX_ROWS }} title="Show every whole-day event">
              +{n} more
            </button>
          ) : null,
        )}
      {open && rows > MAX_ROWS && (
        <button className="fr-plain fr-whole-more" onClick={() => setOpen(false)} style={{ gridColumn: 1, gridRow: rows + 1 }}>
          Show less
        </button>
      )}
    </div>
  )
}
