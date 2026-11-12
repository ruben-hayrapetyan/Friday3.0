// One exam ahead, as a card: when it is and how far off, in its course's colour; how ready you are; each piece of
// prep with where it stands in the plan (tick it off, open it); a line to add more prep; and exam focus, if it's on.

import { useRef, useState } from "react"
import { useNavigate } from "react-router"
import type { Block } from "@/api/client"
import { Check, H, Icon } from "@/components/fr/controls"
import { useClock } from "@/hooks/useClock"
import { useCommand } from "@/hooks/useCommand"
import { dur, when } from "@/lib/format"
import { toMin } from "@/lib/time"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"
import { countdown, course, type Exam, type PrepState, prepState, readiness, sitting, summary } from "./exams"
import { Bar, card, EXAM_STATUS, RULE, StatusTag, TONE } from "./parts"

const MONTH = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
const WEEKDAY = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

export function ExamCard({ exam, blocks }: { exam: Exam; blocks: Block[] }) {
  const { today, setPlace } = useShell()
  const { color, light } = useLook()
  const now = useClock()
  const navigate = useNavigate()
  const e = exam.item
  const start = e.start ?? `${today}T00:00`
  const end = e.end ?? start
  const area = e.area ?? exam.prep.find((p) => p.item.area)?.item.area ?? null
  const tint = color(area)
  const states = exam.prep.map((p) => prepState(p, blocks, start, today))
  const pct = readiness(exam)
  const [label, tone] = EXAM_STATUS[exam.status]
  const line = summary(exam, states, today)
  const away = countdown(start, end, now, today)
  const soon = away === "Now" || away === "Today" || away === "Tomorrow"
  const focusing = exam.focus_from && toMin(exam.focus_from) <= now
  return (
    <article style={card(tint, light)} aria-label={`${e.title}, ${sitting(start, end)}`}>
      <div style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 6 }}>
          <span className="fr-eyebrow" style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
            <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{course(e) ?? "Exam"}</span>
            <span style={{ flex: "none", color: soon ? "var(--fr-due)" : "var(--color-neutral-500)" }}>· {away}</span>
          </span>
          <H size={21} style={{ overflowWrap: "anywhere" }}>
            {e.title}
          </H>
          <span className="tnum" style={{ fontSize: 12, color: "var(--color-neutral-300)" }}>
            {sitting(start, end)}
          </span>
        </div>
        <DateTile date={start.slice(0, 10)} tint={tint} />
      </div>

      {exam.prep.length > 0 && (
      <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
        <div className="tnum" style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
          <span style={{ color: "var(--color-text)", fontWeight: 600 }}>{pct === null ? "—" : `${pct}%`}</span>
          <span style={{ flex: 1, minWidth: 0, color: "var(--color-neutral-400)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {exam.remaining_min ? `${dur(exam.done_min)} done · ${dur(exam.remaining_min)} to go` : `${dur(exam.done_min)} of prep, all done`}
          </span>
          <StatusTag label={label} tone={tone} />
        </div>
        <Bar pct={pct ?? 0} color={tint} />
      </div>
      )}

      {states.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column" }}>
          <span className="fr-eyebrow" style={{ paddingBottom: 4 }}>
            Prep
          </span>
          {states.map((s) => (
            <PrepRow key={s.item.id} s={s} onOpen={() => navigate(`/todo?item=${s.item.id}`)} />
          ))}
        </div>
      )}
      <AddPrep exam={exam} area={area} />

      <div style={{ display: "flex", flexDirection: "column", gap: 6, paddingTop: 2 }}>
        <span style={{ fontSize: 12.5, color: TONE[line.tone], textWrap: "pretty" }}>{line.text}</span>
        {exam.focus_from && (
          <span style={{ display: "flex", gap: 6, alignItems: "baseline", fontSize: 12, color: "var(--color-neutral-400)", textWrap: "pretty" }}>
            <Icon name="target" size={12} style={{ flex: "none", color: tint }} />
            {focusing ? "Focus days: other courses' work waits until after it." : `Focus from ${when(exam.focus_from, today)}: other courses' work waits until after it.`}
          </span>
        )}
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginTop: -6 }}>
        <button className="fr-plain fr-link" onClick={() => (setPlace({ view: 1, first: start.slice(0, 10) }), navigate("/"))} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12 }}>
          <Icon name="calendar-dots" size={13} />
          See the day
        </button>
      </div>
    </article>
  )
}

