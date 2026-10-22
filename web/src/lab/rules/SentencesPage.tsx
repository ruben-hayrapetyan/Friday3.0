// Editable sentences: every rule, built-ins included, as one sentence whose values you can change in place. Walls
// (never crossed) are set apart from preferences (bent when they must be), and each preference says how strongly
// it holds. Edits collect in a draft that is previewed against your plan and saved only with Apply.

import { useEffect, useState } from "react"
import { Link } from "react-router"
import { Icon, Seg } from "@/components/fr/controls"
import { useSettings } from "@/hooks/queries"
import { useRules } from "@/rules/RulesPage"
import { DEFAULT_STAGE, type RuleSpec, stageOf } from "./model"
import { ApplyRules, compare, Outcome, Page, useBaseline, usePreview, useRuleSpecs } from "./shared"
import { Sentence } from "./sentence"

const STRENGTHS = [
  { value: 0, label: "Off" },
  { value: 0.33, label: "Gently" },
  { value: 1, label: "As now" },
  { value: 3, label: "Firmly" },
]
// The planner's own workings: listed last, folded.
const MACHINERY = new Set(["quota", "energy", "soft_late", "unscheduled", "spread", "cluster", "target_shortfall", "elastic_shortfall", "open_value", "minimize_changes"])

export function SentencesPage() {
  const specs = useRuleSpecs()
  const sentences = new Map((useRules().data ?? []).map((r) => [r.name, r.sentence]))
  const [draft, setDraft] = useState<RuleSpec[] | null>(null)
  const [factor, setFactor] = useState<Record<string, number>>({})
  const specsKey = JSON.stringify(specs)
  // Saved rules (yours, or just applied) are the new starting point.
  useEffect(() => {
    setDraft(specs ?? null)
    setFactor({})
  }, [specsKey])
  const rules = draft?.map((r) => withFactor(r, factor[r.name])) ?? []
  const changed = !!specs && JSON.stringify(rules) !== JSON.stringify(specs)
  const preview = usePreview(changed ? { rules } : null, 800)
  const { saved, fresh, baseline } = useBaseline()
  const comparison = changed && preview.changes && saved && fresh && baseline ? compare(saved, fresh, baseline, preview.changes) : undefined
  const edit = (name: string, next: RuleSpec) => setDraft((draft ?? []).map((r) => (r.name === name ? next : r)))
  const walls = rules.filter(isWall)
  const prefs = rules.filter((r) => !isWall(r) && !MACHINERY.has(r.type))
  const row = (r: RuleSpec) => (
    <RuleLine key={r.name} rule={(draft ?? []).find((d) => d.name === r.name) ?? r} said={sentences.get(r.name)} factor={factor[r.name] ?? (r.enabled === false ? 0 : 1)} onFactor={(f) => setFactor({ ...factor, [r.name]: f })} onEdit={(n) => edit(r.name, n)} />
  )
  return (
    <Page
      wide
      title="Sentences"
      idea="Every rule, the built-in ones too, is a sentence you can edit in place: the underlined values are the rule's real parameters. Walls are never crossed; preferences bend when they must, as strongly as you say. Your edits are previewed against your plan on the right and saved only when you press Apply."
    >
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 320px", gap: 32, alignItems: "start" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 26 }}>
          <Group title="Walls" note="Never crossed. Friday would rather leave work unplanned, and tells you.">
            <Walls />
            {walls.map(row)}
          </Group>
          <Group title="Preferences" note="Bent only when something above them needs the room. Strength is how much bending one costs.">
            {prefs.map(row)}
          </Group>
          <details>
            <summary className="fr-kicker" style={{ cursor: "pointer" }}>
              How Friday fills in the rest ({rules.filter((r) => !isWall(r) && MACHINERY.has(r.type)).length})
            </summary>
            {rules.filter((r) => !isWall(r) && MACHINERY.has(r.type)).map(row)}
          </details>
        </div>
        <div style={{ position: "sticky", top: 0, display: "flex", flexDirection: "column", gap: 14 }}>
          <span className="fr-kicker">What your edits do</span>
          {changed ? <Outcome comparison={comparison} busy={preview.busy} error={preview.error} /> : <span style={{ color: "var(--color-neutral-500)" }}>No edits yet.</span>}
          {specs && <ApplyRules rules={rules} current={specs} />}
          <button
            className="btn btn-ghost"
            disabled={!changed}
            onClick={() => {
              setDraft(specs ?? null)
              setFactor({})
            }}
          >
            Undo my edits
          </button>
        </div>
      </div>
    </Page>
  )
}

