// A few plain dials: five human controls in place of twenty rules. Each stop writes named weights and params, shown
// under the dial, and the week is replanned as you turn them. Rules no dial touches stay as they are.

import { useEffect, useState } from "react"
import { Seg } from "@/components/fr/controls"
import { applyDials, DIALS, type Dial, readDials, type RuleSpec } from "./model"
import { ApplyRules, compare, MiniWeek, Outcome, Page, useBaseline, usePreview, useRuleSpecs } from "./shared"

export function DialsPage() {
  const specs = useRuleSpecs()
  const [positions, setPositions] = useState<Record<string, number> | null>(null)
  const specsKey = JSON.stringify(specs)
  // Saved rules (yours, or just applied) are where the dials start again.
  useEffect(() => setPositions(specs ? readDials(specs) : null), [specsKey])
  const draft = specs && positions ? applyDials(specs, positions) : undefined
  const changed = !!draft && JSON.stringify(draft) !== JSON.stringify(specs)
  const preview = usePreview(changed ? { rules: draft } : null, 500)
  const { saved, fixed, fresh, baseline } = useBaseline()
  const comparison = changed && preview.changes && saved && fresh && baseline ? compare(saved, fresh, baseline, preview.changes) : undefined
  return (
    <Page
      wide
      title="Dials"
      idea="Five dials instead of twenty rules. Each stop sets a few rules underneath, listed under the dial, so nothing is hidden: the dial is a shortcut, not a new mechanism. Turn one and the next two weeks are replanned beside it. A dial shows no stop when your rules were set by hand to something in between."
    >
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,440px) minmax(0,1fr)", gap: 32, alignItems: "start" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
          {specs &&
            positions &&
            DIALS.map((d) => <DialRow key={d.id} dial={d} at={positions[d.id]} specs={specs} onPick={(i) => setPositions({ ...positions, [d.id]: i })} />)}
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            {draft && specs && <ApplyRules rules={draft} current={specs} />}
            <button className="btn btn-ghost" disabled={!changed} onClick={() => specs && setPositions(readDials(specs))}>
              Reset
            </button>
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 14, position: "sticky", top: 0 }}>
          {changed ? <Outcome comparison={comparison} busy={preview.busy} error={preview.error} limit={5} /> : <span className="fr-kicker">Your plan as it stands. Turn a dial to see what changes.</span>}
          {baseline && <MiniWeek plan={comparison?.plan ?? baseline} compareTo={comparison ? baseline : undefined} fixed={fixed} />}
          {comparison && <span className="fr-kicker">Yellow: moved by your dials. Dashed: where it was.</span>}
        </div>
      </div>
    </Page>
  )
}

function DialRow({ dial, at, specs, onPick }: { dial: Dial; at: number; specs: RuleSpec[]; onPick: (i: number) => void }) {
  const stop = dial.stops[at]
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <span style={{ fontWeight: 500 }}>{dial.title}</span>
      <div style={{ display: "grid", gridTemplateColumns: "90px auto 90px", gap: 10, alignItems: "center" }}>
        <span className="fr-kicker" style={{ textAlign: "right" }}>
          {dial.low}
        </span>
        <Seg options={dial.stops.map((s, i) => ({ value: i, label: s.label }))} value={at < 0 ? null : at} onPick={onPick} label={dial.title} />
        <span className="fr-kicker">{dial.high}</span>
      </div>
      <span style={{ fontSize: 12, color: "var(--color-neutral-500)" }}>{stop ? writes(stop.set, specs) : "Custom: your rules sit between the stops"}</span>
    </div>
  )
}

/** "late_night weight 1 → 3, wind-down 22:00 → 21:00": what a stop changes, in the rules' own names. */
function writes(set: Record<string, { weight?: number; params?: Record<string, unknown> }>, specs: RuleSpec[]): string {
  const parts: string[] = []
  for (const [name, change] of Object.entries(set)) {
    const r = specs.find((s) => s.name === name)
    if (!r) continue
    if (change.weight !== undefined) parts.push(`${name} weight ${r.weight}${r.weight === change.weight ? "" : ` → ${change.weight}`}`)
    for (const [k, v] of Object.entries(change.params ?? {})) {
      const was = String(r.params[k] ?? "—")
      parts.push(`${name}.${k} ${was}${was === String(v) ? "" : ` → ${v}`}`)
    }
  }
  return `Sets ${parts.join(", ")}`
}
