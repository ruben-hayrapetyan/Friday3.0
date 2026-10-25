// A project's timeline: a small Gantt chart, one lane per step in order, each planned session a bar in the
// project's colour across the days up to the deadline, with today, now and the due date marked.

import type { Item, Schemas } from "@/api/client"
import { H, Icon } from "@/components/fr/controls"
import { useClock } from "@/hooks/useClock"
import { useHorizon } from "@/hooks/queries"
import { clock, dur, weekday, when } from "@/lib/format"
import { dayRange, fromMin, toMin } from "@/lib/time"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"
import { ahead, dueAt, frame, place } from "./gantt"

type Project = Schemas["ProjectOut"]
type Block = Schemas["BlockOut"]

const HEAD = 44 // the day labels, and the due date's tag under them
const LANE = 32
const RULE = "color-mix(in srgb, var(--color-text) 7%, transparent)"

export function Timeline({ p, steps, tone }: { p: Project; steps: Item[]; tone: string }) {
  const { today, layout } = useShell()
  const { skinOf } = useLook()
  const now = useClock()
  const blocks = useHorizon().data?.blocks ?? []
  const lanes = steps.map((s) => ({ s, bs: blocks.filter((b) => b.item_id === s.id).sort((a, b) => a.start.localeCompare(b.start)) }))
  const due = p.item.due ? dueAt(p.item.due) : null
  const f = frame(today, due, lanes.flatMap((l) => l.bs))
  const x = (t: string) => place(f, t) * 100
  const label = layout.tight ? 112 : 176 // the steps' names, held still while the days scroll
  const day = layout.tight ? 54 : 72 // the narrowest a day gets before the chart scrolls
  const nowAt = fromMin(now)
  const showNow = nowAt.slice(0, 10) >= f.first && x(nowAt) > 0 && x(nowAt) < 100
  const finish = p.planned_finish
  const slack = finish && due ? toMin(due) - toMin(finish) : null
  const line =
    p.status === "unplanned"
      ? "Some steps aren't planned yet: give them a length."
      : slack === null
        ? ""
        : slack >= 0
          ? `Planned to finish ${when(finish as string, today)}, ${ahead(slack)} before it's due.`
          : `Planned to finish ${when(finish as string, today)}, after it's due.`
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
        <H size={18}>Timeline</H>
        <span className="fr-kicker">When each step is planned, up to the deadline</span>
      </div>
      <div style={{ overflowX: "auto", borderRadius: "var(--radius-md)", background: "var(--color-bg)", boxShadow: `0 0 0 1px ${RULE}` }}>
        <div style={{ display: "flex", minWidth: label + f.days * day }}>
          <div style={{ position: "sticky", left: 0, zIndex: 3, flex: "none", width: label, background: "var(--color-bg)", boxShadow: `inset -1px 0 0 ${RULE}` }}>
            <div style={{ height: HEAD, display: "flex", alignItems: "flex-end", padding: "0 10px 6px", fontSize: 11, color: "var(--color-neutral-500)" }}>Step</div>
            {lanes.map(({ s }, i) => {
              const done = s.status === "done"
              return (
                <div key={s.id} title={s.title} style={{ height: LANE, display: "flex", alignItems: "center", gap: 8, padding: "0 10px", boxShadow: `inset 0 1px 0 ${RULE}`, fontSize: 12, color: done ? "var(--color-neutral-500)" : "var(--color-text)" }}>
                  <span className="tnum" style={{ flex: "none", width: 14, textAlign: "center", fontSize: 11, color: done ? "var(--color-accent-300)" : "var(--color-neutral-500)" }}>
                    {done ? <Icon name="check" size={12} /> : i + 1}
                  </span>
                  <span style={{ minWidth: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", textDecoration: done ? "line-through" : undefined }}>{s.title}</span>
                </div>
              )
            })}
          </div>
          <div style={{ position: "relative", flex: 1, height: HEAD + lanes.length * LANE + 8, overflow: "hidden" }}>
            {dayRange(f.first, f.days).map((d, i) => {
              const isToday = d === today
              const weekend = ["Sat", "Sun"].includes(weekday(d))
              const wash = isToday ? "color-mix(in srgb, var(--color-accent) 7%, transparent)" : weekend ? "color-mix(in srgb, var(--color-text) 2.5%, transparent)" : undefined
              return (
                <div key={d} style={{ position: "absolute", top: 0, bottom: 0, left: `${(i / f.days) * 100}%`, width: `${100 / f.days}%`, background: wash, boxShadow: i ? `inset 1px 0 0 ${RULE}` : undefined }}>
                  <span className="tnum" style={{ position: "absolute", top: 7, left: 0, right: 0, textAlign: "center", fontSize: 11, whiteSpace: "nowrap", fontWeight: isToday ? 600 : 400, color: isToday ? "var(--color-accent-300)" : "var(--color-neutral-500)" }}>
                    {weekday(d)} {Number(d.slice(8, 10))}
                  </span>
                </div>
              )
            })}
            {lanes.map(({ s }, i) => (
              <div key={s.id} style={{ position: "absolute", left: 0, right: 0, top: HEAD + i * LANE, height: 1, background: RULE }} />
            ))}
            {due && <Due at={x(due)} text={`Due ${weekday(due)} ${Number(due.slice(8, 10))}, ${clock(due)}`} />}
            {showNow && <span title={`Now, ${clock(nowAt)}`} style={{ position: "absolute", zIndex: 2, top: HEAD - 16, bottom: 0, left: `${x(nowAt)}%`, width: 2, marginLeft: -1, borderRadius: 1, background: "var(--fr-now)" }} />}
            {lanes.map(({ s, bs }, i) => (
              <Lane key={s.id} top={HEAD + i * LANE} title={s.title} bs={bs} x={x} skin={skinOf(s.status === "done" ? "done" : "planned", p.item.area, undefined, p.item.preset)} done={s.status === "done"} today={today} />
            ))}
          </div>
        </div>
      </div>
      {line && <span style={{ fontSize: 12, color: tone }}>{line}</span>}
    </div>
  )
}

/** The deadline: a red line through every lane, its date and time on a tag under the day labels, on whichever side
 * of the line has room. */
function Due({ at, text }: { at: number; text: string }) {
  const left = at > 50
  return (
    <>
      <span style={{ position: "absolute", zIndex: 2, top: HEAD - 20, bottom: 0, left: `${at}%`, width: 2, marginLeft: at >= 100 ? -2 : -1, background: "var(--fr-due)" }} />
      <span
        className="tnum"
        style={{
          position: "absolute",
          zIndex: 2,
          top: HEAD - 21,
          ...(left ? { right: `calc(${100 - at}% + 4px)` } : { left: `calc(${at}% + 4px)` }),
          padding: "1px 6px",
          borderRadius: 4,
          fontSize: 10.5,
          fontWeight: 500,
          whiteSpace: "nowrap",
          color: "var(--fr-due)",
          background: "color-mix(in srgb, var(--fr-due) 14%, var(--color-bg))",
        }}
      >
        {text}
      </span>
    </>
  )
}

/** One step's sessions, each a bar from its start to its end (never thinner than 6px), the pigment on its spine
 * and a wash of it, as the calendar paints blocks; beside them, when it's planned. */
function Lane({ top, title, bs, x, skin, done, today }: { top: number; title: string; bs: Block[]; x: (t: string) => number; skin: { bg: string; stripe: string; sub: string }; done: boolean; today: string }) {
  const quiet = { position: "absolute", top: 0, bottom: 0, display: "flex", alignItems: "center", fontSize: 11, whiteSpace: "nowrap", color: "var(--color-neutral-500)" } as const
  if (!bs.length) {
    return (
      <div style={{ position: "absolute", left: 0, right: 0, top, height: LANE }}>
        <span style={{ ...quiet, left: 10, fontStyle: "italic", opacity: 0.7 }}>{done ? "done" : "not planned"}</span>
      </div>
    )
  }
  const from = x(bs[0].start)
  const to = x(bs[bs.length - 1].end)
  const minutes = bs.reduce((sum, b) => sum + toMin(b.end) - toMin(b.start), 0)
  const note = bs.length === 1 ? `${when(bs[0].start, today)}–${clock(bs[0].end)}` : `${bs.length} sessions, ${dur(minutes)}`
  return (
    <div style={{ position: "absolute", left: 0, right: 0, top, height: LANE, zIndex: 1 }}>
      {bs.map((b) => {
        const say = `${title} · ${weekday(b.start)} ${clock(b.start)}–${clock(b.end)}`
        return (
          <div
            key={b.key}
            title={say}
            aria-label={say}
            style={{
              position: "absolute",
              top: 8,
              height: LANE - 16,
              left: `${x(b.start)}%`,
              width: `max(6px, ${x(b.end) - x(b.start)}%)`,
              borderRadius: 4,
              background: skin.bg,
              boxShadow: `inset 3px 0 0 ${skin.stripe}`,
              opacity: b.tentative ? 0.6 : 1,
            }}
          />
        )
      })}
      {/* on whichever side of the bars has more room */}
      <span className="tnum" style={{ ...quiet, ...(100 - to >= from ? { left: `calc(${to}% + 12px)` } : { right: `calc(${100 - from}% + 8px)` }), color: skin.sub }}>
        {note}
      </span>
    </div>
  )
}
