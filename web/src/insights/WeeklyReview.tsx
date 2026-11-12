// The week's look back (v22; Insights → This week since 27 Oct): where the time went by tag, what you finished, what
// carries over (keep, next week or drop), what's coming up, how the week felt, the pace for next week and a note for
// next Sunday. Choices apply when you finish.

import { useQuery } from "@tanstack/react-query"
import { useRef, useState } from "react"
import { useNavigate } from "react-router"
import { query, type Schemas } from "@/api/client"
import { H, Icon, Seg } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { usePaces } from "@/hooks/queries"
import { weekday, when } from "@/lib/format"
import { addDays } from "@/lib/time"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
const FEELS = ["Rough", "Heavy", "Fine", "Good", "Great"]
type Carry = "Keep" | "Next week" | "Drop"

export function WeeklyReview() {
  const { today } = useShell()
  const week = useQuery({ queryKey: ["week_review", today], queryFn: () => query("week_review", { date: today }) }).data
  if (!week) return <div className="fr-panel" />
  const full = { ...week, finished: week.finished ?? [], carried: week.carried ?? [], coming: week.coming ?? [], note: week.note ?? {} }
  return <Week key={week.start} week={full} />
}

type Full = Schemas["WeekOut"] & Required<Pick<Schemas["WeekOut"], "finished" | "carried" | "coming" | "note">>

