// Rules (v22): how you like your days, in your own words. Type a rule; Friday shows how it read it (what, when,
// which days) for you to correct, and how strongly to hold it. Below, every rule with a switch, its strength, how
// often the plan keeps it, and delete. A rule the plan bends can ask what it's up against, and you say which should
// win (COMBINED.md 66); the answer shows on both rules, and clicking it changes it.

import { useQuery } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { Link } from "react-router"
import { query, type Schemas } from "@/api/client"
import { H, Icon, Seg, Switch } from "@/components/fr/controls"
import { useShell } from "@/shell/ShellContext"
import { useCommand } from "@/hooks/useCommand"
import { useStatus } from "@/hooks/queries"
import { dayLabel } from "@/lib/format"

type Strength = "Prefer" | "Strongly" | "Always"
const STRENGTHS: Strength[] = ["Prefer", "Strongly", "Always"]
const EXAMPLES = ["I prefer eating lunch before 1pm", "No work after 10pm", "Keep Saturday mornings free", "At most 6 hours a day", "Deep work in the morning", "Gym right after class", "Finish things a day early"]
const SOURCES: Record<string, [string, string]> = { you: ["user", "Yours"], learned: ["sparkle", "Learned from you"], default: ["sliders-horizontal", "Built in"] }
const DAY_OPTS: { value: string; label: string; days: string[] | null }[] = [
  { value: "every", label: "Every day", days: null },
  { value: "weekdays", label: "Weekdays", days: ["mon", "tue", "wed", "thu", "fri"] },
  { value: "weekends", label: "Weekends", days: ["sat", "sun"] },
]

export const useRules = () => useQuery({ queryKey: ["rules"], queryFn: () => query("rules") })

export function RulesPage() {
  const rules = useRules().data ?? []
  const said = new Map(rules.map((r) => [r.name, r.sentence]))
  const owned = (useStatus().data?.config_keys ?? []).includes("rules")
  const mine = rules.filter((r) => r.source === "you").length
  return (
    <>
      <div className="fr-page-head">
        <span className="fr-h fr-title">Rules</span>
        <span className="fr-head-note" style={{ color: "var(--color-neutral-500)", whiteSpace: "nowrap" }}>
          {rules.filter((r) => r.enabled).length} on, {mine} of them yours
        </span>
        <div style={{ flex: 1 }} />
        <Link to="/lab/rules" className="fr-link fr-head-note" style={{ fontSize: 13, whiteSpace: "nowrap" }}>
          Try new rule designs →
        </Link>
      </div>
      <div className="fr-panel" style={{ overflowY: "auto" }}>
        <div className="fr-gutter" style={{ maxWidth: 1000, padding: "28px 40px 140px", display: "flex", flexDirection: "column", gap: 34 }}>
          <section style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <H size={22}>Rules</H>
              <span style={{ color: "var(--color-neutral-400)", textWrap: "pretty" }}>
                Tell Friday how you like your days, in your own words. Friday turns each one into a rule for the planner. Preferences bend when they must, and Friday learns how much each one matters from your reviews. Rules marked Always never bend.
              </span>
            </div>
            {owned ? <span className="fr-kicker">Your rules are set in friday.toml; change them there.</span> : <NewRule />}
            <div style={{ display: "flex", flexDirection: "column" }}>
              {rules
                .filter((r) => !r.background)
                .map((r) => (
                  <RuleRow key={r.name} rule={r} locked={owned} said={said} />
                ))}
            </div>
            <details>
              <summary className="fr-kicker" style={{ cursor: "pointer", padding: "6px 0" }}>
                How Friday fills in the rest ({rules.filter((r) => r.background).length})
              </summary>
              <div style={{ display: "flex", flexDirection: "column" }}>
                {rules
                  .filter((r) => r.background)
                  .map((r) => (
                    <RuleRow key={r.name} rule={r} locked={owned} said={said} />
                  ))}
              </div>
            </details>
          </section>
        </div>
      </div>
    </>
  )
}

