// Rules (v22): how you like your days, in your own words. Type a rule; Friday shows how it read it (what, when,
// which days) for you to correct, and how strongly to hold it. What Friday can't read goes to Claude when you press ↩
// (when Claude is connected), right here: Claude's rules show under the box to tick, and ↩ again adds them. Below, every rule with a switch, its strength, how often the plan keeps it, and delete.
// A rule the plan bends can ask what it's up against, and you say which should win (COMBINED.md 66); the answer shows
// on both rules, and clicking it changes it. Rules that contradict each other say so, before you add one and after.

import { useAi } from "@/settings/AiConnect"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useRef, useState } from "react"
import { Link, useNavigate } from "react-router"
import { ApiError, command, query, type Schemas } from "@/api/client"
import { Box, H, Icon, Seg, Switch } from "@/components/fr/controls"
import { useToast } from "@/components/Toasts"
import { applyActions } from "@/dialogs/AskClaude"
import { useCommand } from "@/hooks/useCommand"
import { useStatus } from "@/hooks/queries"
import { useInbox } from "@/inbox/InboxPage"
import { dayLabel } from "@/lib/format"
import { WeekPaces } from "./WeekPaces"
import { TimeInput } from "@/components/fr/TimeInput"

type Strength = "Prefer" | "Strongly" | "Always"
const STRENGTHS: Strength[] = ["Prefer", "Strongly", "Always"]
const EXAMPLES = ["I prefer eating lunch before 1pm", "No work after 10pm", "Keep Saturday mornings free", "At most 6 hours a day", "Deep work in the morning", "Gym right after class", "Finish things a day early", "Go easier on Saturdays", "Gym is optional", "Climbing club only if I'm ahead", "No work after 10pm the night before climbing club", "30 minutes before and after gym", "Exam prep as close to the exam as possible", "Never skip lunch or dinner", "Let Friday decide breakfast", "Short tasks in short gaps, long tasks in long stretches"]
const SOURCES: Record<string, [string, string]> = { you: ["user", "Yours"], learned: ["sparkle", "Learned from you"], default: ["sliders-horizontal", "Built in"] }
const DAY_OPTS: { value: string; label: string; days: string[] | null }[] = [
  { value: "every", label: "Every day", days: null },
  { value: "weekdays", label: "Weekdays", days: ["mon", "tue", "wed", "thu", "fri"] },
  { value: "weekends", label: "Weekends", days: ["sat", "sun"] },
]

export const useRules = () => useQuery({ queryKey: ["rules"], queryFn: () => query("rules") })

export function RulesPage() {
  const rules = useRules().data ?? []
  const byName = new Map(rules.map((r) => [r.name, r]))
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
            <div data-tour="week-paces" style={{ display: "flex", flexDirection: "column", gap: 8, padding: "6px 0 4px" }}>
              <span style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
                <span style={{ fontWeight: 500 }}>Your week</span>
                <span className="fr-kicker">Days that go easier or harder, every week. Click a day to change it.</span>
              </span>
              <WeekPaces />
            </div>
            <div style={{ display: "flex", flexDirection: "column" }}>
              {rules
                .filter((r) => !r.background)
                .map((r) => (
                  <RuleRow key={r.name} rule={r} locked={owned} byName={byName} />
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
                    <RuleRow key={r.name} rule={r} locked={owned} byName={byName} />
                  ))}
              </div>
            </details>
          </section>
        </div>
      </div>
    </>
  )
}

/** Claude reading a rule Friday couldn't: asking, what it said, and which of its rules you've ticked. */
type ClaudeReading = { busy: boolean; error?: string; answer?: Schemas["AskClaudeOut"]; kept: number[] }

