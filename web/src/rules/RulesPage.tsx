// Rules (v22): how you like your days, in your own words. Type a rule; Friday shows how it read it (what, when,
// which days) for you to correct, and how strongly to hold it. What Friday can't read goes to Claude when you press ↩
// (when Claude is connected), right here: Claude's rules show under the box to tick, and ↩ again adds them. Below, every rule with a switch, its strength, how often the plan keeps it, and delete.
// A rule the plan bends can ask what it's up against, and you say which should win (COMBINED.md 66); the answer shows
// on both rules, and clicking it changes it. Rules that contradict each other say so, before you add one and after.

import { useAi } from "@/settings/AiConnect"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useRef, useState } from "react"
import { Link, useNavigate, useSearchParams } from "react-router"
import { command, type CommandInput, errorWords, type Output, query, type Schemas } from "@/api/client"
import { Box, H, Icon, Seg, Switch } from "@/components/fr/controls"
import { useToast } from "@/components/Toasts"
import { applyActions } from "@/dialogs/AskClaude"
import { runCommand, useCommand } from "@/hooks/useCommand"
import { useStatus } from "@/hooks/queries"
import { useInbox } from "@/inbox/InboxPage"
import { spoken } from "@/lib/aiName"
import { WeekPaces } from "./WeekPaces"
import { TimeInput } from "@/components/fr/TimeInput"
import { NOTE_EXAMPLES, useNotes } from "@/settings/AboutYou"

type Strength = "Prefer" | "Strongly" | "Always"
const STRENGTHS: Strength[] = ["Prefer", "Strongly", "Always"]
const SOURCES: Record<string, [string, string]> = { you: ["user", "Yours"], learned: ["sparkle", "Learned from you"], default: ["sliders-horizontal", "Built in"] }
const DAY_OPTS: { value: string; label: string; days: string[] | null }[] = [
  { value: "every", label: "Every day", days: null },
  { value: "weekdays", label: "Weekdays", days: ["mon", "tue", "wed", "thu", "fri"] },
  { value: "weekends", label: "Weekends", days: ["sat", "sun"] },
]

export const useRules = () => useQuery({ queryKey: ["rules"], queryFn: () => query("rules") })

type RuleOut = Schemas["RuleOut"]

/** A rule command that shows its change in the list at once (`patch`), put back if the server refuses it. */
function useRuleCommand<N extends "rule_set" | "rule_remove" | "rule_edit">(name: N, label: (out: Output<N>) => string) {
  const client = useQueryClient()
  const toast = useToast()
  return (input: CommandInput<N>, patch: (rules: RuleOut[]) => RuleOut[]) =>
    runCommand(client, toast, name, input, { label, optimistic: (c) => c.setQueryData<RuleOut[]>(["rules"], (was) => was && patch(was)) })
}

const changed = (name: string, update: Partial<RuleOut>) => (rules: RuleOut[]) => rules.map((r) => (r.name === name ? { ...r, ...update } : r))

