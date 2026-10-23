// Try elsewhere and history (m16's design, COMBINED.md 66): the cheapest other place for a block with what it costs
// rule by rule, and a "Move there"; and what was done to the item, by whom.

import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { type Block, query } from "@/api/client"
import { Icon } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { when } from "@/lib/format"
import { fromMin, toMin } from "@/lib/time"
import { useShell } from "@/shell/ShellContext"

const ACTOR: Record<string, string> = { you: "You", cli: "You (command line)", job: "Friday", config: "friday.toml" }
const SAID: Record<string, string> = {
  add: "Added", edit: "Changed", done: "Marked done", drop: "Deleted", reopen: "Opened again", pin: "Pinned",
  unpin: "Unpinned", start: "Started the timer", stop: "Stopped the timer", progress: "Progress", skip: "Skipped", stuck: "Stuck",
  depend: "Tied to another to-do", undepend: "Untied", suggestion_accept: "Accepted from the Inbox",
} // prettier-ignore

export function Elsewhere({ block, onMoved }: { block: Block; onMoved: () => void }) {
  const { today } = useShell()
  const [open, setOpen] = useState<"where" | "history" | null>(null)
  const where = useQuery({ queryKey: ["why_not", block.key], queryFn: () => query("why_not", { key: block.key }), enabled: open === "where" })
  const history = useQuery({ queryKey: ["log_list", block.item_id], queryFn: () => query("log_list", { item_id: block.item_id, limit: 12 }), enabled: open === "history" })
  const pin = useCommand("pin", { label: () => `Moved ${block.title}` })
  // Each rule by its sentence on the Rules page ("Wind down before bed"), not its name.
  const rules = useQuery({ queryKey: ["rules"], queryFn: () => query("rules"), enabled: open === "where" }).data ?? []
  const said = new Map(rules.map((r) => [r.name, r.sentence]))
  const length = toMin(block.end) - toMin(block.start)
  const found = where.data
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", gap: 6 }}>
        <button className="btn btn-ghost" onClick={() => setOpen(open === "where" ? null : "where")} aria-expanded={open === "where"}>
          <Icon name="arrows-left-right" />
          Try elsewhere
        </button>
        <button className="btn btn-ghost" onClick={() => setOpen(open === "history" ? null : "history")} aria-expanded={open === "history"}>
          <Icon name="clock-counter-clockwise" />
          History
        </button>
      </div>
      {open === "where" &&
        (where.isLoading ? (
          <span className="fr-kicker">Looking for the cheapest other place…</span>
        ) : !found?.to_start ? (
          <span className="fr-kicker">{found?.wall ? `Nowhere else it can go (${found.wall}).` : "Nowhere else is better."}</span>
        ) : (
          <div className="fr-well" style={{ padding: 10, display: "flex", flexDirection: "column", gap: 6 }}>
            <span>
              {when(found.to_start, today)} {found.total > 0 ? `costs ${(found.total / 100).toFixed(1)} points more:` : "costs no more."}
            </span>
            {Object.entries(found.difference)
              .filter(([, d]) => d !== 0)
              .map(([rule, d]) => (
                <span key={rule} className="fr-kicker" style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <span>{said.get(rule) ?? rule.replaceAll("_", " ")}</span>
                  <span className="tnum" style={{ color: d > 0 ? "var(--fr-warn)" : "var(--color-accent-300)" }}>
                    {d > 0 ? "+" : ""}
                    {(d / 100).toFixed(1)}
                  </span>
                </span>
              ))}
            <button
              className="btn btn-secondary"
              onClick={() => {
                const start = found.to_start as string
                pin({ id: block.item_id, start, end: fromMin(toMin(start) + length), kind: "preferred", from_start: block.start, from_end: block.end })
                onMoved()
              }}
              style={{ alignSelf: "flex-start" }}
            >
              Move there
            </button>
          </div>
        ))}
      {open === "history" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {(history.data ?? []).map((e) => (
            <span key={e.id} className="tnum" style={{ fontSize: 12, display: "flex", gap: 8, textDecoration: e.undone_by ? "line-through" : undefined, color: "var(--color-neutral-300)" }}>
              <span style={{ color: "var(--color-neutral-500)", minWidth: 92 }}>{when(e.at, today)}</span>
              {SAID[e.command] ?? e.command} · {ACTOR[e.actor] ?? e.actor.replace(/^(sync|mcp|agent):/, "")}
            </span>
          ))}
          {history.data?.length === 0 && <span className="fr-kicker">Nothing yet.</span>}
        </div>
      )}
    </div>
  )
}
