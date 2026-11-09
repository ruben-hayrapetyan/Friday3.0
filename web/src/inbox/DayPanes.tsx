// The planned time Friday can't account for, and sleep taps you missed, each a message in the Inbox (27 Oct: "only
// the gaps, by task"; Review until 29 Oct, then a page of its own in the Inbox, now a message each: "make everything
// just a message the user needs to deal with in inbox"). A task's time that ended with no timer running, no answer
// and the task still open: all of it, some, none, or the whole task finished, saved the moment you pick (1–4). Your
// answers are what Friday learns lengths and your working hours from; one left unanswered counts the way Settings →
// Schedule says. Timed work, checked-off tasks and meals (their taps) aren't asked about.

import { useEffect, useState } from "react"
import type { Schemas } from "@/api/client"
import { Icon } from "@/components/fr/controls"
import { TimeInput } from "@/components/fr/TimeInput"
import { useCommand } from "@/hooks/useCommand"
import { SLEEP_HOURS } from "@/lib/ampm"
import { dur } from "@/lib/format"
import { addDays } from "@/lib/time"
import { useShell } from "@/shell/ShellContext"
import { dayWord, spans } from "./messages"
import { Actions, After, Pane } from "./Pane"

type Gap = Schemas["ReviewGap"]
type Status = "done" | "partial" | "not_done" | "finished"
type Done = (sent?: Promise<unknown>) => void

const SAID: Record<Status, string> = { done: "All of it", partial: "Some", not_done: "None", finished: "Finished it" }
const KEYS: Record<string, Status> = { "1": "done", "2": "partial", "3": "not_done", "4": "finished" }

export function GapPane({ date, gap, onDone }: { date: string; gap: Gap; onDone: Done }) {
  const { today } = useShell()
  const answer = useCommand("review_task", { label: (o) => o.result.message ?? "Saved" })
  const pick = (status: Status, minutes?: number) => onDone(answer({ date, item_id: gap.item_id, status, minutes }))
  return (
    <Pane icon="cards" kicker={`${dayWord(date, today)} · ${spans(gap)}`} title={gap.title}>
      <span style={{ color: "var(--color-neutral-300)", textWrap: "pretty" }}>
        {dur(gap.planned_min)} was planned{gap.last ? ", its last planned time" : ""}. No timer ran and it isn't checked off, so Friday can't tell: how much did you do?
      </span>
      <GapAnswer gap={gap} onPick={pick} />
      <After>Your answer is how Friday learns how long things take you. 1–4 answer it; left unanswered, it counts the way Settings → Schedule says.</After>
    </Pane>
  )
}

function GapAnswer({ gap, onPick }: { gap: Gap; onPick: (s: Status, minutes?: number) => void }) {
  const step = gap.planned_min >= 30 ? 15 : 5
  const [some, setSome] = useState<number | null>(null)
  const half = Math.max(step, Math.round(gap.planned_min / 2 / step) * step)
  useEffect(() => {
    if (some !== null) return
    const press = (e: KeyboardEvent) => {
      if ((e.target instanceof HTMLElement && e.target.closest("input, textarea, select")) || document.querySelector('[aria-modal="true"]')) return
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const chosen = KEYS[e.key]
      if (!chosen) return
      if (chosen === "partial") setSome(half)
      else onPick(chosen)
    }
    window.addEventListener("keydown", press)
    return () => window.removeEventListener("keydown", press)
  }, [some, half, onPick])
  const choices: Status[] = gap.last ? ["finished", "done", "partial", "not_done"] : ["done", "partial", "not_done", "finished"]
  if (some === null)
    return (
      <Actions>
        {choices.map((s, i) => (
          <button key={s} className={`btn ${i === 0 ? "btn-primary" : "btn-secondary"} fr-press`} onClick={() => (s === "partial" ? setSome(half) : onPick(s))}>
            {SAID[s]}
            {s === "done" ? ` (${dur(gap.planned_min)})` : ""}
            <kbd style={{ marginLeft: 4, font: "inherit", fontSize: 11, opacity: 0.6 }}>{Object.keys(KEYS).find((k) => KEYS[k] === s)}</kbd>
          </button>
        ))}
      </Actions>
    )
  return (
    <Actions>
      <span style={{ fontSize: 13, color: "var(--color-neutral-300)" }}>How much did you do?</span>
      <button className="btn btn-icon btn-secondary" aria-label="Less" style={{ width: 28, height: 28 }} disabled={some <= step} onClick={() => setSome(Math.max(step, some - step))}>
        <Icon name="minus" />
      </button>
      <span className="tnum" style={{ width: 64, flex: "none", whiteSpace: "nowrap", textAlign: "center" }}>
        {dur(some)}
      </span>
      <button className="btn btn-icon btn-secondary" aria-label="More" style={{ width: 28, height: 28 }} disabled={some >= gap.planned_min - step} onClick={() => setSome(Math.min(gap.planned_min - step, some + step))}>
        <Icon name="plus" />
      </button>
      <span style={{ fontSize: 12, color: "var(--color-neutral-500)" }}>of {dur(gap.planned_min)}</span>
      <button className="btn btn-primary fr-press" onClick={() => onPick("partial", some)}>
        Save
      </button>
      <button className="btn btn-ghost" onClick={() => setSome(null)}>
        Back
      </button>
    </Actions>
  )
}

/** A tracked-sleep tap the day is missing: the time to add (your usual one to start from), or skip it. */
export function SleepPane({ ask, onDone }: { ask: Schemas["SleepAsk"]; onDone: Done }) {
  const { today } = useShell()
  const add = useCommand("sleep_mark", { label: (o) => o.result.message ?? "Added" })
  const skip = useCommand("sleep_skip", { label: () => "Skipped" })
  const [time, setTime] = useState(ask.at.slice(11, 16))
  // A bedtime (or the end of work) in the small hours is the next morning's date.
  const evening = ask.kind === "bed" || ask.kind === "done"
  const day = evening && time < "12:00" ? addDays(ask.date, 1) : evening ? ask.date : ask.at.slice(0, 10)
  return (
    <Pane icon="moon" kicker={`${dayWord(ask.date, today)} · A sleep tap you missed`} title={ask.question}>
      <span style={{ color: "var(--color-neutral-300)", textWrap: "pretty" }}>Friday learns your real bedtime, wake time and routines from these. It starts from your usual time.</span>
      <Actions>
        <TimeInput value={time} onChange={setTime} label={ask.question} expect={{ hours: SLEEP_HOURS[ask.kind as keyof typeof SLEEP_HOURS] }} style={{ width: 120 }} />
        <button className="btn btn-primary fr-press" disabled={!time} onClick={() => onDone(add({ kind: ask.kind, at: `${day}T${time}` }))}>
          Add it
        </button>
        <button className="btn btn-secondary" onClick={() => onDone(skip({ date: ask.date, kind: ask.kind }))}>
          I don't remember
        </button>
      </Actions>
    </Pane>
  )
}
