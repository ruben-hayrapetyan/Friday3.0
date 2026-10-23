// Week with toggles: your week as it is beside the week with some rules switched off or turned up or down, so a
// rule is understood by watching blocks move. Every change is a preview; Apply saves the whole set at once.

import { useEffect, useState } from "react"
import type { Schemas } from "@/api/client"
import { Seg, Switch } from "@/components/fr/controls"
import { useRules } from "@/rules/RulesPage"
import type { RuleSpec } from "./model"
import { ApplyRules, compare, MiniWeek, Outcome, Page, useBaseline, usePreview, useRuleSpecs } from "./shared"

const FACTORS = [
  { value: 0.33, label: "Weaker" },
  { value: 1, label: "As is" },
  { value: 3, label: "Stronger" },
]

export function WeekPage() {
  const specs = useRuleSpecs()
  const rules = (useRules().data ?? []).filter((r) => r.editable)
  const [off, setOff] = useState<Set<string>>(new Set())
  const [factor, setFactor] = useState<Record<string, number>>({})
  const specsKey = JSON.stringify(specs)
  useEffect(() => {
    setOff(new Set())
    setFactor({})
  }, [specsKey])
  const draft = specs?.map((r) => toggled(r, off.has(r.name), factor[r.name] ?? 1))
  const changed = !!draft && JSON.stringify(draft) !== specsKey
  const preview = usePreview(changed ? { rules: draft } : null, 500)
  const { saved, fixed, fresh, baseline } = useBaseline()
  const comparison = changed && preview.changes && saved && fresh && baseline ? compare(saved, fresh, baseline, preview.changes) : undefined
  const flip = (name: string) => {
    const next = new Set(off)
    if (!next.delete(name)) next.add(name)
    setOff(next)
  }
  const row = (r: Schemas["RuleOut"]) => (
    <div key={r.name} className="fr-row" style={{ display: "grid", gridTemplateColumns: "36px minmax(0,1fr)", gap: "6px 10px", alignItems: "center", padding: "10px 0", opacity: off.has(r.name) ? 0.5 : 1 }}>
      <Switch on={!off.has(r.name) && r.enabled} onToggle={() => flip(r.name)} label={`Switch ${r.sentence}`} />
      <span style={{ fontSize: 13 }}>{r.sentence}</span>
      <span />
      <Seg options={FACTORS} value={factor[r.name] ?? 1} onPick={(f) => setFactor({ ...factor, [r.name]: f })} size="small" label={`Strength of ${r.sentence}`} />
    </div>
  )
  return (
    <Page
      wide
      title="Week with toggles"
      idea="Your next week as it stands beside the same week with your toggles. Switch a rule off or turn it up and watch what moves: yellow blocks moved, dashed outlines show where they were. Nothing is saved until Apply."
    >
      <div style={{ display: "grid", gridTemplateColumns: "300px minmax(0,1fr)", gap: 28, alignItems: "start" }}>
        <div style={{ display: "flex", flexDirection: "column" }}>
          {rules.filter((r) => !r.background).map(row)}
          <details>
            <summary className="fr-kicker" style={{ cursor: "pointer", padding: "8px 0" }}>
              How Friday fills in the rest
            </summary>
            {rules.filter((r) => r.background).map(row)}
          </details>
          <div style={{ display: "flex", gap: 10, marginTop: 14, flexWrap: "wrap" }}>
            {draft && specs && <ApplyRules rules={draft} current={specs} />}
            <button
              className="btn btn-ghost"
              disabled={!changed}
              onClick={() => {
                setOff(new Set())
                setFactor({})
              }}
            >
              Reset
            </button>
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 14, position: "sticky", top: 0 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(380px, 1fr))", gap: 14 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <span className="fr-kicker">Now</span>
              {baseline && <MiniWeek plan={baseline} fixed={fixed} />}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <span className="fr-kicker">With your toggles{preview.busy && changed ? " · planning…" : ""}</span>
              {baseline && <MiniWeek plan={comparison?.plan ?? baseline} compareTo={comparison ? baseline : undefined} fixed={fixed} />}
            </div>
          </div>
          {changed && <Outcome comparison={comparison} busy={preview.busy} error={preview.error} limit={6} />}
        </div>
      </div>
    </Page>
  )
}

function toggled(r: RuleSpec, off: boolean, factor: number): RuleSpec {
  if (off) return { ...r, enabled: false }
  return factor === 1 ? r : { ...r, weight: Math.round(r.weight * factor * 100) / 100 }
}
