// What only you can decide (27 Oct: "remove notifications and put that under review… decisions but in the inbox with
// a notification symbol and a way to let the user know to actually go check it"): late work, and locks that make work
// late, first in the Inbox. Nothing waits on an answer: the plan keeps your locks meanwhile. The count shows on the
// Inbox in the sidebar, as a tray in the calendar's title row, in the window's title and on the Mac's Dock icon.

import { useEffect, useState } from "react"
import { useNavigate } from "react-router"
import type { Schemas } from "@/api/client"
import { Icon } from "@/components/fr/controls"
import { useStatus } from "@/hooks/queries"
import { useCommand } from "@/hooks/useCommand"
import { lateBy, when } from "@/lib/format"
import { useShell } from "@/shell/ShellContext"

type Decision = Schemas["Decision"]

export const useDecisions = (): Decision[] => useStatus().data?.decisions ?? []

const waiting = (n: number) => (n === 1 ? "1 decision waiting in your Inbox" : `${n} decisions waiting in your Inbox`)

/** The count on a warm dot: what waits for you. */
export function DecisionCount({ n, style }: { n: number; style?: React.CSSProperties }) {
  return (
    <span className="tnum" aria-hidden style={{ minWidth: 16, height: 16, padding: "0 4px", borderRadius: 8, background: "var(--fr-warn)", color: "var(--fr-ink)", fontSize: 10, fontWeight: 600, lineHeight: "16px", textAlign: "center", ...style }}>
      {n}
    </span>
  )
}

/** The calendar's title row: a tray with the count, to the Inbox. Nothing when nothing waits. */
export function DecisionsButton() {
  const n = useDecisions().length
  const navigate = useNavigate()
  if (!n) return null
  return (
    <button className="btn btn-icon btn-ghost" onClick={() => navigate("/inbox")} aria-label={waiting(n)} title={waiting(n)} style={{ flex: "none", position: "relative", color: "var(--fr-warn)" }}>
      <Icon name="tray" size={17} />
      <DecisionCount n={n} style={{ position: "absolute", top: 1, right: 0 }} />
    </button>
  )
}

/** The window's title says it too, "(2) Friday", so it shows in the tab and the Dock's window list. */
export function useDecisionsTitle() {
  const n = useDecisions().length
  useEffect(() => {
    const base = document.title.replace(/^\(\d+\) /, "")
    document.title = n ? `(${n}) ${base}` : base
  }, [n])
}

/** The Inbox's first section: each decision with its answers, gone the moment you answer. */
export function Decisions() {
  const decisions = useDecisions()
  const [answered, setAnswered] = useState<string[]>([])
  const shown = decisions.filter((d) => !answered.includes(d.key))
  useEffect(() => setAnswered((was) => was.filter((k) => decisions.some((d) => d.key === k))), [decisions])
  if (!shown.length) return null
  const answer = (key: string) => setAnswered((was) => [...was, key])
  return (
    <section aria-label="To decide" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <span className="fr-kicker" style={{ display: "flex", alignItems: "center", gap: 6, padding: "0 4px", color: "var(--fr-warn)" }}>
        <Icon name="hand-pointing" size={13} />
        To decide
      </span>
      {shown.map((d) => (d.kind === "lock" ? <LockCard key={d.key} decision={d} onAnswer={() => answer(d.key)} /> : <LateCard key={d.key} decision={d} onAnswer={() => answer(d.key)} />))}
    </section>
  )
}

function Card({ icon, title, detail, children }: { icon: string; title: string; detail: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="fr-well" style={{ display: "grid", gridTemplateColumns: "18px minmax(0,1fr)", gap: 10, padding: "12px 12px 12px 10px", boxShadow: "inset 2px 0 0 var(--fr-warn)" }}>
      <Icon name={icon} size={16} style={{ color: "var(--fr-warn)", marginTop: 1 }} />
      <span style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 0 }}>
        <span style={{ fontWeight: 500 }}>{title}</span>
        <span style={{ fontSize: 12, color: "var(--color-neutral-400)", textWrap: "pretty" }}>{detail}</span>
        <span style={{ display: "flex", gap: 6, flexWrap: "wrap", paddingTop: 2 }}>{children}</span>
      </span>
    </div>
  )
}

const BUTTON = { padding: "4px 10px", fontSize: 12 }

function LockCard({ decision, onAnswer }: { decision: Decision; onAnswer: () => void }) {
  const keep = useCommand("lock_keep", { label: (o) => o.result.message ?? "Kept" })
  const unlock = useCommand("resolve", { label: () => "Unlocked; it can move now" })
  const pin = decision.pin_id as number
  return (
    <Card icon="lock-simple" title={decision.title} detail={decision.detail}>
      <button className="btn btn-secondary" style={BUTTON} onClick={() => (onAnswer(), keep({ pin_ids: [pin] }))}>
        Keep it
      </button>
      <button className="btn btn-primary" style={BUTTON} onClick={() => (onAnswer(), unlock({ unlock_pin_ids: [pin] }))}>
        Let it move
      </button>
    </Card>
  )
}

function LateCard({ decision, onAnswer }: { decision: Decision; onAnswer: () => void }) {
  const { today, setDialog } = useShell()
  const navigate = useNavigate()
  const leave = useCommand("late_accept", { label: (o) => o.result.message ?? "Left late" })
  const items = decision.items ?? []
  const detail = (
    <span style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {items.slice(0, 4).map((i) => (
        <button key={i.item_id} className="fr-plain fr-hover-text" onClick={() => navigate(`/todo?item=${i.item_id}`)} style={{ textAlign: "left", fontSize: 12, color: "var(--color-neutral-300)" }}>
          {i.title}
          <span style={{ color: "var(--color-neutral-500)" }}>
            {" "}
            · {i.due ? `due ${when(i.due, today)}, ` : ""}about {lateBy(i.hours)} late
          </span>
        </button>
      ))}
      {items.length > 4 && <span>and {items.length - 4} more</span>}
      <span>{decision.detail}</span>
    </span>
  )
  return (
    <Card icon="clock-countdown" title={decision.title} detail={detail}>
      <button className="btn btn-primary" style={BUTTON} onClick={() => setDialog("triage")}>
        See options
      </button>
      <button className="btn btn-secondary" style={BUTTON} onClick={() => (onAnswer(), leave({ item_ids: items.map((i) => i.item_id) }))}>
        Leave it late
      </button>
    </Card>
  )
}