export function RulesPage() {
  const rules = useRules().data ?? []
  const byName = new Map(rules.map((r) => [r.name, r]))
  const owned = (useStatus().data?.config_keys ?? []).includes("rules")
  const mine = rules.filter((r) => r.source === "you").length
  // ?edit=<name> opens that rule in the box (the Projects page's "Exam focus … in Rules"); ?text= starts a new one
  const [params, setParams] = useSearchParams()
  const [editing, setEditing] = useState<{ rule: RuleOut; opened: number } | null>(null)
  const wanted = params.get("edit")
  useEffect(() => {
    const rule = wanted ? byName.get(wanted) : undefined
    if (rule && editing?.rule.name !== rule.name) setEditing({ rule, opened: Date.now() })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wanted, rules.length])
  const edit = (rule: RuleOut | null) => {
    setEditing(rule ? { rule, opened: Date.now() } : null)
    if (params.has("edit") || params.has("text")) setParams({}, { replace: true })
  }
  const row = (r: RuleOut) => <RuleRow key={r.name} rule={r} locked={owned} byName={byName} editing={editing?.rule.name === r.name} onEdit={() => edit(r)} />
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
              <H size={22}>Rules and notes</H>
              <span style={{ color: "var(--color-neutral-400)", textWrap: "pretty" }}>
                Tell Friday how you work, in your own words. A rule changes how it plans ("no work after 10pm"); a note changes how it reads your mail, calendars and documents ("labs are done in the lab session"). Rules marked Always never bend; the rest bend when they must.
              </span>
            </div>
            {owned ? <span className="fr-kicker">Your rules are set in friday.toml; change them there.</span> : <NewRule editing={editing} start={params.get("text") ?? ""} onDone={() => edit(null)} />}
            <div data-tour="week-paces" style={{ display: "flex", flexDirection: "column", gap: 8, padding: "6px 0 4px" }}>
              <span style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
                <span style={{ fontWeight: 500 }}>Your week</span>
                <span className="fr-kicker">Days that go easier or harder, every week. Click a day to change it.</span>
              </span>
              <WeekPaces />
            </div>
            <div style={{ display: "flex", flexDirection: "column" }}>
              {rules.filter((r) => !r.background).map(row)}
            </div>
            <details>
              <summary className="fr-kicker" style={{ cursor: "pointer", padding: "6px 0" }}>
                How Friday fills in the rest ({rules.filter((r) => r.background).length})
              </summary>
              <div style={{ display: "flex", flexDirection: "column" }}>{rules.filter((r) => r.background).map(row)}</div>
            </details>
          </section>
          <Notes />
        </div>
      </div>
    </>
  )
}

/** Notes about you (Settings' About you until 12 Nov): what the AI keeps in mind reading your mail, calendars and
 * documents, so it skips what needs no time and uses your lengths and your section's deadlines. */
function Notes() {
  const { notes, remove } = useNotes()
  return (
    <section style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <span style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
        <H size={18}>Notes</H>
        <span className="fr-kicker">Read with every email, calendar entry and document. They don't change the plan; rules do.</span>
      </span>
      {notes.map((n, i) => (
        <div key={n} className="fr-row" style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 10px", borderRadius: "var(--radius-md)", background: "var(--color-bg)" }}>
          <Icon name="note-pencil" size={15} style={{ color: "var(--color-neutral-400)", flex: "none" }} />
          <span style={{ flex: 1, textWrap: "pretty" }}>{n}</span>
          <button className="btn btn-ghost" onClick={() => remove(i)} aria-label={`Forget: ${n}`} style={{ padding: "2px 6px" }}>
            <Icon name="x" />
          </button>
        </div>
      ))}
      {!notes.length && (
        <span className="fr-kicker" style={{ textWrap: "pretty" }}>
          None yet. Type one in the box above and press Keep as a note, e.g. “{NOTE_EXAMPLES[0]}” or “{NOTE_EXAMPLES[4]}”.
        </span>
      )}
    </section>
  )
}

/** Claude reading a rule Friday couldn't: asking, what it said, and which of its rules you've ticked. */
type ClaudeReading = { busy: boolean; error?: string; answer?: Schemas["AskClaudeOut"]; kept: number[] }

/** What the box is editing: a rule, and when its pencil was pressed (pressed again, it opens afresh). */
type Editing = { rule: RuleOut; opened: number } | null