function NewRule() {
  const navigate = useNavigate()
  const client = useQueryClient()
  const toast = useToast()
  const [claude, setClaude] = useState<ClaudeReading | null>(null)
  const llm = useInbox().data?.llm as { ready?: boolean } | undefined
  const demo = !!useStatus().data?.demo // the demo's stand-in AI
  const ai = !!llm?.ready || demo // an AI that can be asked (whichever is chosen)
  const aiName = useAi().name
  const strengths = new Map((useRules().data ?? []).map((r) => [r.name, r.strength]))
  const [text, setText] = useState("")
  const [overrides, setOverrides] = useState<Record<string, unknown>>({})
  const [strength, setStrength] = useState<Strength | null>(null)
  const typed = JSON.stringify({ text, overrides })
  const settled = useSettled(typed, 200)
  const preview = useQuery({
    queryKey: ["rule_read", settled],
    queryFn: () => {
      const { text, overrides } = JSON.parse(settled)
      return query("rule_read", { text, overrides: JSON.stringify(overrides) })
    },
    enabled: !!text.trim(),
  }).data
  const add = useCommand("rule_add", { label: (o) => o.result.message ?? "Added" })
  const switchOff = useCommand("rule_set", { label: () => "Switched off" })
  const reading = preview?.reading as Reading | null | undefined
  const chosen = strength ?? ((preview?.strength as Strength) || "Prefer")
  const unread = !!text.trim() && !!preview && !reading
  const clear = () => (setText(""), setOverrides({}), setStrength(null), setClaude(null))
  /** What Friday couldn't read, to Claude, answered here (no dialog): its rules, ticked, for ↩ or Add to apply. */
  const askInline = async () => {
    setClaude({ busy: true, kept: [] })
    try {
      const out = await command("ask_claude", { text, purpose: "rule" })
      const kept = out.result.actions.map((a, i) => (a.error ? -1 : i)).filter((i) => i >= 0)
      setClaude({ busy: false, answer: out.result, kept })
    } catch (e) {
      setClaude({ busy: false, kept: [], error: e instanceof ApiError || e instanceof Error ? e.message : String(e) })
    }
  }
  const applyClaude = async () => {
    const answer = claude?.answer
    if (answer && (await applyActions(claude.kept.map((i) => answer.actions[i]), client, toast))) clear()
  }
  /** ↩ or the button: add what Friday read, or hand what it couldn't read to Claude. Read again if typing ran ahead. */
  const sending = useRef(false) // ↩ twice, or ↩ and a click, adds it once
  const submit = async (replacing?: string) => {
    if (!text.trim() || sending.current) return
    sending.current = true
    try {
      const now = settled === typed && preview ? preview : await query("rule_read", { text, overrides: JSON.stringify(overrides) }).catch(() => null)
      if (!now) return
      if (!now.reading) {
        if (!ai || claude?.busy) return
        if (!claude?.answer?.actions.length) return await askInline() // asked again only when Claude had nothing, or not yet
        if (claude.kept.length) await applyClaude()
        return
      }
      if (await add({ text, overrides: overrides as Record<string, never>, strength: strength ?? ((now.strength as Strength) || "Prefer") })) {
        if (replacing) await switchOff({ name: replacing, enabled: false })
        clear()
      }
    } finally {
      sending.current = false
    }
  }
  const set = (k: string, v: unknown) => setOverrides({ ...overrides, [k]: v })
  return (
    <div data-tour="rule-new" style={{ display: "flex", flexDirection: "column", gap: 12, padding: 16, borderRadius: "var(--radius-lg)", background: "var(--color-bg)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <Icon name="plus" size={18} style={{ color: "var(--color-accent-300)" }} />
        <input value={text} onChange={(e) => (setText(e.target.value), setOverrides({}), setStrength(null), setClaude(null))} onKeyDown={(e) => e.key === "Enter" && submit()} placeholder="I prefer eating lunch before 1pm" aria-label="New rule" style={{ flex: 1, minWidth: 0, border: 0, outline: 0, background: "transparent", color: "var(--color-text)", font: "inherit", fontSize: 16 }} />
        <button className="btn btn-primary" onClick={() => submit()} disabled={!text.trim() || (unread && !ai) || !!claude?.busy || (!!claude?.answer && !claude.kept.length && !!claude.answer.actions.length)}>
          {unread && ai && !claude?.answer && <Icon name="sparkle" />}
          {!unread || !ai ? "Add rule" : claude?.busy ? `Asking ${aiName}…` : claude?.answer?.actions.length ? `Add ${claude.kept.length > 1 ? `${claude.kept.length} rules` : "rule"}` : claude?.answer ? "Ask again" : `Ask ${aiName}`}
        </button>
      </div>
      {text.trim() && preview ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "12px 14px", marginLeft: 28, borderRadius: "var(--radius-md)", background: "var(--color-surface)" }}>
          {!reading && claude ? (
            <ClaudeRules claude={claude} onTick={(kept) => setClaude({ ...claude, kept })} />
          ) : !reading ? (
            // What the grammar can't read goes to Claude (COMBINED.md 37), as rules to confirm: ↩ sends it.
            <span style={{ display: "flex", gap: 8, alignItems: "baseline", fontSize: 12, color: ai ? "var(--color-neutral-300)" : "var(--fr-warn)", textWrap: "pretty" }}>
              <Icon name={ai ? "sparkle" : "question"} size={13} style={{ color: ai ? "var(--color-accent-300)" : undefined, flexShrink: 0, alignSelf: "center" }} />
              {ai ? (
                <span>Friday can’t read this one itself. Press ↩ and {aiName === "AI" ? "the AI" : aiName} will turn it into rules, shown here for you to check before anything changes.</span>
              ) : (
                <span>
                  Friday can’t read that as a rule yet, and no AI is set up to read it instead.{" "}
                  <button className="fr-link" onClick={() => navigate("/settings/integrations")} style={{ fontSize: 12 }}>
                    Set up an AI
                  </button>{" "}
                  or try one of the examples.
                </span>
              )}
            </span>
          ) : (
            <>
              <span style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, color: "var(--color-accent-300)" }}>
                <Icon name="check-circle" size={13} />
                Friday read this as
              </span>
              <H size={16}>{preview.sentence}</H>
              {reading.kind === "pace" ? (
                // A pace for weekdays is a setting: it shows under Your week, with no strength to choose.
                <span className="fr-kicker">{preview.effect}. It shows under Your week.</span>
              ) : ["deadlines", "optional", "ahead", "around", "meals_kept", "meals_learned"].includes(reading.kind) ? (
                <span className="fr-kicker" style={{ textWrap: "pretty" }}>{preview.effect}.</span>
              ) : ["night_before", "close", "fit_gaps", "runs_while_working", "sleep_min"].includes(reading.kind) ? (
                <>
                  <span className="fr-kicker" style={{ textWrap: "pretty" }}>{preview.effect}{chosen === "Always" ? ". It never bends." : ", unless work would be late."}</span>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span className="fr-kicker">Strength</span>
                    <Seg options={STRENGTHS} value={chosen} onPick={setStrength} onBg />
                  </div>
                </>
              ) : (
                <>
                  <span className="fr-kicker">{preview.effect}{chosen === "Always" ? ", and never bends." : ", unless it has to."}</span>
                  <Fields reading={reading} overrides={overrides} onSet={set} onReset={() => setOverrides({})} />
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span className="fr-kicker">Strength</span>
                    <Seg options={STRENGTHS} value={chosen} onPick={setStrength} onBg />
                  </div>
                </>
              )}
              {(preview.conflicts ?? []).map((c) => (
                <Conflict key={c.other} conflict={c} mine={chosen} theirs={strengths.get(c.other)} onReplace={() => submit(c.other)} />
              ))}
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

/** Claude's reading, in the rule box: asking, what went wrong, or what it said and the rules it proposes, ticked to add. */
function ClaudeRules({ claude, onTick }: { claude: ClaudeReading; onTick: (kept: number[]) => void }) {
  const name = useAi().name
  const head = (icon: string, words: string, ink = "var(--color-accent-300)") => (
    <span style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, color: ink }}>
      {claude.busy ? <span className="fr-spinner" /> : <Icon name={icon} size={13} />}
      {words}
    </span>
  )
  if (claude.busy) return head("sparkle", `${name} is reading it…`)
  if (claude.error) return head("warning", `${name} couldn’t read it: ${claude.error}`, "var(--fr-due)")
  const answer = claude.answer
  if (!answer) return null
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {head("sparkle", answer.actions.length ? `${name} read this as` : `${name} had no rule to suggest for this`)}
      {answer.reply && <span style={{ fontSize: 12, color: "var(--color-neutral-300)", textWrap: "pretty" }}>{answer.reply}</span>}
      {answer.actions.map((a, i) => {
        const on = claude.kept.includes(i)
        return (
          <button
            key={i}
            className="fr-plain fr-hover"
            disabled={!!a.error}
            onClick={() => onTick(on ? claude.kept.filter((k) => k !== i) : [...claude.kept, i])}
            style={{ display: "grid", gridTemplateColumns: "18px minmax(0,1fr)", gap: 10, alignItems: "start", padding: "6px 8px", borderRadius: "var(--radius-md)", opacity: a.error ? 0.6 : 1, textAlign: "left" }}
          >
            <Box on={on} />
            <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <H size={15}>{a.sentence}</H>
              {a.error && <span className="fr-kicker" style={{ color: "var(--fr-due)" }}>{a.error}</span>}
            </span>
          </button>
        )
      })}
      {answer.actions.length > 0 && <span className="fr-kicker">↩ adds what’s ticked; Undo takes it all back. Change the words to ask again.</span>}
    </div>
  )
}

