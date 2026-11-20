// The deadline shelf: projects and exams as rows on six weeks across. Each row's bar runs from today to
// its due (an exam's start), filled as far as it's done, with its next step or prep to tick in place.

import { useState } from "react"
import { Check, H, Icon } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { weekday } from "@/lib/format"
import { useLook } from "@/theme/LookProvider"
import { aimFor, at, left, milestones, reached, type Row, STATUS, weekStarts, WEEKS } from "./model"

const TONE: Record<Row["status"], string> = {
  on_track: "var(--color-accent-300)",
  ready: "var(--color-accent-300)",
  late: "var(--fr-due)",
  unplanned: "var(--fr-warn)",
  no_prep: "var(--color-neutral-400)",
  done: "var(--color-neutral-400)",
}
const LINE = "color-mix(in srgb, var(--color-text) 7%, transparent)"
// The row's columns: what it is, and the six weeks. Narrow windows give the name less room, never the weeks none.
const COLUMNS = "minmax(150px, 260px) minmax(0,1fr)"

export function Deadlines({ rows, today, opened, early, onOpen }: { rows: Row[]; today: string; opened: { kind: string; id: number } | null; early: Record<number, number>; onOpen: (r: Row) => void }) {
  const weeks = weekStarts(today)
  return (
    <section aria-label="With a deadline" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", gap: 10, alignItems: "baseline", flexWrap: "wrap", paddingBottom: 6 }}>
        <H size={20}>With a deadline</H>
        <span className="fr-kicker">{rows.length} · soonest first</span>
      </div>
      <div aria-hidden style={{ display: "grid", gridTemplateColumns: COLUMNS, fontSize: 11, color: "var(--color-neutral-400)", paddingBottom: 4 }}>
        <span />
        <span style={{ display: "grid", gridTemplateColumns: `repeat(${WEEKS}, minmax(0,1fr))`, minWidth: 0 }}>
          {weeks.map((w, i) => (
            <span key={w} className="tnum" style={{ paddingLeft: 4, boxShadow: `inset 1px 0 0 ${LINE}`, whiteSpace: "nowrap", overflow: "hidden" }}>
              {i ? `${weekday(w)} ${Number(w.slice(8))}` : "This week"}
            </span>
          ))}
        </span>
      </div>
      {rows.map((r) => (
        <DeadlineRow key={`${r.kind}${r.id}`} r={r} today={today} early={r.kind === "project" ? (early[r.id] ?? 0) : 0} lit={opened?.kind === r.kind && opened.id === r.id} onOpen={() => onOpen(r)} />
      ))}
      {!rows.length && (
        <span className="fr-kicker" style={{ textWrap: "pretty" }}>
          Nothing with a deadline. A project is something with steps, like an essay or a presentation; exams come in from your class calendar. Add one with New project or New exam.
        </span>
      )}
    </section>
  )
}

function DeadlineRow({ r, today, early, lit, onOpen }: { r: Row; today: string; early: number; lit: boolean; onOpen: () => void }) {
  const { color } = useLook()
  const done = useCommand("done", { label: (o) => `${o.result.item.title}: done` })
  // A step ticked shows ticked at once; the next one comes when the server says which it is.
  const [ticked, setTicked] = useState<number[]>([])
  const step = r.steps.find((s) => !s.done && !ticked.includes(s.id))
  const tint = color(r.area, r.preset)
  const flag = r.due && `${weekday(r.due.slice(0, 10))} ${Number(r.due.slice(8, 10))}`
  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`${r.title}, ${STATUS[r.status].toLowerCase()}`}
      className="fr-hover-soft"
      onClick={onOpen}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && e.target === e.currentTarget && (e.preventDefault(), onOpen())}
      style={{ display: "grid", gridTemplateColumns: COLUMNS, alignItems: "center", minHeight: 54, padding: "6px 0", cursor: "pointer", borderRadius: "var(--radius-md)", background: lit ? "color-mix(in srgb, var(--color-accent) 10%, transparent)" : undefined, boxShadow: `inset 0 -1px 0 ${LINE}` }}
    >
      <span style={{ display: "flex", gap: 10, alignItems: "center", minWidth: 0, padding: "0 12px 0 6px" }}>
        <span style={{ width: 4, alignSelf: "stretch", borderRadius: 2, background: tint, flex: "none" }} />
        <span style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
          <span style={{ display: "flex", gap: 6, alignItems: "center", minWidth: 0 }}>
            {r.kind === "exam" && <Icon name="exam" size={12} style={{ color: "var(--color-neutral-400)", flex: "none" }} />}
            <span style={{ fontWeight: 600, fontSize: 13.5, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.title}</span>
          </span>
          {step ? (
            <span style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12, color: "var(--color-neutral-400)", minWidth: 0 }}>
              <span onClick={(e) => e.stopPropagation()} style={{ display: "inline-flex", flex: "none" }}>
                <Check small done={false} onToggle={() => (setTicked([...ticked, step.id]), done({ id: step.id }))} />
              </span>
              <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{step.title}</span>
            </span>
          ) : (
            <span className="fr-kicker">{r.steps.length ? (r.kind === "exam" ? "All prep done" : "All steps done") : r.kind === "exam" ? "No prep yet" : "One piece of work"}</span>
          )}
          <span className="fr-kicker tnum" style={{ color: TONE[r.status] }}>
            {STATUS[r.status]} · {left(r)} left
          </span>
        </span>
      </span>
      <span style={{ position: "relative", height: 26, minWidth: 0 }}>
        {Array.from({ length: WEEKS - 1 }, (_, i) => (
          <span key={i} style={{ position: "absolute", top: -6, bottom: -6, left: `${((i + 1) / WEEKS) * 100}%`, width: 1, background: LINE }} />
        ))}
        {r.due && (
          <span data-bar style={{ position: "absolute", left: 0, width: `${at(r.due, today)}%`, top: 7, height: 12, borderRadius: 6, overflow: "hidden", background: `color-mix(in srgb, ${tint} 22%, transparent)` }}>
            <span data-fill style={{ display: "block", height: "100%", width: `${reached(r, today) * 100}%`, background: tint }} />
          </span>
        )}
        {r.due && early > 0 && (
          <span data-aim title={`Aims to finish ${early} ${early === 1 ? "day" : "days"} early`} style={{ position: "absolute", left: `${at(aimFor(r.due, early), today)}%`, top: 3, height: 20, borderLeft: `2px dotted ${tint}` }} />
        )}
        {milestones(r).map((m) => (
          <span key={m.id} data-milestone title={`${m.title}, due ${weekday((m.due ?? "").slice(0, 10))} ${Number((m.due ?? "").slice(8, 10))}${m.done ? ", done" : ""}`} style={{ position: "absolute", left: `calc(${at(m.due ?? "", today)}% - 5px)`, top: 8, width: 10, height: 10, transform: "rotate(45deg)", background: m.done ? tint : "var(--color-surface)", boxShadow: `0 0 0 2px ${tint}` }} />
        ))}
        {flag && (
          <span className="tnum" style={{ position: "absolute", ...(at(r.due ?? "", today) > 82 ? { right: 0 } : { left: `calc(${at(r.due ?? "", today)}% + 6px)` }), top: 5, fontSize: 11, color: r.hard ? "var(--fr-due)" : "var(--color-neutral-400)", whiteSpace: "nowrap" }}>
            {r.kind === "exam" ? "Exam" : "Due"} {flag}
          </span>
        )}
      </span>
    </div>
  )
}

