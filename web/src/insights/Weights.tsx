// A new weighing of your rules, as Friday learned it (27 Oct: one sentence quoting nineteen rules said neither which
// mattered nor how much): what would count more and what less, each rule on its line, the biggest first. Shown with
// the question in the Inbox (C75).

import { useState } from "react"
import { Icon } from "@/components/fr/controls"
import { type Change, sides, times, type Weighed } from "./shapes"

const SHOWN = 4 // each side's biggest changes; the rest on "Show all"

/** What would count more and what less, each rule on its line with how much, the biggest first; big changes marked. */
export function Weights({ changes, said }: { changes: Change[]; said: (rule: string) => string }) {
  const [all, setAll] = useState(false)
  const { more, less } = sides(changes)
  const big = [...more, ...less].filter((w) => w.big)
  const hidden = Math.max(0, more.length - SHOWN) + Math.max(0, less.length - SHOWN)
  const side = (title: string, list: Weighed[], icon: string) =>
    list.length > 0 && (
      <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
        <span className="fr-eyebrow" style={{ display: "flex", alignItems: "center", gap: 6, paddingBottom: 4 }}>
          <Icon name={icon} size={11} />
          {title} · {list.length}
        </span>
        {(all ? list : list.slice(0, SHOWN)).map((w) => (
          <div key={w.rule} title={`${said(w.rule)}: ${w.word} (${times(w.factor)})`} style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", gap: 10, alignItems: "baseline", padding: "4px 0", fontSize: 12.5 }}>
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{said(w.rule)}</span>
            <span className="tnum" style={{ fontSize: 11.5, whiteSpace: "nowrap", color: w.big ? "var(--fr-warn)" : "var(--color-neutral-400)" }}>
              {w.big && <Icon name="warning" size={11} style={{ marginRight: 4 }} />}
              {w.word} <span style={{ color: "var(--color-neutral-500)" }}>{times(w.factor)}</span>
            </span>
          </div>
        ))}
      </div>
    )
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, paddingLeft: 40 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "10px 28px" }}>
        {side("Counts more", more, "arrow-up")}
        {side("Counts less", less, "arrow-down")}
      </div>
      <div style={{ display: "flex", gap: 12, alignItems: "baseline", flexWrap: "wrap" }}>
        {big.length > 0 && (
          <span className="fr-kicker" style={{ color: "var(--fr-warn)", textWrap: "pretty", flex: "1 1 260px" }}>
            {big.length === 1 ? "One big change" : `${big.length} big changes`}: {big.map((w) => `“${said(w.rule)}” would count ${w.word}`).join("; ")}. Approve only if that's how you want to plan.
          </span>
        )}
        {hidden > 0 && (
          <button className="fr-link" onClick={() => setAll(!all)} style={{ fontSize: 12, marginLeft: "auto" }}>
            {all ? "Show fewer" : `Show all ${more.length + less.length}`}
          </button>
        )}
      </div>
    </div>
  )
}