function Week({ week }: { week: Full }) {
  const { today } = useShell()
  const { color } = useLook()
  const navigate = useNavigate()
  const paces = usePaces().data
  const [carry, setCarry] = useState<Record<number, Carry>>({})
  const [feel, setFeel] = useState(week.note?.feel ?? null)
  const [notes, setNotes] = useState(week.note?.notes ?? "")
  const [pace, setPace] = useState<string | null>(null)
  const [finished, setFinished] = useState(false)
  const note = useCommand("week_note", { label: () => "Saved" })
  const edit = useCommand("edit", { label: () => "Moved to next week" })
  const drop = useCommand("drop", { label: () => "Dropped" })
  const setPaceCmd = useCommand("pace", { label: (o) => o.result.message })
  const groups = week.groups ?? []
  const planned = week.areas.reduce((s, a) => s + a.planned_h, 0)
  const actual = week.areas.reduce((s, a) => s + a.actual_h, 0)
  const top = Math.max(1, ...groups.map((g) => Math.max(g.planned_h, g.actual_h)))
  const suggested = feel === "Rough" || feel === "Heavy" ? "Easy" : feel === "Great" ? "Push" : (paces?.default ?? "Normal")
  const nextMonday = addDays(week.end, 1)
  // "Next week" starts it next Monday: only for work due after then (12 Nov: one due sooner was refused, and the
  // review still said it was done)
  const canWait = (c: { when: string }) => !c.when || c.when >= `${nextMonday}T00:00`
  // Once: a second click while it saves dropped and moved the same work again (audit, 12 Nov).
  const sending = useRef(false)
  const [busy, setBusy] = useState(false)
  const finish = async () => {
    if (sending.current) return
    sending.current = true
    setBusy(true)
    try {
      await finishWeek()
    } finally {
      sending.current = false
      setBusy(false)
    }
  }
  const finishWeek = async () => {
    let failed = false
    for (const c of week.carried) {
      if (carry[c.item_id] === "Drop") failed = !(await drop({ id: c.item_id })) || failed
      if (carry[c.item_id] === "Next week" && canWait(c)) failed = !(await edit({ id: c.item_id, release: `${nextMonday}T00:00` })) || failed
    }
    const chosen = pace ?? suggested
    if (paces && chosen !== paces.now_label) failed = !(await setPaceCmd({ name: chosen, for_days: 7 })) || failed
    if (!failed) setFinished(true) // a refusal is said in its toast; the review stays open to try again
  }
  // "26 October – 1 November" across two months, "19–25 October" within one
  const month = (d: string) => MONTHS[Number(d.slice(5, 7)) - 1]
  const range = month(week.start) === month(week.end) ? `${Number(week.start.slice(8, 10))}–${Number(week.end.slice(8, 10))} ${month(week.end)}` : `${Number(week.start.slice(8, 10))} ${month(week.start)} – ${Number(week.end.slice(8, 10))} ${month(week.end)}`
  return (
    <div className="fr-panel" style={{ overflowY: "auto" }}>
      <div className="fr-gutter" style={{ maxWidth: 1040, padding: "32px 40px 150px", display: "flex", flexDirection: "column", gap: 34 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <H size={36}>Week of {range}</H>
          <span style={{ fontSize: 15, color: "var(--color-neutral-300)", textWrap: "pretty", maxWidth: 640 }}>
            You finished {week.finished.length} {week.finished.length === 1 ? "thing" : "things"} and worked {actual.toFixed(1)} of {planned.toFixed(1)} planned hours.
            {week.carried.length ? ` ${week.carried.length} carry over.` : " Nothing carries over."}
          </span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <H size={18}>Where the time went</H>
            {/* 31 Oct: "it doesn't provide any info" — what the bars are, and what each row holds */}
            <span style={{ fontSize: 13, color: "var(--color-neutral-400)", textWrap: "pretty", maxWidth: 640 }}>
              {weekday(week.start)} to {week.end < today ? weekday(week.end) : "today"}: the filled bar is time you timed or marked done, the outline what Friday planned. A row is a tag, or the course a to-do's title names, or its kind.
            </span>
          </div>
          {groups.map((g) => {
            const c = color(g.area, g.preset)
            const listed = g.items.filter((i) => i.planned_h || i.actual_h) // under three minutes says nothing
            const shown = listed.slice(0, 3)
            return (
              <div key={`${g.by}:${g.name}`} style={{ display: "grid", gridTemplateColumns: "150px minmax(0,1fr) 110px", gap: "4px 16px", alignItems: "center" }}>
                <span style={{ display: "flex", gap: 8, alignItems: "center", minWidth: 0 }}>
                  <span className="fr-swatch" style={{ background: c }} />
                  <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{g.name}</span>
                </span>
                <div style={{ position: "relative", height: 10, borderRadius: 5, background: "color-mix(in srgb, var(--color-text) 6%, transparent)" }}>
                  <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${(g.planned_h / top) * 100}%`, borderRadius: 5, boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${c} 45%, transparent)` }} />
                  <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${(g.actual_h / top) * 100}%`, borderRadius: 5, background: c }} />
                </div>
                <span className="tnum" style={{ fontSize: 12, color: "var(--color-neutral-400)", textAlign: "right" }}>
                  {g.planned_h ? `${hours(g.actual_h)} of ${hours(g.planned_h)}` : `${hours(g.actual_h)} done`}
                </span>
                <span style={{ gridColumn: "2 / 4", fontSize: 12, color: "var(--color-neutral-500)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {shown.map((i, n) => (
                    <span key={i.item_id}>
                      {n > 0 && " · "}
                      <button className="fr-plain fr-hover-text" onClick={() => navigate(`/todo?item=${i.item_id}`)} style={{ font: "inherit", color: "var(--color-neutral-300)" }}>
                        {i.title}
                        {(i.count ?? 1) > 1 && ` ×${i.count}`}
                      </button>{" "}
                      <span className="tnum">{itemHours(i)}</span>
                    </span>
                  ))}
                  {listed.length > shown.length && ` · ${listed.length - shown.length} more`}
                </span>
              </div>
            )
          })}
          {!groups.length && <span className="fr-kicker">Nothing planned or recorded yet this week.</span>}
        </div>
        <div className="fr-stack" style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(0,1.3fr)", gap: 40, alignItems: "start" }}>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <H size={18} style={{ paddingBottom: 8 }}>
              Finished
            </H>
            {week.finished.map((d) => (
              <div key={d.item_id} className="fr-row" style={{ display: "grid", gridTemplateColumns: "16px 3px minmax(0,1fr) auto", gap: 10, alignItems: "center", padding: "7px 0" }}>
                <Icon name="check" size={13} style={{ color: "var(--color-accent-300)" }} />
                <span style={{ alignSelf: "stretch", borderRadius: 2, background: color(d.area) }} />
                <span>{d.title}</span>
                <span className="tnum fr-kicker">{when(d.when, today)}</span>
              </div>
            ))}
            {!week.finished.length && <span className="fr-kicker">Nothing yet.</span>}
          </div>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <H size={18} style={{ paddingBottom: 8 }}>
              Carried over
            </H>
            {week.carried.map((c) => (
              <div key={c.item_id} className="fr-row" style={{ display: "grid", gridTemplateColumns: "3px minmax(0,1fr) auto", gap: 12, alignItems: "center", padding: "10px 0" }}>
                <span style={{ alignSelf: "stretch", borderRadius: 2, background: color(c.area) }} />
                <span style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
                  <span style={{ fontWeight: 500 }}>{c.title}</span>
                  <span className="fr-kicker">
                    {c.note}
                    {c.when ? `, due ${when(c.when, today)}` : ""}
                  </span>
                </span>
                <Seg options={canWait(c) ? (["Keep", "Next week", "Drop"] as const) : (["Keep", "Drop"] as const)} value={carry[c.item_id] ?? "Keep"} onPick={(v) => setCarry({ ...carry, [c.item_id]: v })} size="small" onBg />
              </div>
            ))}
            {!week.carried.length && <span className="fr-kicker">Nothing.</span>}
            <H size={18} style={{ padding: "26px 0 8px" }}>
              Coming up
            </H>
            {week.coming.map((n) => (
              <div key={`${n.item_id}${n.when}`} className="fr-row" style={{ display: "grid", gridTemplateColumns: "3px minmax(0,1fr) auto", gap: 12, alignItems: "center", padding: "8px 0" }}>
                <span style={{ alignSelf: "stretch", borderRadius: 2, background: color(n.area) }} />
                <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <Icon name={n.note === "fixed" ? "calendar-blank" : "flag"} size={12} style={{ color: "var(--color-neutral-400)" }} />
                  {n.title}
                </span>
                <span className="tnum" style={{ fontSize: 12, color: n.note === "due" ? "var(--fr-due)" : "var(--color-neutral-400)" }}>
                  {when(n.when, today)}
                </span>
              </div>
            ))}
            {!week.coming.length && <span className="fr-kicker">Nothing due or fixed next week yet.</span>}
          </div>
        </div>
        <div className="fr-row fr-stack" style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)", gap: 40, alignItems: "start", paddingTop: 8 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 22 }}>
            <H size={18}>How did the week feel?</H>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(5, minmax(0,1fr))", gap: 6 }}>
              {FEELS.map((f) => (
                <button
                  key={f}
                  onClick={() => (setFeel(f), note({ week: week.start, feel: f }))}
                  className="fr-plain"
                  style={{
                    padding: "10px 6px",
                    textAlign: "center",
                    borderRadius: "var(--radius-md)",
                    fontSize: 12,
                    background: feel === f ? "color-mix(in srgb, var(--color-accent) 18%, transparent)" : "var(--color-bg)",
                    boxShadow: feel === f ? "inset 0 0 0 1px var(--color-accent-500)" : "0 0 0 1px color-mix(in srgb, var(--color-text) 7%, transparent)",
                    color: feel === f ? "var(--color-accent-200)" : "var(--color-text)",
                  }}
                >
                  {f}
                </button>
              ))}
            </div>
            <H size={18} style={{ paddingTop: 12 }}>
              Pace for next week
            </H>
            {paces && (
              <Seg
                options={Object.keys(paces.paces).map((p) => ({
                  value: p,
                  label: (
                    <>
                      {p}
                      {p === suggested && <span style={{ fontSize: 11, color: "var(--color-accent-300)" }}>suggested</span>}
                    </>
                  ),
                }))}
                value={pace ?? suggested}
                onPick={setPace}
              />
            )}
            <span className="fr-kicker" style={{ textWrap: "pretty" }}>
              {feel === "Rough" || feel === "Heavy" ? "A lighter week to recover. Deadlines still hold." : "Applies for seven days when you finish. Deadlines hold whatever you pick."}
            </span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 22 }}>
            <H size={18}>Anything to remember?</H>
            <textarea
              className="input"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              onBlur={() => notes !== (week.note?.notes ?? "") && note({ week: week.start, notes })}
              placeholder="A note for next Sunday, like what worked or what to drop"
              style={{ minHeight: 112, resize: "vertical", font: "inherit" }}
            />
            <span className="fr-kicker">Notes show up at the top of next week’s review.</span>
          </div>
        </div>
        {finished ? (
          <div style={{ display: "flex", gap: 14, alignItems: "center", padding: "16px 18px", borderRadius: "var(--radius-lg)", background: "color-mix(in srgb, var(--color-accent) 10%, var(--color-bg))", boxShadow: "0 0 0 1px color-mix(in srgb, var(--color-accent) 30%, transparent)" }}>
            <Icon name="check-circle" size={22} style={{ color: "var(--color-accent-300)" }} />
            <span style={{ flex: 1 }}>The week is reviewed. Friday has planned next week around what you chose.</span>
            <button className="btn btn-primary" onClick={() => navigate("/")}>
              See the plan
            </button>
          </div>
        ) : (
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <button className="btn btn-primary" onClick={finish} disabled={busy} style={{ padding: "10px 16px", fontSize: 14 }}>
              <Icon name="check" />
              Finish review and plan the week
            </button>
            <span className="fr-kicker">
              {Object.values(carry).filter((c) => c !== "Keep").length} changes to carried work; pace {pace ?? suggested}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

function hours(h: number): string {
  return `${Number(h.toFixed(1))} h`
}

/** A to-do's share of the row: what was done of what was planned, or only the one there is. */
function itemHours(i: Schemas["TimeItem"]): string {
  if (i.actual_h && i.planned_h) return `${Number(i.actual_h.toFixed(1))} of ${hours(i.planned_h)}`
  return i.actual_h ? `${hours(i.actual_h)} done` : `${hours(i.planned_h)} planned`
}