function NewRule() {
  const { askClaude } = useShell()
  const [text, setText] = useState("")
  const [overrides, setOverrides] = useState<Record<string, unknown>>({})
  const [strength, setStrength] = useState<Strength | null>(null)
  const settled = useSettled(JSON.stringify({ text, overrides }), 200)
  const preview = useQuery({
    queryKey: ["rule_read", settled],
    queryFn: () => {
      const { text, overrides } = JSON.parse(settled)
      return query("rule_read", { text, overrides: JSON.stringify(overrides) })
    },
    enabled: !!text.trim(),
  }).data
  const add = useCommand("rule_add", { label: (o) => o.result.message ?? "Added" })
  const reading = preview?.reading as Reading | null | undefined
  const chosen = strength ?? ((preview?.strength as Strength) || "Prefer")
  const submit = async () => {
    if (!reading) return
    if (await add({ text, overrides: overrides as Record<string, never>, strength: chosen })) {
      setText("")
      setOverrides({})
      setStrength(null)
    }
  }
  const set = (k: string, v: unknown) => setOverrides({ ...overrides, [k]: v })
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, padding: 16, borderRadius: "var(--radius-lg)", background: "var(--color-bg)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <Icon name="plus" size={18} style={{ color: "var(--color-accent-300)" }} />
        <input value={text} onChange={(e) => (setText(e.target.value), setOverrides({}), setStrength(null))} onKeyDown={(e) => e.key === "Enter" && submit()} placeholder="I prefer eating lunch before 1pm" aria-label="New rule" style={{ flex: 1, minWidth: 0, border: 0, outline: 0, background: "transparent", color: "var(--color-text)", font: "inherit", fontSize: 16 }} />
        <button className="btn btn-primary" onClick={submit} disabled={!reading}>
          Add rule
        </button>
      </div>
      {text.trim() && preview ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "12px 14px", marginLeft: 28, borderRadius: "var(--radius-md)", background: "var(--color-surface)" }}>
          <span style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, color: reading ? "var(--color-accent-300)" : "var(--fr-warn)" }}>
            <Icon name={reading ? "check-circle" : "question"} size={13} />
            {reading ? "Friday read this as" : preview.effect}
          </span>
          {!reading && (
            // What the grammar can't read goes to Claude (COMBINED.md 37), as rules to confirm.
            <button className="btn btn-secondary" onClick={() => askClaude(text, "rule")} style={{ alignSelf: "flex-start" }}>
              <Icon name="sparkle" />
              Ask Claude to read it
            </button>
          )}
          {reading && (
            <>
              <H size={16}>{preview.sentence}</H>
              <span className="fr-kicker">{preview.effect}{chosen === "Always" ? ", and never bends." : ", unless it has to."}</span>
              <Fields reading={reading} overrides={overrides} onSet={set} onReset={() => setOverrides({})} />
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span className="fr-kicker">Strength</span>
                <Seg options={STRENGTHS} value={chosen} onPick={setStrength} onBg />
              </div>
            </>
          )}
        </div>
      ) : (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, paddingLeft: 28, alignItems: "center" }}>
          <span className="fr-kicker" style={{ marginRight: 4 }}>
            Try
          </span>
          {EXAMPLES.map((x) => (
            <button key={x} className="fr-chip" onClick={() => setText(x)} style={{ color: "var(--color-neutral-300)" }}>
              {x}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

interface Reading {
  kind: string
  subject: string
  rel: string | null
  at: string | null
  until: string | null
  days: string[] | null
  amount: number | null
}

/** The parts of a reading you can correct: what, when and which days. */
function Fields(props: { reading: Reading; overrides: Record<string, unknown>; onSet: (k: string, v: unknown) => void; onReset: () => void }) {
  const { reading, overrides, onSet, onReset } = props
  const pin = (k: string) => k in overrides && <Icon name="push-pin" size={12} style={{ color: "var(--color-accent-300)" }} />
  const dayValue = DAY_OPTS.find((o) => JSON.stringify(o.days) === JSON.stringify(reading.days))?.value ?? null
  const rels = reading.kind === "window" ? ["before", "after", "between"] : []
  return (
    <div className="fr-row" style={{ display: "grid", gridTemplateColumns: "56px minmax(0,1fr)", gap: "8px 12px", alignItems: "center", paddingTop: 8 }}>
      <span className="fr-kicker">What</span>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <input className="input" value={reading.subject} onChange={(e) => onSet("subject", e.target.value.toLowerCase())} aria-label="What" style={{ width: 180, padding: "4px 8px", fontSize: 12, minHeight: 0 }} />
        {pin("subject")}
      </div>
      {rels.length > 0 && (
        <>
          <span className="fr-kicker">When</span>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <Seg options={rels} value={reading.rel} onPick={(v) => onSet("rel", v)} onBg />
            <input type="time" step={900} className="input" value={reading.at ?? ""} onChange={(e) => onSet("at", e.target.value)} style={{ width: 110, padding: "4px 8px", fontSize: 12, minHeight: 0 }} />
            {reading.rel === "between" && (
              <input type="time" step={900} className="input" value={reading.until ?? ""} onChange={(e) => onSet("until", e.target.value)} style={{ width: 110, padding: "4px 8px", fontSize: 12, minHeight: 0 }} />
            )}
            {pin("at")}
          </div>
        </>
      )}
      {reading.kind === "cap" && (
        <>
          <span className="fr-kicker">Hours</span>
          <input type="number" min={1} max={16} step={0.5} className="input" value={reading.amount ?? 6} onChange={(e) => onSet("amount", Number(e.target.value))} style={{ width: 90, padding: "4px 8px", fontSize: 12, minHeight: 0 }} />
        </>
      )}
      {reading.kind !== "cap" && reading.kind !== "early" && reading.kind !== "after" && (
        <>
          <span className="fr-kicker">Days</span>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <Seg options={DAY_OPTS} value={dayValue} onPick={(v) => onSet("days", DAY_OPTS.find((o) => o.value === v)?.days ?? null)} onBg />
            {pin("days")}
            {Object.keys(overrides).length > 0 && (
              <button className="fr-link" style={{ fontSize: 12 }} onClick={onReset}>
                Use Friday’s reading
              </button>
            )}
          </div>
        </>
      )}
    </div>
  )
}

function RuleRow({ rule, locked, said }: { rule: Schemas["RuleOut"]; locked: boolean; said: Map<string, string> }) {
  const set = useCommand("rule_set", { label: () => "Saved" })
  const remove = useCommand("rule_remove", { label: () => "Deleted" })
  const win = useCommand("rule_win", { label: (o) => o.result.message ?? "Saved" })
  const [asking, setAsking] = useState(false)
  const bends = rule.enabled && rule.strength !== "Always" && rule.effect === "Gives way in this plan"
  const [icon, source] = SOURCES[rule.source] ?? SOURCES.default
  const options = rule.source === "you" ? STRENGTHS : rule.strength === "Always" ? (["Always"] as Strength[]) : (["Prefer", "Strongly"] as Strength[])
  return (
    <div className="fr-row fr-rule-row" style={{ display: "grid", gridTemplateColumns: "36px minmax(180px,1fr) auto 28px", gap: "8px 14px", alignItems: "center", padding: "12px 0", opacity: rule.enabled ? 1 : 0.5 }}>
      <Switch on={rule.enabled} onToggle={() => !locked && set({ name: rule.name, enabled: !rule.enabled })} label={`${rule.enabled ? "Switch off" : "Switch on"} ${rule.sentence}`} />
      <span style={{ display: "flex", flexDirection: "column", gap: 3, minWidth: 0 }}>
        <span style={{ fontWeight: 500 }}>{rule.sentence}</span>
        <span style={{ display: "flex", gap: 10, flexWrap: "wrap", fontSize: 12, color: "var(--color-neutral-500)" }}>
          <span style={{ display: "inline-flex", gap: 5, alignItems: "center" }}>
            <Icon name={icon} size={12} />
            {source}
          </span>
          <span>{rule.effect}</span>
          {bends && !locked && (
            <button className="fr-plain fr-link" onClick={() => setAsking(!asking)} aria-expanded={asking} style={{ fontSize: 12 }}>
              What to?
            </button>
          )}
          {(rule.wins_over ?? []).map((other) => (
            <button key={other} className="fr-plain fr-hover-text" title="Click to let it win instead" onClick={() => !locked && win({ winner: other, loser: rule.name })} style={{ fontSize: 12 }}>
              Wins over “{said.get(other) ?? other}”
            </button>
          ))}
          {(rule.gives_way_to ?? []).map((other) => (
            <button key={other} className="fr-plain fr-hover-text" title="Click to let this one win instead" onClick={() => !locked && win({ winner: rule.name, loser: other })} style={{ fontSize: 12 }}>
              Gives way to “{said.get(other) ?? other}”
            </button>
          ))}
        </span>
      </span>
      <span style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
        {rule.editable && !locked ? <Seg options={options} value={rule.strength} onPick={(v) => set({ name: rule.name, strength: v as Strength })} size="small" /> : <span className="fr-tag accent">{rule.strength}</span>}
        <span className="tnum" style={{ fontSize: 11, color: "var(--color-neutral-500)", whiteSpace: "nowrap" }}>
          {rule.kept}
        </span>
      </span>
      {!locked && rule.editable ? (
        <button className="btn btn-icon btn-ghost" onClick={() => remove({ name: rule.name })} aria-label="Delete rule" style={{ width: 28, height: 28, color: "var(--color-neutral-500)" }}>
          <Icon name="trash" />
        </button>
      ) : (
        <span />
      )}
      {asking && <Clash rule={rule} onAnswer={(winner, loser) => (win({ winner, loser }), setAsking(false))} />}
    </div>
  )
}

/** "This clashes with … Which should win?" (the v22 design): planned once more with the rule weighed far higher. */
function Clash({ rule, onAnswer }: { rule: Schemas["RuleOut"]; onAnswer: (winner: string, loser: string) => void }) {
  const found = useQuery({ queryKey: ["rule_clash", rule.name], queryFn: () => query("rule_clash", { name: rule.name }), staleTime: 60_000 })
  const clash = found.data
  return (
    <div style={{ gridColumn: "2 / -1", display: "flex", flexDirection: "column", gap: 10, padding: "12px 14px", borderRadius: "var(--radius-md)", background: "color-mix(in srgb, var(--fr-warn) 9%, var(--color-bg))" }}>
      {found.isLoading ? (
        <span className="fr-kicker">Planning once more with this rule weighed far higher (a few seconds)…</span>
      ) : found.isError || !clash ? (
        <span className="fr-kicker">Couldn’t find out just now.</span>
      ) : !clash.other ? (
        <span className="fr-kicker">Weighed far higher, it bends no less, or no other rule gives way for it: your deadlines and the work itself are what bend it.</span>
      ) : (
        <>
          <span style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
            <Icon name="warning" size={14} style={{ color: "var(--fr-warn)" }} />
            <span style={{ textWrap: "pretty" }}>
              This clashes with <span style={{ fontWeight: 500 }}>{clash.other_sentence}</span>
              {clash.days?.length ? ` on ${clash.days.map(dayLabel).join(", ")}` : ""}. Which should win?
            </span>
          </span>
          <span style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <button className="btn btn-secondary" onClick={() => onAnswer(rule.name, clash.other as string)} style={{ fontSize: 12 }}>
              {clash.sentence}
            </button>
            <button className="btn btn-secondary" onClick={() => onAnswer(clash.other as string, rule.name)} style={{ fontSize: 12 }}>
              {clash.other_sentence}
            </button>
          </span>
          <span style={{ fontSize: 11, color: "var(--color-neutral-500)" }}>Friday remembers your answer for these two rules. Click the result to change it.</span>
        </>
      )}
    </div>
  )
}

function useSettled<T>(value: T, ms: number): T {
  const [settled, setSettled] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), ms)
    return () => clearTimeout(timer)
  }, [value, ms])
  return settled
}
