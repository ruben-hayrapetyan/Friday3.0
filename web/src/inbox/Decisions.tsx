// What only you can decide (27 Oct: "remove notifications and put that under review… decisions but in the inbox with
// a notification symbol and a way to let the user know to actually go check it"): late work, locks that make work
// late, and what Friday learned against a rule of yours, first among the Inbox's messages (29 Oct). Nothing waits on
// an answer: the plan keeps your locks meanwhile. What waits in the Inbox, all of it, is counted on the Inbox in the
// sidebar, as a tray in the calendar's title row and in the window's title; the Mac's Dock icon counts these.

import { useEffect } from "react"
import { useNavigate } from "react-router"
import type { Schemas } from "@/api/client"
import { Icon } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { lateBy, when } from "@/lib/format"
import { useShell } from "@/shell/ShellContext"
import { Actions, After, Pane } from "./Pane"
import { useInboxCount } from "./queries"

export { useDecisions } from "./queries"

type Decision = Schemas["Decision"]
type Done = (sent?: Promise<unknown>) => void

const waiting = (n: number) => (n === 1 ? "1 thing waiting in your Inbox" : `${n} things waiting in your Inbox`)

/** The count on a warm dot: what waits for you. */
export function DecisionCount({ n, style }: { n: number; style?: React.CSSProperties }) {
  return (
    <span className="tnum" aria-hidden style={{ minWidth: 16, height: 16, padding: "0 4px", borderRadius: 8, background: "var(--fr-warn)", color: "var(--fr-ink)", fontSize: 11, fontWeight: 600, lineHeight: "16px", textAlign: "center", ...style }}>
      {n}
    </span>
  )
}

/** The calendar's title row: a tray with the count, to the Inbox. Nothing when nothing waits. */
export function DecisionsButton() {
  const n = useInboxCount()
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
  const n = useInboxCount()
  useEffect(() => {
    const base = document.title.replace(/^\(\d+\) /, "")
    document.title = n ? `(${n}) ${base}` : base
  }, [n])
}

const KICKER: Record<string, string> = { late: "Will be late", lock: "A lock makes work late", learned: "What Friday learned, against a rule of yours" }
const ICON: Record<string, string> = { late: "clock-countdown", lock: "lock-simple", learned: "scales" }

/** A decision opened: what it is, and its answers; `onDone` the moment you answer. */
export function DecisionPane({ decision, onDone }: { decision: Decision; onDone: Done }) {
  return (
    <Pane icon={ICON[decision.kind] ?? "hand-pointing"} kicker={`To decide · ${KICKER[decision.kind] ?? "Only you can say"}`} title={decision.title} warn>
      {decision.kind === "lock" ? <Lock decision={decision} onDone={onDone} /> : decision.kind === "learned" ? <Learned decision={decision} onDone={onDone} /> : <Late decision={decision} onDone={onDone} />}
    </Pane>
  )
}

function Lock({ decision, onDone }: { decision: Decision; onDone: Done }) {
  const keep = useCommand("lock_keep", { label: (o) => o.result.message ?? "Kept" })
  const unlock = useCommand("resolve", { label: () => "Unlocked; it can move now" })
  const pin = decision.pin_id as number
  return (
    <>
      <span style={{ color: "var(--color-neutral-300)", textWrap: "pretty" }}>{decision.detail}</span>
      <Actions>
        <button className="btn btn-primary" onClick={() => onDone(unlock({ unlock_pin_ids: [pin] }))}>
          Let it move
        </button>
        <button className="btn btn-secondary" onClick={() => onDone(keep({ pin_ids: [pin] }))}>
          Keep it
        </button>
      </Actions>
    </>
  )
}

function Late({ decision, onDone }: { decision: Decision; onDone: Done }) {
  const { today, setDialog } = useShell()
  const navigate = useNavigate()
  const leave = useCommand("late_accept", { label: (o) => o.result.message ?? "Left late" })
  const items = decision.items ?? []
  return (
    <>
      <div style={{ display: "flex", flexDirection: "column" }}>
        {items.map((i) => (
          <button key={i.item_id} className="fr-plain fr-hover fr-row" onClick={() => navigate(`/todo?item=${i.item_id}`)} style={{ display: "flex", gap: 10, alignItems: "baseline", textAlign: "left", padding: "8px 2px" }}>
            <span style={{ flex: 1, minWidth: 0, fontWeight: 500 }}>{i.title}</span>
            <span className="tnum" style={{ fontSize: 12, color: "var(--color-neutral-400)", whiteSpace: "nowrap" }}>
              {i.due ? `due ${when(i.due, today)}, ` : ""}about {lateBy(i.hours)} late
            </span>
          </button>
        ))}
      </div>
      <span style={{ color: "var(--color-neutral-300)", textWrap: "pretty" }}>{decision.detail}</span>
      <Actions>
        <button className="btn btn-primary" onClick={() => setDialog("triage")}>
          See options
        </button>
        <button className="btn btn-secondary" onClick={() => onDone(leave({ item_ids: items.map((i) => i.item_id) }))}>
          Leave it late
        </button>
      </Actions>
    </>
  )
}

/** What Friday learned against a rule of yours (29 Oct: "make sure that there is guards against any of friday's
 * learned behaviours and the rules contradicting (and whether the rules need to be updated or the behaviours)"): which
 * side Friday would change, and each answer with what it does. */
function Learned({ decision, onDone }: { decision: Decision; onDone: Done }) {
  const resolve = useCommand("conflict_resolve", { label: (o) => o.result.message ?? "Done" })
  const options = decision.options ?? []
  return (
    <>
      <span style={{ color: "var(--color-neutral-300)", textWrap: "pretty" }}>{decision.detail}</span>
      <span style={{ fontSize: 13, color: "var(--color-neutral-400)" }}>{decision.update === "rule" ? "Friday would update the rule." : "Friday would keep your rule and change what it learned."}</span>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {options.map((o) => (
          <span key={o.id} style={{ fontSize: 13, color: "var(--color-neutral-400)", textWrap: "pretty" }}>
            <b style={{ fontWeight: 500, color: "var(--color-neutral-200)" }}>{o.label}:</b> {o.detail}
          </span>
        ))}
      </div>
      <Actions>
        {options.map((o) => (
          <button key={o.id} className={`btn ${o.recommended ? "btn-primary" : "btn-secondary"}`} onClick={() => onDone(resolve({ key: decision.key.replace(/^learned:/, ""), option: o.id }))}>
            {o.label}
          </button>
        ))}
      </Actions>
      <After>Nothing waits on your answer: the plan goes on meanwhile.</After>
    </>
  )
}