function NewRule({ editing, start, onDone }: { editing: Editing; start: string; onDone: () => void }) {
  const navigate = useNavigate()
  const client = useQueryClient()
  const toast = useToast()
  const [claude, setClaude] = useState<ClaudeReading | null>(null)
  const llm = useInbox().data?.llm as { ready?: boolean } | undefined
  const demo = !!useStatus().data?.demo // the demo's stand-in AI
  const aiName = useAi().name
  const strengths = new Map((useRules().data ?? []).map((r) => [r.name, r.strength]))
  const [text, setText] = useState(start)
  const [overrides, setOverrides] = useState<Record<string, unknown>>({})
  const [strength, setStrength] = useState<Strength | null>(null)
  // Editing a rule of yours: its saved reading stands under your corrections while its words are the same
  const [base, setBase] = useState<Record<string, unknown>>({})
  const box = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const yours = editing?.rule.words != null ? editing.rule : null
  const ai = (!!llm?.ready || demo) && !yours // an AI that can be asked (whichever is chosen); it adds, so not in an edit
  useEffect(() => {
    if (!editing) return
    setText(editing.rule.words ?? "")
    setBase((editing.rule.reading as Record<string, unknown>) ?? {})
    setOverrides({})
    setStrength(editing.rule.strength as Strength)
    setClaude(null)
    box.current?.scrollIntoView?.({ block: "nearest", behavior: "smooth" })
    input.current?.focus()
  }, [editing])
  const sent = yours && text === yours.words ? { ...base, ...overrides } : overrides
  const typed = JSON.stringify({ text, overrides: sent, editing: yours?.name ?? "" })
  const settled = useSettled(typed, 200)
  const preview = useQuery({
    queryKey: ["rule_read", settled],
    queryFn: () => {
      const { text, overrides, editing } = JSON.parse(settled)
      return query("rule_read", { text, overrides: JSON.stringify(overrides), editing })
    },
    enabled: !!text.trim(),
  }).data
  const add = useCommand("rule_add", { label: (o) => o.result.message ?? "Added" })
  const save = useRuleCommand("rule_edit", (o) => o.result.message ?? "Saved")
  const notes = useNotes()
  // a note, not a rule: what Friday reads keeps it in mind; the plan doesn't change (About you, 12 Nov)
  const keepNote = () => {
    if (!text.trim()) return
    notes.add(text)
    clear()
  }
  const switchOff = useCommand("rule_set", { label: () => "Switched off" })
  const reading = preview?.reading as Reading | null | undefined
  const chosen = strength ?? ((preview?.strength as Strength) || "Prefer")
  const unread = !!text.trim() && !!preview && !reading
  // A sentence with several stretches of the day reads as a rule for each (8 Nov), added together.
  const all = preview && reading ? [preview, ...(preview.also ?? [])] : []
  // Asking the AI: what Friday couldn't read, or what it read and you'd rather the AI read (8 Nov: "the deterministic
  // interpretation might be wrong").
  const asking = unread || !!claude
  const clear = () => (setText(""), setOverrides({}), setBase({}), setStrength(null), setClaude(null))
  const cancel = () => (clear(), onDone())
  /** What Friday couldn't read, to Claude, answered here (no dialog): its rules, ticked, for ↩ or Add to apply. */
  const askInline = async () => {
    setClaude({ busy: true, kept: [] })
    try {
      const out = await command("ask_claude", { text, purpose: "rule" })
      const kept = out.result.actions.map((a, i) => (a.error ? -1 : i)).filter((i) => i >= 0)
      setClaude({ busy: false, answer: out.result, kept })
    } catch (e) {
      setClaude({ busy: false, kept: [], error: errorWords(e) })
    }
  }
  const applyClaude = async () => {
    const answer = claude?.answer
    if (answer && (await applyActions(claude.kept.map((i) => answer.actions[i]), client, toast))) clear()
  }
  /** ↩ or the button: add what Friday read (or save the rule you're editing), or hand what it couldn't read to
   * Claude. Read again if typing ran ahead. */
  const sending = useRef(false) // ↩ twice, or ↩ and a click, adds it once
  const submit = async (replacing?: string) => {
    if (!text.trim() || sending.current) return
    sending.current = true
    try {
      const now = settled === typed && preview ? preview : await query("rule_read", { text, overrides: JSON.stringify(sent), editing: yours?.name ?? "" }).catch(() => null)
      if (!now) return
      if (yours) {
        if (!now.reading || now.also?.length) return
        const update = { sentence: now.sentence, strength: chosen, words: text, reading: now.reading }
        if (await save({ name: yours.name, text, overrides: sent as Record<string, never>, strength: chosen }, changed(yours.name, update))) cancel()
        return
      }
      if (!now.reading || claude) {
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
  if (editing && !yours) return <BuiltInEdit key={editing.opened} rule={editing.rule} onDone={onDone} />
  const label = yours ? "Save" : !asking || !ai ? (all.length > 1 ? `Add ${all.length} rules` : "Add rule") : claude?.busy ? `Asking ${aiName}…` : claude?.answer?.actions.length ? `Add ${claude.kept.length > 1 ? `${claude.kept.length} rules` : "rule"}` : claude?.answer ? "Ask again" : `Ask ${aiName}`
  const blocked = yours ? !reading || all.length > 1 : (unread && !ai) || !!claude?.busy || (!!claude?.answer && !claude.kept.length && !!claude.answer.actions.length)
  return (
    <div ref={box} data-tour="rule-new" data-editing={yours ? yours.name : undefined} style={{ display: "flex", flexDirection: "column", gap: 12, padding: 16, borderRadius: "var(--radius-lg)", background: "var(--color-bg)", boxShadow: yours ? "inset 0 0 0 1px var(--color-accent-300)" : undefined }}>
      {yours && (
        <span className="fr-kicker" style={{ display: "flex", gap: 6, alignItems: "baseline", textWrap: "pretty" }}>
          <Icon name="pencil-simple" size={12} style={{ alignSelf: "center" }} />
          <span>
            Editing <span style={{ fontWeight: 500, color: "var(--color-text)" }}>“{yours.sentence}”</span>: change the words or Friday’s reading, then Save. It stays where it is.
          </span>
        </span>
      )}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <Icon name={yours ? "pencil-simple" : "plus"} size={18} style={{ color: "var(--color-accent-300)" }} />
        <input ref={input} value={text} onChange={(e) => (setText(e.target.value), setOverrides({}), setStrength(yours ? chosen : null), setClaude(null))} onKeyDown={(e) => (e.key === "Enter" ? submit() : e.key === "Escape" && yours ? cancel() : undefined)} placeholder="I prefer eating lunch before 1pm" aria-label={yours ? "Rule" : "New rule"} style={{ flex: 1, minWidth: 0, border: 0, outline: 0, background: "transparent", color: "var(--color-text)", font: "inherit", fontSize: 16 }} />
        {yours ? (
          <button className="btn btn-secondary" onClick={cancel}>
            Cancel
          </button>
        ) : (
          <button className="btn btn-secondary" onClick={keepNote} disabled={!text.trim()} title="Kept for reading your mail, calendars and documents; the plan doesn't change">
            Keep as a note
          </button>
        )}
        <button className="btn btn-primary" onClick={() => submit()} disabled={!text.trim() || blocked}>
          {asking && ai && !claude?.answer && <Icon name="sparkle" />}
          {label}
        </button>
      </div>
      {text.trim() && preview ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "12px 14px", marginLeft: 28, borderRadius: "var(--radius-md)", background: "var(--color-surface)" }}>
          {claude ? (
            <>
              <ClaudeRules claude={claude} onTick={(kept) => setClaude({ ...claude, kept })} />
              {reading && !claude.busy && (
                <button className="fr-link" onClick={() => setClaude(null)} style={{ alignSelf: "flex-start", fontSize: 12 }}>
                  Back to Friday’s reading
                </button>
              )}
            </>
          ) : !reading && yours ? (
            <span style={{ display: "flex", gap: 8, alignItems: "baseline", fontSize: 12, color: "var(--fr-warn)", textWrap: "pretty" }}>
              <Icon name="question" size={13} style={{ flexShrink: 0, alignSelf: "center" }} />
              <span>Friday can’t read that as a rule: say it another way. Cancel keeps the rule as it was.</span>
            </span>
          ) : !reading ? (
            // What the grammar can't read goes to Claude (COMBINED.md 37), as rules to confirm: ↩ sends it.
            <span style={{ display: "flex", gap: 8, alignItems: "baseline", fontSize: 12, color: ai ? "var(--color-neutral-300)" : "var(--fr-warn)", textWrap: "pretty" }}>
              <Icon name={ai ? "sparkle" : "question"} size={13} style={{ color: ai ? "var(--color-accent-300)" : undefined, flexShrink: 0, alignSelf: "center" }} />
              {ai ? (
                <span>Friday can’t read this one itself. Press ↩ and {spoken(aiName)} will turn it into rules, shown here for you to check before anything changes.</span>
              ) : (
                <span>
                  Friday can’t read that as a rule yet, and no AI is set up to read it instead.{" "}
                  <button className="fr-link" onClick={() => navigate("/settings/integrations")} style={{ fontSize: 12 }}>
                    Set up an AI
                  </button>{" "}
                  or say it another way, like the example in the box.
                </span>
              )}
            </span>
          ) : (
            <>
              <span style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, color: "var(--color-accent-300)" }}>
                <Icon name="check-circle" size={13} />
                {all.length > 1 ? `Friday read this as ${all.length} rules` : "Friday read this as"}
              </span>
              {all.map((r) => (
                <H key={r.sentence} size={16}>
                  {r.sentence}
                </H>
              ))}
              {yours && preview.starts_over && (
                // 14 Nov: an edit that says another kind of rule is a new rule, and saying so before Save
                <span style={{ display: "flex", gap: 8, alignItems: "baseline", fontSize: 12, color: "var(--fr-warn)", textWrap: "pretty" }}>
                  <Icon name="warning" size={13} style={{ flexShrink: 0, alignSelf: "center" }} />
                  <span>This is another kind of rule than “{preview.replaces}”, so it takes its place as a new rule: how often it’s kept starts over.</span>
                </span>
              )}
              {yours && all.length > 1 && <span className="fr-kicker" style={{ color: "var(--fr-warn)", textWrap: "pretty" }}>An edit is one rule: say one here, and add the others as new rules.</span>}
              {all.length > 1 ? (
                <>
                  <span className="fr-kicker">{preview.effect}{chosen === "Always" ? ", and never bends." : ", unless it has to."}</span>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span className="fr-kicker">Strength</span>
                    <Seg options={STRENGTHS} value={chosen} onPick={setStrength} onBg />
                  </div>
                </>
              ) : reading.kind === "pace" ? (
                // A pace for weekdays is a setting: it shows under Your week, with no strength to choose.
                <span className="fr-kicker">{preview.effect}. It shows under Your week.</span>
              ) : reading.kind === "exam_focus" ? (
                // A wall, not a preference: other courses' work waits, so there's no strength to pick (14 Nov)
                <>
                  <span className="fr-kicker" style={{ textWrap: "pretty" }}>{preview.effect}.</span>
                  <Fields reading={reading} overrides={overrides} onSet={set} onReset={() => setOverrides({})} />
                </>
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
              {all.length === 1 &&
                (preview.conflicts ?? []).map((c) => (
                  <Conflict key={c.other} conflict={c} mine={chosen} theirs={strengths.get(c.other)} onReplace={yours ? undefined : () => submit(c.other)} />
                ))}
              {all.length > 1 &&
                all.flatMap((r) => r.conflicts ?? []).map((c) => (
                  <span key={c.other} className="fr-kicker" style={{ color: c.overlap ? undefined : "var(--fr-warn)", textWrap: "pretty" }}>
                    {c.overlap ? "Overlaps" : "Contradicts"} “{c.other_sentence}”: {c.why}.
                  </span>
                ))}
              {ai && (
                // The grammar's reading can be wrong: the AI reads it instead, shown here to check before anything changes.
                <button className="fr-link" onClick={askInline} style={{ alignSelf: "flex-start", fontSize: 12, display: "inline-flex", gap: 6, alignItems: "center" }}>
                  <Icon name="sparkle" size={12} />
                  Not what you meant? Ask {aiName}
                </button>
              )}
            </>
          )}
        </div>
      ) : null}
    </div>
  )
}

