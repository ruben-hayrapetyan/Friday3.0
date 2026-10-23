// Teach by example: pick a block, then click where you would rather have it. Friday says which rules keep it where
// it is (why_not: the cost of the move, rule by rule, or the wall in the way) and offers the change that would let
// it move: weaken or switch off the rule you are fighting, or pin the block there. Each offer names its command.

import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { query } from "@/api/client"
import { Icon } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { when } from "@/lib/format"
import { useRules } from "@/rules/RulesPage"
import { useShell } from "@/shell/ShellContext"
import { MiniWeek, Page, useBaseline } from "./shared"

const points = (cost: number) => (cost / 100).toFixed(1)

export function TeachPage() {
  const { saved, fixed } = useBaseline()
  const [picked, setPicked] = useState<{ itemId: number; start: string } | null>(null)
  const [target, setTarget] = useState<string | null>(null)
  const key = picked ? `T${picked.itemId}@${picked.start}` : null
  return (
    <Page
      wide
      title="Teach by example"
      idea="Instead of reading rules, argue with the plan. Click a block, then click where you would rather have it. Friday answers with the rules that keep it where it is, how much each one objects, and the one change that would let it move."
    >
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 360px", gap: 28, alignItems: "start" }}>
        {saved && (
          <MiniWeek
            plan={saved}
            fixed={fixed}
            pickedItem={picked?.itemId}
            onPickBlock={(itemId, start) => {
              setPicked({ itemId, start })
              setTarget(null)
            }}
            onPickTime={(local) => picked && setTarget(local)}
          />
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: 16, position: "sticky", top: 0 }}>
          {key ? <Why blockKey={key} /> : <span className="fr-kicker">1. Click a block in the week.</span>}
          {key && !target && <span className="fr-kicker">2. Click an empty time where you would rather do it.</span>}
          {key && target && picked && <WhyNot blockKey={key} itemId={picked.itemId} target={target} />}
        </div>
      </div>
    </Page>
  )
}

function useRuleWords() {
  const rules = useRules().data ?? []
  return { rules, said: (name: string) => rules.find((r) => r.name === name)?.sentence ?? name.replace(/_/g, " ") }
}

function Why({ blockKey }: { blockKey: string }) {
  const why = useQuery({ queryKey: ["why", blockKey], queryFn: () => query("why", { key: blockKey }) }).data
  const { said } = useRuleWords()
  if (!why) return <span className="fr-kicker">Asking why it’s here…</span>
  const costs = Object.entries(why.costs).filter(([, c]) => c > 0)
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <span className="fr-kicker">Why it’s here</span>
      <span>{why.sentence}</span>
      {costs.length > 0 && <span style={{ fontSize: 12, color: "var(--color-neutral-500)" }}>Already bending here: {costs.map(([n, c]) => `${said(n)} (${points(c)})`).join(", ")}</span>}
    </div>
  )
}

function WhyNot({ blockKey, itemId, target }: { blockKey: string; itemId: number; target: string }) {
  const { today } = useShell()
  const answer = useQuery({ queryKey: ["why_not", blockKey, target], queryFn: () => query("why_not", { key: blockKey, start: target }), retry: false })
  const { rules, said } = useRuleWords()
  const ruleSet = useCommand("rule_set", { label: () => "Rule changed; Friday is replanning" })
  const pin = useCommand("pin", { label: () => "Pinned there" })
  if (answer.error) return <span style={{ color: "var(--fr-due)" }}>{answer.error.message}</span>
  const a = answer.data
  if (!a) return <span className="fr-kicker">Trying it at {when(target, today)}…</span>
  const against = Object.entries(a.difference)
    .filter(([, c]) => c > 0)
    .sort((x, y) => y[1] - x[1])
  // The planner's own workings (keeping the plan steady, mostly) are no rule to argue with: a pin is the answer there.
  const top = rules.find((r) => r.name === against[0]?.[0] && !r.background)
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <span className="fr-kicker">Moving it to {when(a.to_start ?? target, today)}</span>
      {a.wall ? (
        <span style={{ display: "flex", gap: 8 }}>
          <Icon name="wall" size={16} />
          It can’t go there: {a.wall}.
        </span>
      ) : against.length === 0 ? (
        <span>No rule objects to that. Friday kept it where it is to keep the plan steady, or another block needed the spot.</span>
      ) : (
        <>
          <span>
            {against.length === 1 ? "One rule objects" : `${against.length} rules object`}, {points(a.total)} points in all:
          </span>
          {against.map(([name, cost]) => (
            <Objection key={name} words={said(name)} cost={cost} max={against[0][1]} />
          ))}
        </>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 6 }}>
        {top?.editable && top.strength === "Strongly" && (
          <button className="btn btn-ghost" onClick={() => ruleSet({ name: top.name, strength: "Prefer" })} style={{ justifyContent: "flex-start" }}>
            Hold “{top.sentence}” less strongly (rule_set: Prefer)
          </button>
        )}
        {top?.editable && top.enabled && (
          <button className="btn btn-ghost" onClick={() => ruleSet({ name: top.name, enabled: false })} style={{ justifyContent: "flex-start" }}>
            Switch off “{top.sentence}” (rule_set)
          </button>
        )}
        {!a.wall && (
          <button className="btn btn-ghost" onClick={() => pin({ id: itemId, start: a.to_start ?? target, kind: "preferred" })} style={{ justifyContent: "flex-start" }}>
            Just this once: prefer it here (pin, preferred)
          </button>
        )}
      </div>
    </div>
  )
}

function Objection({ words, cost, max }: { words: string; cost: number; max: number }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 90px 40px", gap: 8, alignItems: "center", fontSize: 13 }}>
      <span>{words}</span>
      <span style={{ height: 6, borderRadius: 3, background: "color-mix(in srgb, var(--color-text) 8%, transparent)" }}>
        <span style={{ display: "block", height: "100%", borderRadius: 3, width: `${(100 * cost) / max}%`, background: "var(--fr-warn)" }} />
      </span>
      <span className="tnum" style={{ textAlign: "right", color: "var(--color-neutral-500)" }}>
        +{points(cost)}
      </span>
    </div>
  )
}