const isWall = (r: RuleSpec) => r.params.price === "forbid" || DEFAULT_STAGE[r.type] === "deadlines"

function withFactor(r: RuleSpec, f: number | undefined): RuleSpec {
  if (f === undefined) return r
  return f === 0 ? { ...r, enabled: false } : { ...r, enabled: true, weight: Math.round(r.weight * f * 100) / 100 }
}

function Group({ title, note, children }: { title: string; note: string; children: React.ReactNode }) {
  return (
    <section style={{ display: "flex", flexDirection: "column" }}>
      <span className="fr-h" style={{ fontSize: 20 }}>
        {title}
      </span>
      <span style={{ color: "var(--color-neutral-500)", marginBottom: 6 }}>{note}</span>
      {children}
    </section>
  )
}

/** Sleep and the daily cap are settings, not rules, but they are walls too: shown here, changed in Settings. */
function Walls() {
  const settings = useSettings().data
  if (!settings) return null
  const sleep = Object.values(settings.sleep ?? {}) as { bedtime: string; wake: string; margin_min: number }[]
  const caps = Object.values(settings.daily_cap ?? {}) as number[]
  const same = sleep.every((s) => s.bedtime === sleep[0]?.bedtime && s.wake === sleep[0]?.wake)
  return (
    <>
      <WallLine to="/settings">
        {sleep[0] && same
          ? `Never plan between ${sleep[0].bedtime} plus ${sleep[0].margin_min} minutes and ${sleep[0].wake}`
          : "Never plan in your sleep (it differs by day)"}
      </WallLine>
      <WallLine to="/settings">{`Never more than ${Math.max(...caps)} hours of work in a day`}</WallLine>
    </>
  )
}

function WallLine({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <div className="fr-row" style={{ display: "flex", gap: 10, alignItems: "center", padding: "12px 0" }}>
      <Icon name="wall" size={16} style={{ color: "var(--color-neutral-500)" }} />
      <span style={{ flex: 1 }}>{children}</span>
      <Link to={to} className="fr-link" style={{ fontSize: 12 }}>
        Change in Settings
      </Link>
    </div>
  )
}

function RuleLine(props: { rule: RuleSpec; said?: string; factor: number; onFactor: (f: number) => void; onEdit: (r: RuleSpec) => void }) {
  const { rule, said, factor, onFactor, onEdit } = props
  const wall = isWall(rule)
  const stage = stageOf(rule)
  return (
    <div className="fr-row" style={{ display: "grid", gridTemplateColumns: "20px minmax(0,1fr) auto", gap: 10, alignItems: "center", padding: "12px 0", opacity: factor === 0 ? 0.5 : 1 }}>
      <Icon name={wall ? "wall" : stage === "wellbeing" ? "heart" : "sliders-horizontal"} size={16} style={{ color: "var(--color-neutral-500)" }} />
      <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <span style={{ lineHeight: 2 }}>
          <Sentence rule={rule} said={said} onEdit={onEdit} />
        </span>
        <span style={{ fontSize: 11, color: "var(--color-neutral-600)" }}>
          {rule.name} · {wall ? "wall" : stage === "wellbeing" ? "protects you: outranks every preference" : "preference"} · weight {rule.weight}
        </span>
      </span>
      {wall ? <span className="fr-tag accent">Always</span> : <Seg options={STRENGTHS} value={factor} onPick={onFactor} size="small" label={`How strongly: ${rule.name}`} />}
    </div>
  )
}
