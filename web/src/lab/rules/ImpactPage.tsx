// Impact first: each rule judged by what it does to this plan. Free numbers come first (what the rule charges the
// saved plan, and which blocks it charges); "What does it do?" runs a solve without the rule and shows the
// difference, so a rule that holds things back shows up even when it charges nothing.

import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { query, type Schemas } from "@/api/client"
import { useHorizon } from "@/hooks/queries"
import { useShell } from "@/shell/ShellContext"
import { useRules } from "@/rules/RulesPage"
import { clockTime, when } from "@/lib/format"
import { applyChanges, fmtH, type PlanMap, type Shape, shapeOf } from "./model"
import { compare, MiniWeek, Outcome, Page, useBaseline, usePreview } from "./shared"

export function ImpactPage() {
  const rules = useRules().data ?? []
  const totals = useQuery({ queryKey: ["rule_totals"], queryFn: () => query("rule_totals", {}) }).data ?? {}
  const { saved, fixed, fresh, baseline } = useBaseline()
  const blocks = useHorizon().data?.blocks ?? []
  const [open, setOpen] = useState<string | null>(null)
  const on = rules.filter((r) => r.enabled)
  const max = Math.max(1, ...on.map((r) => totals[r.name] ?? 0))
  const row = (r: Schemas["RuleOut"]) => (
    <ImpactRow key={r.name} rule={r} points={totals[r.name] ?? 0} max={max} blocks={blocks} open={open === r.name} onOpen={() => setOpen(open === r.name ? null : r.name)} base={{ saved, fixed, fresh, baseline }} />
  )
  return (
    <Page
      title="Impact"
      idea="Every rule, judged by what it does to your plan. The bar is what the rule charges the plan right now (how much it is being bent). A rule can charge nothing and still matter: it is keeping things away from where it objects. Open a rule to see that: Friday plans the next two weeks without it and shows what it changes."
    >
      {baseline ? <ShapeLine shape={shapeOf(baseline)} /> : <div className="fr-well fr-kicker" style={{ padding: "12px 16px" }}>Planning the next two weeks…</div>}
      <div style={{ display: "flex", flexDirection: "column" }}>{on.filter((r) => !r.background).map(row)}</div>
      <details>
        <summary className="fr-kicker" style={{ cursor: "pointer", padding: "6px 0" }}>
          How Friday fills in the rest ({on.filter((r) => r.background).length})
        </summary>
        {on.filter((r) => r.background).map(row)}
      </details>
    </Page>
  )
}

function ShapeLine({ shape }: { shape: Shape }) {
  const parts = [
    `${fmtH(shape.total)} planned`,
    `${fmtH(shape.lateNight)} after ${clockTime("22:00")}`,
    `${fmtH(shape.weekends)} on weekends`,
    `heaviest day ${fmtH(shape.heaviestDay)}`,
    `longest sitting ${fmtH(shape.longestSitting)}`,
  ]
  return (
    <div className="fr-well" style={{ padding: "12px 16px", display: "flex", gap: 18, flexWrap: "wrap" }}>
      <span className="fr-kicker">Next two weeks</span>
      {parts.map((p) => (
        <span key={p} className="tnum" style={{ color: "var(--color-neutral-300)" }}>
          {p}
        </span>
      ))}
    </div>
  )
}

interface Base {
  saved?: PlanMap
  fixed: Schemas["ItemOut"][]
  fresh?: Schemas["ChangeOut"]
  baseline?: PlanMap
}

function ImpactRow(props: { rule: Schemas["RuleOut"]; points: number; max: number; blocks: Schemas["BlockOut"][]; open: boolean; onOpen: () => void; base: Base }) {
  const { rule, points, max, blocks, open, onOpen, base } = props
  const { today } = useShell()
  const charged = blocks.filter((b) => (b.cost?.[rule.name] ?? 0) > 0).sort((a, b) => (b.cost?.[rule.name] ?? 0) - (a.cost?.[rule.name] ?? 0))
  return (
    <div className="fr-row" style={{ display: "flex", flexDirection: "column", gap: 10, padding: "14px 0" }}>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 180px auto", gap: 16, alignItems: "center" }}>
        <span style={{ display: "flex", flexDirection: "column", gap: 3, minWidth: 0 }}>
          <span style={{ fontWeight: 500 }}>{rule.sentence}</span>
          <span style={{ fontSize: 12, color: "var(--color-neutral-500)" }}>
            {rule.strength} ·{" "}
            {charged.length
              ? `bends on ${charged.length} ${charged.length === 1 ? "block" : "blocks"}: ${charged
                  .slice(0, 3)
                  .map((b) => `${b.title} ${when(b.start, today)}`)
                  .join(", ")}${charged.length > 3 ? "…" : ""}`
              : points > 0
                ? "bent across the plan, not on one block"
                : "kept everywhere in this plan"}
          </span>
        </span>
        <span title={`${(points / 100).toFixed(1)} points`} style={{ height: 8, borderRadius: 4, background: "color-mix(in srgb, var(--color-text) 8%, transparent)", overflow: "hidden" }}>
          <span style={{ display: "block", height: "100%", width: `${(100 * points) / max}%`, background: "var(--fr-warn)" }} />
        </span>
        <button className="btn btn-ghost" onClick={onOpen} disabled={!base.baseline}>
          {open ? "Close" : "What does it do?"}
        </button>
      </div>
      {open && <Without name={rule.name} base={base} />}
    </div>
  )
}

function Without({ name, base }: { name: string; base: Base }) {
  const without = usePreview({ off: [name] }, 0)
  const { changes } = without
  const { saved, fresh, baseline } = base
  const withoutPlan = changes && saved ? applyChanges(saved, changes) : undefined
  // Read the other way round: from the plan without the rule to the plan with it, i.e. what the rule does.
  const because = changes && withoutPlan && saved && fresh ? compare(saved, changes, withoutPlan, fresh) : undefined
  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(0,320px) minmax(0,1fr)", gap: 20, padding: "6px 0 6px 0" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <span className="fr-kicker">Because of this rule</span>
        <Outcome comparison={because} busy={without.busy} error={without.error} />
        <span className="fr-kicker" style={{ marginTop: 8 }}>
          Lit: where this rule puts things. Dashed: where they would go without it.
        </span>
      </div>
      {baseline && <MiniWeek plan={baseline} compareTo={withoutPlan} fixed={base.fixed} />}
    </div>
  )
}
