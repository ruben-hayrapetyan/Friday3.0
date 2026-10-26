// What Friday learned (v22 Insights): each suggestion with why, Approve or Not now; once answered, what you chose
// with Undo. Suggestions are a new set of weights, a proposed rule, keeping a "never" hard, learned lengths, the
// hours your plans tend to slip, and a kind you keep doing before another that's planned first.

import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { query } from "@/api/client"
import { Icon } from "@/components/fr/controls"
import { useToast } from "@/components/Toasts"
import { undoAll, useCommand } from "@/hooks/useCommand"
import { weighing } from "./shapes"

interface Suggestion {
  key: string
  icon: string
  title: string
  why: string
  yes: () => Promise<{ command_id: number | null } | undefined>
  no: () => Promise<{ command_id: number | null } | undefined>
}

export function Learned() {
  const learning = useQuery({ queryKey: ["learning"], queryFn: () => query("learning") }).data
  const questions = useQuery({ queryKey: ["questions"], queryFn: () => query("questions") }).data
  const rules = useQuery({ queryKey: ["rules"], queryFn: () => query("rules") }).data
  const apply = useCommand("learn_apply", { label: (o) => o.result.message ?? "Approved" })
  const reject = useCommand("learn_reject", { label: (o) => o.result.message ?? "Kept as it was" })
  const answer = useCommand("proposal_answer", { label: (o) => o.result.message ?? "Thanks" })
  const use = useCommand("learn_module", { label: (o) => o.result.message ?? "Saved" })
  const order = useCommand("learn_order", { label: (o) => o.result.message ?? "Saved" })
  const client = useQueryClient()
  const toast = useToast()
  const [closed, setClosed] = useState<Record<string, { state: string; id: number | null }>>({})
  const items: Suggestion[] = []
  // A change is {rule, from, to}: said in the rule's own words (the Rules page's sentence), more or less weight.
  const suggested = learning?.suggested as { version: number; changes: { rule: string; from: number; to: number }[] } | null | undefined
  const said = (rule: string) => rules?.find((r) => r.name === rule)?.sentence ?? rule.replaceAll("_", " ")
  if (suggested) {
    items.push({
      key: `profile${suggested.version}`,
      icon: "sliders-horizontal",
      title: "Weigh your preferences the way you answered",
      why: weighing(suggested.changes ?? [], said) || "From your answers and the blocks you moved.",
      yes: () => apply({ version: suggested.version }),
      no: () => reject({ version: suggested.version }),
    })
  }
  if (questions?.proposal) {
    const p = questions.proposal
    items.push({ key: `rule${p.name}`, icon: "list-plus", title: p.sentence.replace(" Add that as a rule?", ""), why: "You keep moving work away from this. Add it as a rule?", yes: () => answer({ kind: "rule", name: p.name, yes: true }), no: () => answer({ kind: "rule", name: p.name, yes: false }) })
  }
  if (questions?.wall) {
    const w = questions.wall
    items.push({ key: `wall${w.name}`, icon: "wall", title: w.sentence ?? `Keep ${w.name} as a hard rule?`, why: "It gave way to deadlines lately. Keep it hard, or let it bend?", yes: () => answer({ kind: "wall", name: w.name, yes: true }), no: () => answer({ kind: "wall", name: w.name, yes: false }) })
  }
  const durations = learning?.durations as { in_use: boolean; better: boolean | null; error: number; error_before: number } | null | undefined
  if (durations?.better && !durations.in_use) {
    items.push({ key: "durations", icon: "timer", title: "Use the lengths Friday learned", why: `They're typically ${Math.round(durations.error * 100)}% off, against ${Math.round(durations.error_before * 100)}% for the estimates now.`, yes: () => use({ module: "durations", use: true }), no: async () => ({ command_id: null }) })
  }
  const energy = learning?.energy as { in_use: boolean; worst: { day: string; time: string }[] } | null | undefined
  if (energy?.worst.length && !energy.in_use) {
    items.push({ key: "energy", icon: "battery-low", title: "Plan less deep work when it tends to slip", why: `Planned work often slips around ${energy.worst.slice(0, 3).map((w) => `${w.day} ${w.time}`).join(", ")}.`, yes: () => use({ module: "energy", use: true }), no: async () => ({ command_id: null }) })
  }
  const first = learning?.order
  if (first) {
    const plural = (kind: string) => (kind.endsWith("s") ? kind : `${kind}s`)
    items.push({
      key: `order${first.first}>${first.then}`,
      icon: "sort-ascending",
      title: `Plan ${plural(first.first)} before ${plural(first.then)}`,
      why: `You started a ${first.first} instead of the ${first.then} planned then ${first.chose} of ${first.of} times.`,
      yes: () => order({ first: first.first, then: first.then, use: true }),
      no: () => order({ first: first.first, then: first.then, use: false }),
    })
  }
  const shown = [...items, ...Object.keys(closed).filter((k) => !items.some((i) => i.key === k)).map((k) => ({ key: k, closedOnly: true }))]
  const act = async (s: Suggestion, yes: boolean) => {
    const out = await (yes ? s.yes() : s.no())
    if (out) setClosed({ ...closed, [s.key]: { state: yes ? "Approved" : "Not now", id: out.command_id } })
  }
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {items.map((s) => {
        const c = closed[s.key]
        return (
          <div key={s.key} className="fr-row" style={{ display: "grid", gridTemplateColumns: "28px minmax(0,1fr) auto", gap: 14, alignItems: "center", padding: "12px 0", opacity: c ? 0.6 : 1 }}>
            <span style={{ width: 28, height: 28, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", background: "var(--color-bg)" }}>
              <Icon name={s.icon} size={15} style={{ color: "var(--color-accent-300)" }} />
            </span>
            <span style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
              <span style={{ fontWeight: 500 }}>{s.title}</span>
              <span className="fr-kicker" style={{ textWrap: "pretty" }}>
                {s.why}
              </span>
            </span>
            {c ? (
              <span style={{ display: "flex", gap: 10, alignItems: "center", fontSize: 12, color: "var(--color-neutral-400)" }}>
                {c.state}
                {c.id !== null && (
                  <button className="fr-link" onClick={async () => (await undoAll(client, toast, [c.id as number]), setClosed(({ [s.key]: _, ...rest }) => rest))}>
                    Undo
                  </button>
                )}
              </span>
            ) : (
              <span style={{ display: "flex", gap: 6 }}>
                <button className="btn btn-ghost" onClick={() => act(s, false)}>
                  Not now
                </button>
                <button className="btn btn-primary" onClick={() => act(s, true)}>
                  Approve
                </button>
              </span>
            )}
          </div>
        )
      })}
      {!items.length && shown.length === 0 && <div className="fr-row" style={{ padding: "14px 0", color: "var(--color-neutral-500)" }}>Nothing to approve. Friday learns from your reviews and the blocks you move.</div>}
    </div>
  )
}
