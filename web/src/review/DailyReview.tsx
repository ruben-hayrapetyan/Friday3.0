// The daily Review (27 Oct: "only the gaps, by task"): what Friday can't know on its own. A task's time that ended
// with no timer running, no answer on the calendar and the task still open is one row: all of it, some, none, or
// the whole task finished, saved the moment you pick. Timed work, checked-off tasks and meals (their taps) aren't
// asked about. Your answers are what Friday learns lengths and your working hours from; one left unanswered counts
// the way Settings → Schedule says (done, or not done and planned again). Below, forgotten sleep taps.

import { useQuery } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { query, type Schemas } from "@/api/client"
import { H, Icon } from "@/components/fr/controls"
import { TimeInput } from "@/components/fr/TimeInput"
import { useCommand } from "@/hooks/useCommand"
import { SLEEP_HOURS } from "@/lib/ampm"
import { clock, dur, weekday } from "@/lib/format"
import { addDays } from "@/lib/time"
import { useShell } from "@/shell/ShellContext"

type Gap = Schemas["ReviewGap"]
type Status = "done" | "partial" | "not_done" | "finished"

const FULL: Record<string, string> = { Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday", Thu: "Thursday", Fri: "Friday", Sat: "Saturday", Sun: "Sunday" }
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
export const dayName = (date: string) => `${FULL[weekday(date)]} ${Number(date.slice(8, 10))} ${MONTHS[Number(date.slice(5, 7)) - 1]}`

const useReview = (date: string) => useQuery({ queryKey: ["review", date], queryFn: () => query("review", { date }) }).data
const open = (gaps: Gap[] | undefined) => (gaps ?? []).filter((g) => !g.answer).length

/** The day to review: yesterday while it has something to answer, then today; null until yesterday's is read. */
export function useReviewDay(): string | null {
  const { today } = useShell()
  const yesterday = addDays(today, -1)
  const before = useReview(yesterday)
  return before === undefined ? null : open(before.gaps) ? yesterday : today
}

/** How many rows yesterday and today have to answer: the dot on Review. */
export function useReviewWaiting(): number {
  const { today } = useShell()
  return open(useReview(addDays(today, -1))?.gaps) + open(useReview(today)?.gaps)
}

const SAID: Record<Status, string> = { done: "All of it", partial: "Some", not_done: "None", finished: "Finished it" }

export function DailyReview({ date }: { date: string }) {
  const review = useReview(date)
  const answer = useCommand("review_task", { label: (o) => o.result.message ?? "Saved" })
  // Your answers show at once (27 Oct, instant feedback); the server's catch up behind them.
  const [mine, setMine] = useState<Record<number, { status: Status; minutes?: number }>>({})
  const [changing, setChanging] = useState<number | null>(null)
  const gaps = review?.gaps ?? []
  useEffect(() => setMine((was) => Object.fromEntries(Object.entries(was).filter(([id]) => !gaps.some((g) => g.item_id === Number(id) && g.answer)))), [gaps])
  if (!review) return <div className="fr-panel" />
  const said = (g: Gap): Status | null => mine[g.item_id]?.status ?? (g.finished ? "finished" : (g.answer ?? null))
  const toAnswer = gaps.filter((g) => !said(g) || changing === g.item_id)
  const answered = gaps.filter((g) => said(g) && changing !== g.item_id)
  const pick = (g: Gap, status: Status, minutes?: number) => {
    setMine((was) => ({ ...was, [g.item_id]: { status, minutes } }))
    setChanging(null)
    answer({ date, item_id: g.item_id, status, minutes })
  }
  return (
    <div className="fr-panel" style={{ overflowY: "auto" }}>
      <div className="fr-gutter" style={{ maxWidth: 720, padding: "32px 40px 150px", display: "flex", flexDirection: "column", gap: 18 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <H size={32}>{dayName(date)}</H>
          <span style={{ color: "var(--color-neutral-400)", textWrap: "pretty" }}>{subline(toAnswer.length, answered.length)}</span>
        </div>
        {!!review.sleep?.length && <SleepAsks asks={review.sleep} />}
        {toAnswer.map((g, i) => (
          <GapRow key={g.item_id} gap={g} keys={i === 0} onPick={(s, m) => pick(g, s, m)} />
        ))}
        {!!answered.length && (
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span className="fr-kicker" style={{ padding: "6px 0" }}>
              Answered
            </span>
            {answered.map((g) => (
              <Answered key={g.item_id} gap={g} said={said(g) as Status} minutes={mine[g.item_id]?.minutes ?? g.done_min ?? 0} onChange={g.finished ? undefined : () => setChanging(g.item_id)} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function subline(toAnswer: number, answered: number): string {
  if (toAnswer) return `${toAnswer} ${toAnswer === 1 ? "thing" : "things"} Friday can't tell on its own: planned time you didn't time or mark. Your answers teach it how long things take.`
  if (answered) return "All answered."
  return "Nothing to answer: everything planned was timed, marked or checked off."
}

/** When a gap's blocks were: "8–8:45am, 10:15–11:30am". */
export function spans(g: Pick<Gap, "spans">): string {
  return g.spans.map(([s, e]) => `${clock(s).replace(/(am|pm)$/, (m) => (clock(e).endsWith(m) ? "" : m))}–${clock(e)}`).join(", ")
}

const BUTTON = { padding: "5px 12px", fontSize: 13 }
const KEYS: Record<string, Status> = { "1": "done", "2": "partial", "3": "not_done", "4": "finished" }

function GapRow({ gap, keys, onPick }: { gap: Gap; keys: boolean; onPick: (s: Status, minutes?: number) => void }) {
  const step = gap.planned_min >= 30 ? 15 : 5
  const [some, setSome] = useState<number | null>(null)
  const half = Math.max(step, Math.round(gap.planned_min / 2 / step) * step)
  // The first row answers to 1–4, as the cards did.
  useEffect(() => {
    if (!keys || some !== null) return
    const press = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLElement && e.target.closest("input, textarea, select")) return
      const chosen = KEYS[e.key]
      if (!chosen) return
      if (chosen === "partial") setSome(half)
      else onPick(chosen)
    }
    window.addEventListener("keydown", press)
    return () => window.removeEventListener("keydown", press)
  }, [keys, some, half, onPick])
  const choices: Status[] = gap.last ? ["finished", "done", "partial", "not_done"] : ["done", "partial", "not_done", "finished"]
  return (
    <div className="fr-well" style={{ display: "flex", flexDirection: "column", gap: 10, padding: "14px 16px" }}>
      <span style={{ display: "flex", flexDirection: "column", gap: 3 }}>
        <span style={{ fontWeight: 500, fontSize: 15 }}>{gap.title}</span>
        <span className="tnum" style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>
          {dur(gap.planned_min)} planned · {spans(gap)}
          {gap.last ? " · its last planned time" : ""}
        </span>
      </span>
      {some === null ? (
        <span style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {choices.map((s, i) => (
            <button key={s} className={`btn ${i === 0 ? "btn-primary" : "btn-secondary"} fr-press`} style={BUTTON} onClick={() => (s === "partial" ? setSome(half) : onPick(s))}>
              {SAID[s]}
              {s === "done" ? ` (${dur(gap.planned_min)})` : ""}
            </button>
          ))}
        </span>
      ) : (
        <span style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontSize: 13, color: "var(--color-neutral-300)" }}>How much did you do?</span>
          <button className="btn btn-icon btn-secondary" aria-label="Less" style={{ width: 28, height: 28 }} disabled={some <= step} onClick={() => setSome(Math.max(step, some - step))}>
            <Icon name="minus" />
          </button>
          <span className="tnum" style={{ minWidth: 64, textAlign: "center" }}>
            {dur(some)}
          </span>
          <button className="btn btn-icon btn-secondary" aria-label="More" style={{ width: 28, height: 28 }} disabled={some >= gap.planned_min - step} onClick={() => setSome(Math.min(gap.planned_min - step, some + step))}>
            <Icon name="plus" />
          </button>
          <span style={{ fontSize: 12, color: "var(--color-neutral-500)" }}>of {dur(gap.planned_min)}</span>
          <button className="btn btn-primary fr-press" style={BUTTON} onClick={() => onPick("partial", some)}>
            Save
          </button>
          <button className="btn btn-ghost" style={BUTTON} onClick={() => setSome(null)}>
            Back
          </button>
        </span>
      )}
    </div>
  )
}

function Answered({ gap, said, minutes, onChange }: { gap: Gap; said: Status; minutes: number; onChange?: () => void }) {
  const what = said === "partial" ? `${dur(minutes)} of ${dur(gap.planned_min)}` : said === "not_done" ? "None: Friday plans it again" : said === "finished" ? "Finished" : `All of it (${dur(gap.planned_min)})`
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 4px", fontSize: 13 }}>
      <Icon name={said === "not_done" ? "x" : said === "partial" ? "circle-half" : "check"} size={14} style={{ color: said === "not_done" ? "var(--color-neutral-500)" : "var(--color-accent-300)" }} />
      <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{gap.title}</span>
      <span style={{ color: "var(--color-neutral-400)" }}>{what}</span>
      {onChange && (
        <button className="fr-plain fr-link" style={{ fontSize: 12 }} onClick={onChange}>
          Change
        </button>
      )}
    </div>
  )
}

/** Tracked sleep's taps this day is missing: the time to add (your usual one to start from), or skip it. */
function SleepAsks({ asks }: { asks: Schemas["SleepAsk"][] }) {
  return (
    <div className="fr-well" style={{ display: "flex", flexDirection: "column", gap: 6, padding: "12px 14px" }}>
      <span style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, color: "var(--color-neutral-400)" }}>
        <Icon name="moon" size={14} style={{ color: "var(--color-accent-300)" }} />
        Forgot a tap? Add the time, or skip it.
      </span>
      {asks.map((a) => (
        <SleepAskRow key={a.kind} ask={a} />
      ))}
    </div>
  )
}

function SleepAskRow({ ask }: { ask: Schemas["SleepAsk"] }) {
  const add = useCommand("sleep_mark", { label: (o) => o.result.message ?? "Added" })
  const skip = useCommand("sleep_skip", { label: () => "Skipped" })
  const [time, setTime] = useState(ask.at.slice(11, 16))
  // A bedtime (or the end of work) in the small hours is the next morning's date.
  const evening = ask.kind === "bed" || ask.kind === "done"
  const day = evening && time < "12:00" ? addDays(ask.date, 1) : evening ? ask.date : ask.at.slice(0, 10)
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
      <span style={{ flex: 1, minWidth: 180 }}>{ask.question}</span>
      <TimeInput value={time} onChange={setTime} label={ask.question} expect={{ hours: SLEEP_HOURS[ask.kind as keyof typeof SLEEP_HOURS] }} style={{ width: 110, padding: "3px 6px", minHeight: 0, fontSize: 12 }} />
      <button className="btn btn-secondary fr-press" disabled={!time} onClick={() => add({ kind: ask.kind, at: `${day}T${time}` })} style={{ fontSize: 12, padding: "3px 10px" }}>
        Add
      </button>
      <button className="btn btn-ghost" onClick={() => skip({ date: ask.date, kind: ask.kind })} style={{ fontSize: 12, padding: "3px 8px" }}>
        Skip
      </button>
    </div>
  )
}