/** A built-in rule in the box (14 Nov): its words stay, its number (hours of focused work in a row, days early) and
 * its strength change. The sentence shows the new number as you change it. */
function BuiltInEdit({ rule, onDone }: { rule: RuleOut; onDone: () => void }) {
  const box = useRef<HTMLDivElement>(null)
  const n = rule.number
  const [value, setValue] = useState(n?.value ?? 0)
  const [strength, setStrength] = useState(rule.strength as Strength)
  const save = useRuleCommand("rule_edit", (o) => o.result.message ?? "Saved")
  useEffect(() => box.current?.scrollIntoView?.({ block: "nearest", behavior: "smooth" }), [])
  const fits = !n || (Number.isFinite(value) && value >= n.low && value <= n.high)
  const said = !n ? rule.sentence : value === 1 ? n.one : n.said.replace("{n}", String(value))
  const options = rule.strength === "Always" ? (["Always"] as Strength[]) : (["Prefer", "Strongly"] as Strength[])
  const submit = async () => {
    if (!fits) return
    const input = { name: rule.name, strength, ...(n && value !== n.value ? { number: value } : {}) }
    const number = n ? { ...n, value } : n
    if (await save(input, changed(rule.name, { sentence: said, strength, number }))) onDone()
  }
  return (
    <div ref={box} data-tour="rule-new" data-editing={rule.name} style={{ display: "flex", flexDirection: "column", gap: 12, padding: 16, borderRadius: "var(--radius-lg)", background: "var(--color-bg)", boxShadow: "inset 0 0 0 1px var(--color-accent-300)" }}>
      <span className="fr-kicker" style={{ display: "flex", gap: 6, alignItems: "baseline", textWrap: "pretty" }}>
        <Icon name="pencil-simple" size={12} style={{ alignSelf: "center" }} />
        <span>Editing a built-in rule: its words stay; {n ? "its number and strength change" : "its strength changes"}. It stays where it is.</span>
      </span>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <Icon name="sliders-horizontal" size={18} style={{ color: "var(--color-accent-300)" }} />
        <span style={{ flex: 1, minWidth: 0, fontSize: 16, textWrap: "pretty" }}>{said}</span>
        <button className="btn btn-secondary" onClick={onDone}>
          Cancel
        </button>
        <button className="btn btn-primary" onClick={submit} disabled={!fits}>
          Save
        </button>
      </div>
      <div className="fr-row" style={{ display: "grid", gridTemplateColumns: "72px minmax(0,1fr)", gap: "8px 12px", alignItems: "center", padding: "12px 14px", marginLeft: 28, borderRadius: "var(--radius-md)", background: "var(--color-surface)" }}>
        {n && (
          <>
            <span className="fr-kicker">{n.label}</span>
            <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input type="number" className="input" aria-label={n.label} min={n.low} max={n.high} step={n.step} value={Number.isFinite(value) ? value : ""} onChange={(e) => setValue(e.target.value === "" ? Number.NaN : Number(e.target.value))} onKeyDown={(e) => (e.key === "Enter" ? submit() : e.key === "Escape" ? onDone() : undefined)} style={{ width: 90, padding: "4px 8px", fontSize: 12, minHeight: 0 }} />
              <span className="fr-kicker" style={{ color: fits ? undefined : "var(--fr-warn)" }}>
                {n.unit}
                {fits ? "" : `: from ${n.low} to ${n.high}`}
              </span>
            </span>
          </>
        )}
        <span className="fr-kicker">Strength</span>
        <Seg options={options} value={strength} onPick={setStrength} onBg />
      </div>
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
function Conflict({ conflict: c, mine, theirs, onReplace }: { conflict: Schemas["RuleConflict"]; mine: string; theirs?: string; onReplace?: () => void }) {
  const outcome = c.overlap ? "" : mine === "Always" && theirs === "Always" ? " Both are Always, so Friday can’t keep both." : theirs === "Always" ? " That one is Always, so this one would give way there." : mine === "Always" ? " This one is Always, so that one would give way there." : " Friday would bend one of them; once both are in, you can say which wins."
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, padding: "10px 12px", borderRadius: "var(--radius-md)", background: c.overlap ? "var(--color-bg)" : "color-mix(in srgb, var(--fr-warn) 9%, var(--color-bg))" }}>
      <span style={{ display: "flex", gap: 8, alignItems: "baseline", fontSize: 12, textWrap: "pretty" }}>
        <Icon name={c.overlap ? "info" : "warning"} size={13} style={{ color: c.overlap ? "var(--color-neutral-400)" : "var(--fr-warn)", flexShrink: 0, alignSelf: "center" }} />
        <span>
          {c.overlap ? "Overlaps" : "Contradicts"} <span style={{ fontWeight: 500 }}>“{c.other_sentence}”</span>: {c.why}.{outcome}
        </span>
      </span>
      {onReplace && (
        <button className="fr-link" onClick={onReplace} style={{ alignSelf: "flex-start", fontSize: 12, marginLeft: 21 }}>
          Add this, and switch that one off
        </button>
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
  const rels = reading.kind === "window" ? ["before", "after", "between", { value: "not_between", label: "not between" }] : []
  if (reading.kind === "exam_focus")
    return (
      <div className="fr-row" style={{ display: "grid", gridTemplateColumns: "84px minmax(0,1fr)", gap: "8px 12px", alignItems: "center", paddingTop: 8 }}>
        <span className="fr-kicker">Days before</span>
        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <DaysBefore value={reading.amount ?? 3} onSet={(n) => onSet("amount", n)} />
          {pin("amount")}
        </span>
      </div>
    )
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
      {!["cap", "early", "after", "spread", "cluster"].includes(reading.kind) && (
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

/** Exam focus's days, 1 to 14: what you type shows as typed, and counts once it's a whole number in range. */
function DaysBefore({ value, onSet }: { value: number; onSet: (n: number) => void }) {
  const [typed, setTyped] = useState(String(value))
  useEffect(() => setTyped((was) => (Number(was) === value ? was : String(value))), [value])
  const n = Number(typed)
  const fits = typed !== "" && Number.isInteger(n) && n >= 1 && n <= 14
  return (
    <>
      <input type="number" min={1} max={14} step={1} className="input" aria-label="Days before" value={typed} onChange={(e) => (setTyped(e.target.value), Number.isInteger(Number(e.target.value)) && Number(e.target.value) >= 1 && Number(e.target.value) <= 14 && onSet(Number(e.target.value)))} style={{ width: 90, padding: "4px 8px", fontSize: 12, minHeight: 0 }} />
      <span className="fr-kicker" style={{ color: fits ? undefined : "var(--fr-warn)" }}>{fits ? (n === 1 ? "day" : "days") : "days: from 1 to 14"}</span>
    </>
  )
}

function RuleRow(props: { rule: RuleOut; locked: boolean; byName: Map<string, RuleOut>; editing: boolean; onEdit: () => void }) {
  const { rule, locked, byName, editing, onEdit } = props
  const said = (name: string) => byName.get(name)?.sentence ?? name
  const setRule = useRuleCommand("rule_set", () => "Saved")
  const set = (input: { name: string; enabled?: boolean; strength?: Strength }) => setRule(input, changed(input.name, input))
  const removeRule = useRuleCommand("rule_remove", () => "Deleted")
  const remove = (input: { name: string }) => removeRule(input, (rules) => rules.filter((r) => r.name !== input.name))
  const win = useCommand("rule_win", { label: (o) => o.result.message ?? "Saved" })
  const [asking, setAsking] = useState(false)
  // 14 Nov: "Violated on Tue, Thu" and a Why? that says plainly what took the time, not "Gives way" and "What to?"
  const bends = rule.enabled && rule.strength !== "Always" && (rule.violated ?? []).length > 0
  const [icon, source] = SOURCES[rule.source] ?? SOURCES.default
  const options = rule.type === "exam_focus" ? (["Always"] as Strength[]) : rule.source === "you" ? STRENGTHS : rule.strength === "Always" ? (["Always"] as Strength[]) : (["Prefer", "Strongly"] as Strength[])
  return (
    <div className="fr-row fr-rule-row" data-rule={rule.name} data-editing={editing || undefined} style={{ display: "grid", gridTemplateColumns: "36px minmax(180px,1fr) auto 60px", gap: "8px 14px", alignItems: "center", padding: "12px 0", opacity: rule.enabled ? 1 : 0.5, boxShadow: editing ? "inset 3px 0 0 var(--color-accent-300)" : undefined }}>
      <Switch on={rule.enabled} onToggle={() => !locked && set({ name: rule.name, enabled: !rule.enabled })} label={`${rule.enabled ? "Switch off" : "Switch on"} ${rule.sentence}`} />
      <span style={{ display: "flex", flexDirection: "column", gap: 3, minWidth: 0 }}>
        <span style={{ fontWeight: 500 }}>{rule.sentence}</span>
        <span style={{ display: "flex", gap: 10, flexWrap: "wrap", fontSize: 12, color: "var(--color-neutral-500)" }}>
          <span style={{ display: "inline-flex", gap: 5, alignItems: "center" }}>
            <Icon name={icon} size={12} />
            {source}
          </span>
          <span>
            {rule.effect}
            {bends && !locked && (
              <>
                {" · "}
                <button className="fr-plain fr-link" onClick={() => setAsking(!asking)} aria-expanded={asking} style={{ fontSize: 12 }}>
                  Why?
                </button>
              </>
            )}
          </span>
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
        <span style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
          <button className="btn btn-icon btn-ghost" onClick={onEdit} aria-label="Edit rule" aria-pressed={editing} title={rule.words != null ? "Change its words, its reading or its strength" : "Change its number or its strength"} style={{ width: 28, height: 28, color: editing ? "var(--color-accent-300)" : "var(--color-neutral-500)" }}>
            <Icon name="pencil-simple" />
          </button>
          <button className="btn btn-icon btn-ghost" onClick={() => remove({ name: rule.name })} aria-label="Delete rule" style={{ width: 28, height: 28, color: "var(--color-neutral-500)" }}>
            <Icon name="trash" />
          </button>
        </span>
      ) : (
        <span />
      )}
      {asking && <Why rule={rule} onAnswer={(winner, loser) => win({ winner, loser })} />}
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

/** Why a rule is violated in this plan (14 Nov), said plainly: the work that took its time and what it's due by, read
 * from the plan at once ("Tue and Thu: CS essay (due Wed) needed those hours"); and, planned once more with the rule
 * weighed far higher (a few seconds), another rule it clashes with, and which should win. Stays open once answered. */
function Why({ rule, onAnswer }: { rule: RuleOut; onAnswer: (winner: string, loser: string) => void }) {
  const why = useQuery({ queryKey: ["rule_why", rule.name], queryFn: () => query("rule_why", { name: rule.name }), staleTime: 30_000 })
  const found = useQuery({ queryKey: ["rule_clash", rule.name], queryFn: () => query("rule_clash", { name: rule.name }), staleTime: 60_000 })
  const [answered, setAnswered] = useState<string | null>(null)
  const clash = found.data
  const lines = why.data?.lines ?? []
  const answer = (winner: string, loser: string, said: string) => (onAnswer(winner, loser), setAnswered(said))
  return (
    <div style={{ gridColumn: "2 / -1", display: "flex", flexDirection: "column", gap: 8, padding: "12px 14px", borderRadius: "var(--radius-md)", background: "var(--color-bg)" }}>
      {why.isLoading ? (
        <span className="fr-kicker">Looking at this plan…</span>
      ) : (
        lines.map((line) => (
          <span key={line.said} style={{ display: "flex", gap: 8, alignItems: "baseline", fontSize: 13, textWrap: "pretty" }}>
            <Icon name="calendar-dots" size={13} style={{ color: "var(--color-neutral-400)", flexShrink: 0, alignSelf: "center" }} />
            <span>{line.said}</span>
          </span>
        ))
      )}
      {found.isLoading ? (
        <span className="fr-kicker">Checking whether another rule is in the way (a few seconds)…</span>
      ) : clash?.other ? (
        <>
          <span style={{ display: "flex", gap: 8, alignItems: "baseline", fontSize: 13, textWrap: "pretty" }}>
            <Icon name="warning" size={13} style={{ color: "var(--fr-warn)", flexShrink: 0, alignSelf: "center" }} />
            <span>{clash.said}</span>
          </span>
          {answered ? (
            <span className="fr-kicker" style={{ marginLeft: 21 }}>{answered} Click it above to change it.</span>
          ) : (
            <>
              <span style={{ display: "flex", gap: 6, flexWrap: "wrap", marginLeft: 21 }}>
                <button className="btn btn-secondary" onClick={() => answer(rule.name, clash.other as string, `“${clash.sentence}” wins from now on.`)} style={{ fontSize: 12 }}>
                  {clash.sentence}
                </button>
                <button className="btn btn-secondary" onClick={() => answer(clash.other as string, rule.name, `“${clash.other_sentence}” wins from now on.`)} style={{ fontSize: 12 }}>
                  {clash.other_sentence}
                </button>
              </span>
              <span style={{ fontSize: 11, color: "var(--color-neutral-500)", marginLeft: 21 }}>Friday remembers your answer for these two rules.</span>
            </>
          )}
        </>
      ) : !why.isLoading && !lines.length ? (
        <span className="fr-kicker">Friday couldn’t tell what took that time in this plan.</span>
      ) : null}
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
