// One of Friday's questions, opened in the Inbox (C75): what it noticed and why it asks, then yes, no where there is
// one, and Not now, which sets it aside until Friday has more to go on. The two days to compare answer themselves.

import { useCommand } from "@/hooks/useCommand"
import { Comparison } from "@/insights/Comparison"
import type { Ask } from "./asks"
import { Actions, After, Pane } from "./Pane"

type Done = (sent?: Promise<unknown>) => void

export function AskPane({ ask, onDone }: { ask: Ask; onDone: Done }) {
  const later = useCommand("ask_later", { label: (o) => o.result.message ?? "Not now" })
  const notNow = () => onDone(later({ key: ask.key, evidence: ask.evidence }))
  return (
    <Pane icon={ask.icon} kicker={ask.kicker} title={ask.title}>
      <span style={{ color: "var(--color-neutral-300)", textWrap: "pretty" }}>{ask.why}</span>
      {ask.key === "compare" ? <Comparison bare onAnswer={(sent) => onDone(sent)} /> : ask.body}
      <Actions>
        {ask.yes && (
          <button className="btn btn-primary fr-press" onClick={() => onDone(ask.yes?.run())}>
            {ask.yes.label}
          </button>
        )}
        {ask.no && (
          <button className="btn btn-secondary fr-press" onClick={() => onDone(ask.no?.run())}>
            {ask.no.label}
          </button>
        )}
        <button className="btn btn-ghost" onClick={notNow}>
          Not now
        </button>
      </Actions>
      <After>Not now: it leaves your Inbox, and Friday asks again once it has more to go on.</After>
    </Pane>
  )
}
