// The daily review (v22): one card per block of the day, answered with a key (1 done, 2 partly, 3 didn't happen,
// 4 finished the whole thing). Beside it, what Friday will do with each answer. The day is settled when the last
// card is answered (`review_submit`); nothing changes before that. A day comes back with what's on record answered,
// so a reviewed day isn't asked again; only blocks that started since are.

import { useQuery } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { useNavigate } from "react-router"
import { type Block, query } from "@/api/client"
import { H, Icon } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useItems } from "@/hooks/queries"
import { clock, dur, weekday, when } from "@/lib/format"
import { addDays } from "@/lib/time"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"
import { type Answer, known, length, type Status } from "./answers"

const OPTIONS: { status: Status; key: string; label: string; desc: string; icon: string; ic: string }[] = [
  { status: "done", key: "1", label: "Done", desc: "Did what was planned", icon: "check", ic: "var(--color-accent-300)" },
  { status: "partial", key: "2", label: "Partly", desc: "Some of it", icon: "circle-half", ic: "var(--color-accent-400)" },
  { status: "not_done", key: "3", label: "Didn’t happen", desc: "Friday plans it again", icon: "x", ic: "var(--color-neutral-400)" },
  { status: "finished", key: "4", label: "Finished it", desc: "The whole thing is done", icon: "check-circle", ic: "var(--color-accent-300)" },
]
const STATE: Record<Status, string> = { done: "Done", partial: "Partly", not_done: "Didn’t happen", finished: "Finished" }
const FULL: Record<string, string> = { Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday", Thu: "Thursday", Fri: "Friday", Sat: "Saturday", Sun: "Sunday" }
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

// Half the block, on the slider's steps (5 minutes for a short block, else 15).
const halfOf = (b: Block) => (length(b) < 30 ? Math.max(5, Math.round(length(b) / 10) * 5) : Math.round(length(b) / 30) * 15)
export const dayName = (date: string) => `${FULL[weekday(date)]} ${Number(date.slice(8, 10))} ${MONTHS[Number(date.slice(5, 7)) - 1]}`

/** The day to review: yesterday while one of its blocks is unanswered, then today. */
export function useReviewDay(): string {
  const { today } = useShell()
  const yesterday = addDays(today, -1)
  const before = useQuery({ queryKey: ["review", yesterday], queryFn: () => query("review", { date: yesterday }) }).data
  return before && !before.reviewed && before.blocks.some((b) => !(b.key in (before.settled ?? {}))) ? yesterday : today
}

export function DailyReview({ date, onWeek }: { date: string; onWeek: () => void }) {
  const review = useQuery({ queryKey: ["review", date], queryFn: () => query("review", { date }) }).data
  const [answers, setAnswers] = useState<Record<string, Answer>>(() => saved(date))
  const [partial, setPartial] = useState<number | null>(null)
  const [submitted, setSubmitted] = useState(false)
  const [fresh, setFresh] = useState(false) // answering a reviewed day again, from nothing
  const submit = useCommand("review_submit", { label: (o) => o.result.message ?? "Reviewed" })
  const done = useCommand("done", { label: () => "Done" })
  const navigate = useNavigate()
  const cards = review?.blocks ?? []
  const all = known(cards, review?.settled, answers, fresh)
  const at = cards.findIndex((b) => !all[b.key])
  const card = at >= 0 ? cards[at] : null
  useEffect(() => sessionStorage.setItem(`review-${date}`, JSON.stringify(answers)), [date, answers])
  const answer = async (status: Status, minutes?: number) => {
    if (!card) return
    const mine = { ...answers, [card.key]: { status, minutes: minutes ?? (status === "not_done" ? 0 : length(card)) } }
    const next = { ...all, ...mine }
    setAnswers(mine)
    setPartial(null)
    if (cards.every((b) => next[b.key]) && review) {
      const entries = cards.map((b) => {
        const a = next[b.key]
        const status = a.status === "finished" ? "done" : a.status
        return { block_key: b.key, status, share: a.status === "partial" ? a.minutes / length(b) : 1 }
      })
      if (await submit({ date, entries })) {
        for (const b of cards) if (next[b.key].status === "finished") await done({ id: b.item_id })
        setSubmitted(true)
        setFresh(false)
        sessionStorage.removeItem(`review-${date}`)
      }
    }
  }
  const back = () => {
    const last = [...cards].reverse().find((b) => answers[b.key]) // this visit's; what's on record stays
    if (!last) return
    const { [last.key]: _, ...rest } = answers
    setAnswers(rest)
    setPartial(null)
  }
  useKeysForCards(card !== null && partial === null, (k) => {
    const option = OPTIONS.find((o) => o.key === k)
    if (!option || !card) return
    if (option.status === "partial") setPartial(halfOf(card))
    else answer(option.status)
  }, back)
  if (!review) return <div className="fr-panel" />
  // Settled once every block has an answer, whether given now or on record from before.
  const finished = submitted || (card === null && (review.reviewed || cards.length > 0))
  const again = () => (setAnswers({}), setFresh(true), setSubmitted(false))
  return (
    <div className="fr-panel" style={{ overflowY: "auto" }}>
      <div className="fr-gutter fr-stack" style={{ display: "grid", gridTemplateColumns: "minmax(0,600px) minmax(0,1fr)", gap: 48, padding: "32px 40px 150px", alignItems: "start" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <H size={32}>{dayName(date)}</H>
            <span style={{ color: "var(--color-neutral-400)" }}>{subline(cards.length, cards.filter((b) => all[b.key]).length, review.reviewed)}</span>
          </div>
          {cards.length > 0 && <Bars cards={cards} answers={all} current={card?.key ?? null} />}
          {card && !finished && <Card card={card} pos={`${at + 1} of ${cards.length}`} partial={partial} onPick={(s) => (s === "partial" ? setPartial(halfOf(card)) : answer(s))} onPartial={setPartial} onLog={(m) => answer("partial", m)} />}
          {!cards.length && !finished && <span style={{ color: "var(--color-neutral-400)" }}>Nothing was planned that day.</span>}
          {finished && <Wrapped date={date} cards={cards} answers={all} onWeek={onWeek} onPlan={() => navigate("/")} onAgain={cards.length ? again : undefined} />}
          <div style={{ display: "flex", gap: 16, fontSize: 12 }}>
            {Object.keys(answers).length > 0 && !finished && (
              <button className="fr-plain fr-hover-text" onClick={back} style={{ color: "var(--color-neutral-400)", display: "flex", gap: 6, alignItems: "center" }}>
                <Icon name="arrow-u-up-left" />
                Previous card
              </button>
            )}
            {card && !finished && (
              <button className="fr-plain fr-hover-text" onClick={() => navigate("/")} style={{ color: "var(--color-neutral-400)" }}>
                Finish later
              </button>
            )}
          </div>
        </div>
        <Log cards={cards} answers={all} />
      </div>
    </div>
  )
}

function saved(date: string): Record<string, Answer> {
  try {
    return JSON.parse(sessionStorage.getItem(`review-${date}`) ?? "{}")
  } catch {
    return {}
  }
}

function subline(n: number, answered: number, reviewed: boolean): string {
  if (!n) return reviewed ? "Reviewed." : "No blocks to look back on."
  return `${n} ${n === 1 ? "block" : "blocks"} to look back on${answered ? `, ${answered} answered` : ""}. About a minute.`
}

function useKeysForCards(active: boolean, onKey: (k: string) => void, onBack: () => void) {
  useEffect(() => {
    if (!active) return
    const press = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLElement && e.target.closest("input, textarea, select")) return
      if (["1", "2", "3", "4"].includes(e.key)) onKey(e.key)
      if (e.key === "ArrowLeft" || e.key === "Backspace") onBack()
    }
    window.addEventListener("keydown", press)
    return () => window.removeEventListener("keydown", press)
  }, [active, onKey, onBack])
}

function Bars({ cards, answers, current }: { cards: Block[]; answers: Record<string, Answer>; current: string | null }) {
  const fill = (b: Block) => {
    const a = answers[b.key]
    if (b.key === current) return "var(--color-text)"
    if (!a) return "color-mix(in srgb, var(--color-text) 8%, transparent)"
    return a.status === "not_done" ? "var(--color-neutral-600)" : a.status === "partial" ? "var(--color-accent-600)" : "var(--color-accent)"
  }
  return (
    <div style={{ display: "grid", gridTemplateColumns: `repeat(${cards.length}, minmax(0,1fr))`, gap: 4 }}>
      {cards.map((b) => (
        <span key={b.key} title={b.title} style={{ height: 4, borderRadius: 2, background: fill(b) }} />
      ))}
    </div>
  )
}

interface CardProps {
  card: Block
  pos: string
  partial: number | null
  onPick: (s: Status) => void
  onPartial: (m: number | null) => void
  onLog: (m: number) => void
}

function Card({ card, pos, partial, onPick, onPartial, onLog }: CardProps) {
  const { today } = useShell()
  const { color } = useLook()
  const item = useItems().data?.find((i) => i.id === card.item_id)
  const planned = length(card)
  return (
    <div style={{ position: "relative", padding: "0 0 18px" }}>
      <div style={{ position: "absolute", left: 24, right: 24, bottom: 0, height: 40, borderRadius: "var(--radius-lg)", background: "color-mix(in srgb, var(--color-text) 4%, var(--color-bg))", boxShadow: "0 0 0 1px color-mix(in srgb, var(--color-text) 7%, transparent)" }} />
      <div style={{ position: "absolute", left: 12, right: 12, bottom: 9, height: 40, borderRadius: "var(--radius-lg)", background: "color-mix(in srgb, var(--color-text) 6%, var(--color-bg))", boxShadow: "0 0 0 1px color-mix(in srgb, var(--color-text) 7%, transparent)" }} />
      <div style={{ position: "relative", display: "grid", gridTemplateColumns: "4px minmax(0,1fr)", borderRadius: "var(--radius-lg)", background: "var(--color-bg)", boxShadow: "var(--fr-float-sh)", overflow: "hidden" }}>
        <span style={{ background: color(card.area) }} />
        <div style={{ padding: "22px 24px 22px 22px", display: "flex", flexDirection: "column", gap: 18 }}>
          <div className="tnum" style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", fontSize: 12, color: "var(--color-neutral-400)" }}>
            <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span className="fr-swatch" style={{ background: color(card.area) }} />
              {[card.area, item?.preset].filter(Boolean).join(", ") || "No tag"}
            </span>
            <span>{pos}</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <H size={44} style={{ lineHeight: 0.95 }}>
              {card.title}
            </H>
            <span className="tnum" style={{ color: "var(--color-neutral-300)" }}>
              {clock(card.start)}–{clock(card.end)}, planned {dur(planned)}
              {item?.due && <span style={{ color: "var(--color-neutral-500)" }}>. Due {when(item.due, today)}</span>}
            </span>
          </div>
          <H size={16}>How did it go?</H>
          {partial === null ? (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0,1fr))", gap: 8 }}>
              {OPTIONS.map((o) => (
                <button
                  key={o.key}
                  onClick={() => onPick(o.status)}
                  className="fr-plain"
                  style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", gap: "2px 10px", alignItems: "center", padding: "12px 14px", borderRadius: "var(--radius-md)", background: "var(--color-surface)", boxShadow: "0 0 0 1px color-mix(in srgb, var(--color-text) 9%, transparent)" }}
                >
                  <span style={{ display: "flex", gap: 8, alignItems: "center", fontWeight: 500 }}>
                    <Icon name={o.icon} size={16} style={{ color: o.ic }} />
                    {o.label}
                  </span>
                  <kbd className="fr-kbd" style={{ gridRow: "span 2" }}>
                    {o.key}
                  </kbd>
                  <span style={{ fontSize: 12, color: "var(--color-neutral-500)" }}>{o.desc}</span>
                </button>
              ))}
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12, padding: 14, borderRadius: "var(--radius-md)", background: "var(--color-surface)", boxShadow: "0 0 0 1px color-mix(in srgb, var(--color-text) 7%, transparent)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <span>How long did you work on it?</span>
                <H size={24} style={{ fontVariantNumeric: "tabular-nums" }}>
                  {dur(partial)}
                </H>
              </div>
              <input type="range" min={Math.min(15, Math.max(5, planned - 5))} max={planned} step={planned < 30 ? 5 : 15} value={partial} onChange={(e) => onPartial(Number(e.target.value))} aria-label="Time worked" style={{ accentColor: "var(--color-accent)" }} />
              <span style={{ fontSize: 12, color: "var(--color-neutral-500)" }}>The other {dur(Math.max(0, planned - partial))} goes back into the plan.</span>
              <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                <button className="btn btn-ghost" onClick={() => onPartial(null)}>
                  Back
                </button>
                <button className="btn btn-primary" onClick={() => onLog(partial)}>
                  <Icon name="check" />
                  Log it
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function Wrapped(props: { date: string; cards: Block[]; answers: Record<string, Answer>; onWeek: () => void; onPlan: () => void; onAgain?: () => void }) {
  const { date, cards, answers, onWeek, onPlan, onAgain } = props
  const worked = Object.values(answers).reduce((s, a) => s + a.minutes, 0)
  const did = Object.values(answers).filter((a) => a.status !== "not_done").length
  const line = cards.length && Object.keys(answers).length ? `You did ${did} of ${cards.length} blocks, ${dur(worked)} in all. Friday has planned what's left.` : "This day is settled."
  return (
    <div className="fr-well" style={{ display: "flex", flexDirection: "column", gap: 14, padding: 24, borderRadius: "var(--radius-lg)" }}>
      <Icon name="check-circle" size={28} style={{ color: "var(--color-accent-300)" }} />
      <H size={34}>{FULL[weekday(date)]} is wrapped</H>
      <span style={{ color: "var(--color-neutral-300)", textWrap: "pretty" }}>{line}</span>
      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn btn-primary" onClick={onWeek}>
          <Icon name="calendar-check" />
          Review the week
        </button>
        <button className="btn btn-secondary" onClick={onPlan}>
          Back to plan
        </button>
        {onAgain && (
          <button className="btn btn-ghost" onClick={onAgain}>
            Change answers
          </button>
        )}
      </div>
    </div>
  )
}

function Log({ cards, answers }: { cards: Block[]; answers: Record<string, Answer> }) {
  const { color } = useLook()
  const answered = cards.filter((b) => answers[b.key])
  const what = (b: Block, a: Answer) => {
    if (a.status === "finished") return `Marked done. ${dur(a.minutes)} logged.`
    if (a.status === "done") return `${dur(a.minutes)} logged. What's left stays planned.`
    if (a.status === "partial") return `${dur(a.minutes)} logged; the other ${dur(length(b) - a.minutes)} goes back into the plan.`
    return "Nothing logged. It goes back into the plan, in the next good place."
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 6 }}>
      <H size={18}>What Friday will do</H>
      <span className="fr-kicker">Nothing changes until the last card. Every change can be undone from the plan.</span>
      {answered.map((b) => {
        const a = answers[b.key]
        const tag = a.status === "not_done" ? ["color-mix(in srgb, var(--color-text) 8%, transparent)", "var(--color-neutral-300)"] : ["color-mix(in srgb, var(--color-accent) 18%, transparent)", "var(--color-accent-200)"]
        return (
          <div key={b.key} className="fr-row" style={{ display: "grid", gridTemplateColumns: "3px minmax(0,1fr)", gap: 12, padding: "10px 0" }}>
            <span style={{ borderRadius: 2, background: color(b.area) }} />
            <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <span style={{ display: "flex", gap: 8, alignItems: "center", fontWeight: 500 }}>
                {b.title}
                <span style={{ fontSize: 11, fontWeight: 400, padding: "1px 6px", borderRadius: 4, background: tag[0], color: tag[1] }}>{STATE[a.status]}</span>
              </span>
              <span style={{ fontSize: 12, color: "var(--color-neutral-400)", textWrap: "pretty" }}>{what(b, a)}</span>
            </span>
          </div>
        )
      })}
      {!answered.length && <div className="fr-row" style={{ padding: "14px 0", color: "var(--color-neutral-500)" }}>Answer the first card to see what happens next.</div>}
    </div>
  )
}