/** Before adding: “Contradicts …” (or “Overlaps …”), what it means at these strengths, and adding it in that one's place. */
function Conflict({ conflict: c, mine, theirs, onReplace }: { conflict: Schemas["RuleConflict"]; mine: string; theirs?: string; onReplace: () => void }) {
  const outcome = c.overlap ? "" : mine === "Always" && theirs === "Always" ? " Both are Always, so Friday can’t keep both." : theirs === "Always" ? " That one is Always, so this one would give way there." : mine === "Always" ? " This one is Always, so that one would give way there." : " Friday would bend one of them; once both are in, you can say which wins."
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, padding: "10px 12px", borderRadius: "var(--radius-md)", background: c.overlap ? "var(--color-bg)" : "color-mix(in srgb, var(--fr-warn) 9%, var(--color-bg))" }}>
      <span style={{ display: "flex", gap: 8, alignItems: "baseline", fontSize: 12, textWrap: "pretty" }}>
        <Icon name={c.overlap ? "info" : "warning"} size={13} style={{ color: c.overlap ? "var(--color-neutral-400)" : "var(--fr-warn)", flexShrink: 0, alignSelf: "center" }} />
        <span>
          {c.overlap ? "Overlaps" : "Contradicts"} <span style={{ fontWeight: 500 }}>“{c.other_sentence}”</span>: {c.why}.{outcome}
        </span>
      </span>
      <button className="fr-link" onClick={onReplace} style={{ alignSelf: "flex-start", fontSize: 12, marginLeft: 21 }}>
        Add this, and switch that one off
      </button>
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
  const rels = reading.kind === "window" ? ["before", "after", "between", { value: "not_between", label: "not between" }] : []
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
            <TimeInput step={900} value={reading.at ?? ""} onChange={(t) => onSet("at", t)} label="At" style={{ width: 110, padding: "4px 8px", fontSize: 12, minHeight: 0 }} />
            {(reading.rel === "between" || reading.rel === "not_between") && (
              <TimeInput step={900} value={reading.until ?? ""} onChange={(t) => onSet("until", t)} label="Until" expect={{ after: reading.at ?? undefined }} style={{ width: 110, padding: "4px 8px", fontSize: 12, minHeight: 0 }} />
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

function RuleRow({ rule, locked, byName }: { rule: Schemas["RuleOut"]; locked: boolean; byName: Map<string, Schemas["RuleOut"]> }) {
  const said = (name: string) => byName.get(name)?.sentence ?? name
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
              Wins over “{said(other)}”
            </button>
          ))}
          {(rule.gives_way_to ?? []).map((other) => (
            <button key={other} className="fr-plain fr-hover-text" title="Click to let this one win instead" onClick={() => !locked && win({ winner: rule.name, loser: other })} style={{ fontSize: 12 }}>
              Gives way to “{said(other)}”
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
      {rule.enabled &&
        (rule.contradicts ?? []).map((c) => (
          <Contradiction key={c.other} rule={rule} other={byName.get(c.other)} conflict={c} locked={locked} onWin={(winner, loser) => win({ winner, loser })} onOff={() => set({ name: rule.name, enabled: false })} />
        ))}
    </div>
  )
}

/** Two rules that can't both be kept, found from the rules themselves. Both bend: which should win? One is Always:
 * it wins, and this one says it gives way. Both Always: Friday can't keep both, so one should go. */
function Contradiction(props: { rule: Schemas["RuleOut"]; other?: Schemas["RuleOut"]; conflict: Schemas["RuleConflict"]; locked: boolean; onWin: (winner: string, loser: string) => void; onOff: () => void }) {
  const { rule, other, conflict: c, locked, onWin, onOff } = props
  const mine = rule.strength === "Always"
  const theirs = other?.strength === "Always"
  if (mine && !theirs) return null // it wins; the other rule says it gives way
  const both = mine && theirs
  const bends = !mine && !theirs
  return (
    <div style={{ gridColumn: "2 / -1", display: "flex", flexDirection: "column", gap: 8, padding: "10px 12px", borderRadius: "var(--radius-md)", background: theirs && !both ? "var(--color-bg)" : "color-mix(in srgb, var(--fr-warn) 9%, var(--color-bg))" }}>
      <span style={{ display: "flex", gap: 8, alignItems: "baseline", fontSize: 12, textWrap: "pretty" }}>
        <Icon name={theirs && !both ? "info" : "warning"} size={13} style={{ color: theirs && !both ? "var(--color-neutral-400)" : "var(--fr-warn)", flexShrink: 0, alignSelf: "center" }} />
        <span>
          {theirs && !both ? "Gives way to" : "Contradicts"} <span style={{ fontWeight: 500 }}>“{c.other_sentence}”</span>
          {theirs && !both ? ", which is Always" : ""}: {c.why}.{both ? " Both are Always, so Friday can’t keep both." : bends ? " Which should win?" : ""}
        </span>
      </span>
      {!locked && bends && (
        <span style={{ display: "flex", gap: 6, flexWrap: "wrap", marginLeft: 21 }}>
          <button className="btn btn-secondary" onClick={() => onWin(rule.name, c.other)} style={{ fontSize: 12 }}>
            {rule.sentence}
          </button>
          <button className="btn btn-secondary" onClick={() => onWin(c.other, rule.name)} style={{ fontSize: 12 }}>
            {c.other_sentence}
          </button>
        </span>
      )}
      {!locked && both && (
        <button className="fr-link" onClick={onOff} style={{ alignSelf: "flex-start", fontSize: 12, marginLeft: 21 }}>
          Switch this one off
        </button>
      )}
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