/** The exam's day as a little tear-off calendar page: the month in the course's colour, the day large. */
function DateTile({ date, tint }: { date: string; tint: string }) {
  const day = new Date(toMin(date) * 60000)
  return (
    <div aria-hidden style={{ flex: "none", width: 54, borderRadius: 8, overflow: "hidden", textAlign: "center", background: "var(--color-bg)", boxShadow: `0 0 0 1px ${RULE}` }}>
      <div className="fr-mono" style={{ padding: "3px 0", fontSize: 11, fontWeight: 600, letterSpacing: "0.12em", color: "#fff", background: tint }}>
        {MONTH[day.getUTCMonth()].toUpperCase()}
      </div>
      <div className="fr-h tnum" style={{ fontSize: 24, lineHeight: 1, padding: "6px 0 2px" }}>
        {day.getUTCDate()}
      </div>
      <div className="fr-mono" style={{ fontSize: 11, paddingBottom: 5, color: "var(--color-neutral-400)" }}>
        {WEEKDAY[day.getUTCDay()]}
      </div>
    </div>
  )
}

const STATE_COLOR: Record<PrepState["state"], string> = {
  done: "var(--color-neutral-500)",
  planned: "var(--color-neutral-400)",
  late: "var(--fr-due)",
  unplanned: "var(--fr-warn)",
}

function PrepRow({ s, onOpen }: { s: PrepState; onOpen: () => void }) {
  const done = useCommand("done", { label: () => `${s.item.title}: done` })
  const reopen = useCommand("reopen", { label: () => "Open again" })
  const isDone = s.state === "done"
  const length = isDone ? (s.item.duration_min ?? 0) : s.left
  return (
    <div className="fr-row" style={{ display: "grid", gridTemplateColumns: "18px minmax(0,1fr) auto", gap: 10, alignItems: "start", padding: "8px 0" }}>
      <span style={{ paddingTop: 1 }}>
        <Check small done={isDone} onToggle={() => (isDone ? reopen({ id: s.item.id }) : done({ id: s.item.id }))} />
      </span>
      <button className="fr-plain fr-hover-text" onClick={onOpen} title="Open" style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
        <span style={{ fontWeight: 500, overflowWrap: "anywhere", textDecoration: isDone ? "line-through" : undefined, color: isDone ? "var(--color-neutral-500)" : undefined }}>{s.item.title}</span>
        <span className="tnum" style={{ fontSize: 11.5, color: STATE_COLOR[s.state], display: "flex", alignItems: "center", gap: 4 }}>
          {s.state === "unplanned" && <Icon name="warning-circle" size={11} />}
          {s.state === "late" && <Icon name="clock-countdown" size={11} />}
          {s.note}
        </span>
      </button>
      <span className="tnum" style={{ fontSize: 12, color: "var(--color-neutral-400)", paddingTop: 1 }}>
        {length ? dur(length) : ""}
      </span>
    </div>
  )
}

/** A line to add prep: due when the exam starts, made `before` it, in its course. */
function AddPrep({ exam, area }: { exam: Exam; area: string | null }) {
  const add = useCommand("add", { label: () => "Prep added" })
  const [text, setText] = useState("")
  const sending = useRef(false) // ↩ twice, or ↩ and Add, adds it once
  const submit = async () => {
    if (!text.trim() || sending.current) return
    sending.current = true
    try {
      const out = await add({ text, preset: "Exam prep", due: exam.item.start, area, before: [exam.item.id] })
      if (out) setText("")
    } finally {
      sending.current = false
    }
  }
  return (
    <div className="fr-row" style={{ display: "flex", gap: 10, alignItems: "center", padding: "8px 0 0", marginTop: exam.prep.length ? -14 : 0 }}>
      <Icon name="plus" size={14} style={{ flex: "none", width: 18, textAlign: "center", color: "var(--color-neutral-500)" }} />
      <input
        value={text}
        onChange={(ev) => setText(ev.target.value)}
        onKeyDown={(ev) => ev.key === "Enter" && submit()}
        placeholder={exam.prep.length ? "Add prep ~1h" : "Add prep, like a practice exam ~2h"}
        aria-label={`Add prep for ${exam.item.title}`}
        style={{ flex: 1, minWidth: 0, border: 0, outline: 0, background: "transparent", color: "var(--color-text)", font: "inherit", fontSize: 12.5 }}
      />
      {text.trim() && (
        <button className="btn btn-ghost" onClick={submit} style={{ fontSize: 12, padding: "2px 10px" }}>
          Add
        </button>
      )}
    </div>
  )
}
