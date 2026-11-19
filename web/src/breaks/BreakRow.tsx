// A break on the calendar (18 Nov): a band with its name across its days, and under it one line a day saying what's
// left on that day's list, which opens it. The line never grows with the list, so the calendar keeps its height ("the
// longest task list dictates how few of the calendar is seen").

import type { Schemas } from "@/api/client"
import { Icon } from "@/components/fr/controls"
import { useShell } from "@/shell/ShellContext"
import { dur } from "@/lib/format"
import { inView, rangeWords, things } from "./words"

type Day = Schemas["CalendarDay"]
type OnBreak = NonNullable<Day["vacation"]>

/** The breaks among these days, each with the run of days it covers here. */
export function breaksIn(days: Day[], dates: string[]): { vacation: OnBreak; start: string; end: string }[] {
  const out: { vacation: OnBreak; start: string; end: string }[] = []
  for (const date of dates) {
    const v = days.find((d) => d.date === date)?.vacation
    if (!v) continue
    const last = out[out.length - 1]
    if (last && last.vacation.id === v.id) last.end = date
    else out.push({ vacation: v, start: date, end: date })
  }
  return out
}

/** The first and last day of a break, from where this day is in it. */
export function breakSpan(date: string, v: OnBreak): { first: string; last: string } {
  const at = new Date(`${date}T00:00:00Z`).getTime()
  const day = 86_400_000
  const iso = (ms: number) => new Date(ms).toISOString().slice(0, 10)
  return { first: iso(at - (v.day_n - 1) * day), last: iso(at + (v.days - v.day_n) * day) }
}

/** What a break day's line says: what's left, or that it's done, or that there's nothing. */
export function lineWords(v: OnBreak): string {
  if (v.mode === "off") return "Off"
  if (!v.things) return "Nothing to do"
  const left = v.things - (v.ticked ?? 0)
  return left ? `${things(left)} to do` : "All done"
}

export function BreakRow({ days, dates }: { days: Day[]; dates: string[] }) {
  const { setBreakDay, breakDay, setBreakEdit } = useShell()
  const runs = breaksIn(days, dates)
  if (!runs.length) return null
  return (
    <div style={{ gridColumn: "2 / -1", display: "grid", gridTemplateColumns: `repeat(${dates.length}, minmax(0,1fr))`, gap: "3px 0", padding: "0 0 8px" }}>
      {runs.map(({ vacation, start, end }) => {
        const at = inView(start, end, dates)
        if (!at) return null
        const span = breakSpan(start, vacation)
        const clippedStart = span.first < start
        const clippedEnd = span.last > end
        return (
          <button
            key={`band${vacation.id}`}
            className="fr-plain fr-break-band"
            onClick={() => setBreakEdit({ id: vacation.id })}
            title={`${vacation.name}, ${rangeWords(span.first, span.last)}: click to change it`}
            style={{
              gridColumn: `${at.from + 1} / ${at.to + 2}`,
              gridRow: 1,
              margin: `0 ${clippedEnd ? 0 : 6}px 0 ${clippedStart ? 0 : 6}px`,
              borderLeft: clippedStart ? "none" : undefined,
              borderRadius: `${clippedStart ? 0 : 4}px ${clippedEnd ? 0 : 4}px ${clippedEnd ? 0 : 4}px ${clippedStart ? 0 : 4}px`,
            }}
          >
            {clippedStart && <span aria-hidden>‹ </span>}
            <Icon name="umbrella" size={12} style={{ flex: "none" }} />
            <span style={{ fontWeight: 600 }}>{vacation.name}</span>
            <span className="fr-break-band-note">{vacation.mode === "off" ? "Off" : `Light · about ${dur(vacation.work_min)} a day`}</span>
            {clippedEnd && <span aria-hidden> ›</span>}
          </button>
        )
      })}
      {dates.map((date, n) => {
        const v = days.find((d) => d.date === date)?.vacation
        if (!v) return null
        const quiet = v.mode === "off" || !v.things
        const ticked = v.ticked ?? 0
        const share = v.things ? ticked / v.things : 0
        const words = lineWords(v)
        return (
          <button
            key={`line${date}`}
            className="fr-plain fr-break-line"
            aria-pressed={breakDay === date}
            data-quiet={quiet || undefined}
            onClick={() => setBreakDay(breakDay === date ? null : date)}
            title={quiet ? `${words}: open the day` : `${words}, ${ticked} of ${things(v.things ?? 0)} done: open the day's list`}
            style={{ gridColumn: n + 1, gridRow: 2, margin: "0 6px" }}
          >
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0 }}>{words}</span>
            {!quiet && (
              <>
                <span className="fr-break-bar" aria-hidden>
                  <span style={{ width: `${Math.round(share * 100)}%` }} />
                </span>
                <span className="tnum" style={{ flex: "none" }}>
                  {ticked}/{v.things}
                </span>
              </>
            )}
          </button>
        )
      })}
    </div>
  )
}
