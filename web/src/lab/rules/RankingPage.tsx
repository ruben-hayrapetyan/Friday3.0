// Priorities: put what matters in order. Deadlines stay on top. Everything above the line is protected: Friday
// never gives up an hour of it for anything below (the line is the engine's wellbeing/preferences stage boundary).
// Within each side, each place up doubles how much a rule counts.

import { useEffect, useMemo, useState } from "react"
import { Icon } from "@/components/fr/controls"
import { type Concern, rankRules, type RuleSpec, stageOf } from "./model"
import { ApplyRules, compare, Outcome, Page, useBaseline, usePreview, useRuleSpecs } from "./shared"

const LINE = "—line—"
const CONCERNS: Concern[] = [
  { id: "sleep", title: "Sleep and winding down", rules: ["late_night"] },
  { id: "evenings", title: "Free weekday evenings", rules: ["weekday_evenings"] },
  { id: "weekends", title: "Free weekends", rules: ["weekends"] },
  { id: "stretch", title: "No marathon sittings", rules: ["deep_run"] },
  { id: "light", title: "Days that aren’t too full", rules: ["daily_load"] },
  { id: "even", title: "Work spread evenly before it’s due", rules: ["even_load"] },
  { id: "early", title: "Finishing a day early", rules: ["finish_early"] },
  { id: "long", title: "Fewer, longer sessions", rules: ["chunk_cost"] },
  { id: "course", title: "One course at a time", rules: ["same_course"] },
  { id: "steady", title: "A plan that doesn’t keep changing", rules: ["minimize_changes"] },
]

/** Today's order: protected concerns first, then by weight, with the line between them. */
function startingOrder(specs: RuleSpec[], concerns: Concern[]): string[] {
  const rule = (c: Concern) => specs.find((r) => r.name === c.rules[0])
  const stage = (c: Concern) => {
    const r = rule(c)
    return r ? stageOf(r) : "preferences"
  }
  const byWeight = (a: Concern, b: Concern) => (rule(b)?.weight ?? 0) - (rule(a)?.weight ?? 0)
  const above = concerns.filter((c) => stage(c) === "wellbeing").sort(byWeight)
  const below = concerns.filter((c) => stage(c) !== "wellbeing").sort(byWeight)
  return [...above.map((c) => c.id), LINE, ...below.map((c) => c.id)]
}

export function RankingPage() {
  const specs = useRuleSpecs()
  const specsKey = JSON.stringify(specs)
  const concerns = useMemo(() => CONCERNS.filter((c) => specs?.some((r) => r.name === c.rules[0] && r.enabled !== false)), [specs])
  const start = useMemo(() => (specs ? startingOrder(specs, concerns) : []), [specs, concerns])
  const [order, setOrder] = useState<string[] | null>(null)
  const [dragging, setDragging] = useState<string | null>(null)
  // Saved rules (yours, or just applied) are today's order again.
  useEffect(() => setOrder(null), [specsKey])
  const shown = order ?? start
  const line = shown.indexOf(LINE)
  const ids = shown.filter((x) => x !== LINE)
  const draft = specs ? rankRules(specs, start.filter((x) => x !== LINE), ids, line, concerns) : undefined
  const changed = !!draft && JSON.stringify(draft) !== JSON.stringify(specs)
  const preview = usePreview(changed ? { rules: draft } : null, 600)
  const { saved, fresh, baseline } = useBaseline()
  const comparison = changed && preview.changes && saved && fresh && baseline ? compare(saved, fresh, baseline, preview.changes) : undefined
  const move = (id: string, to: number) => {
    const rest = shown.filter((x) => x !== id)
    rest.splice(Math.max(0, Math.min(rest.length, to)), 0, id)
    setOrder(rest)
  }
  const title = (id: string) => concerns.find((c) => c.id === id)?.title ?? id
  return (
    <Page
      wide
      title="Priorities"
      idea="Drag what matters into order. Deadlines always come first. The line splits what Friday protects from what it merely prefers: nothing below the line is ever bought with time from above it. Each place you move something up doubles how much it counts; each place down halves it. Friday shows the week this order makes before you save it."
    >
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,460px) minmax(0,1fr)", gap: 32, alignItems: "start" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <Row label="Deadlines" locked />
          {shown.map((id, i) =>
            id === LINE ? (
              <div
                key={id}
                draggable
                onDragStart={() => setDragging(id)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => dragging && move(dragging, i)}
                style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 0", cursor: "grab", color: "var(--color-accent-300)" }}
              >
                <span style={{ flex: 1, borderTop: "2px dashed var(--color-accent-300)" }} />
                <span className="fr-kicker" style={{ color: "inherit" }}>
                  Protected above · preferred below
                </span>
                <Arrows onUp={() => move(id, i - 1)} onDown={() => move(id, i + 1)} />
              </div>
            ) : (
              <div key={id} draggable onDragStart={() => setDragging(id)} onDragOver={(e) => e.preventDefault()} onDrop={() => dragging && move(dragging, i)}>
                <Row label={title(id)} rank={i < line ? i + 2 : i + 1} onUp={() => move(id, i - 1)} onDown={() => move(id, i + 1)} protectedRow={i < line} />
              </div>
            ),
          )}
          <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
            {draft && specs && <ApplyRules rules={draft} current={specs} />}
            <button className="btn btn-ghost" disabled={!changed} onClick={() => setOrder(null)}>
              Reset
            </button>
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 16, position: "sticky", top: 0 }}>
          <span className="fr-kicker">What this order means</span>
          <Meaning ids={ids} line={line} start={start} title={title} />
          <span className="fr-kicker">What it does to the next two weeks</span>
          {changed ? <Outcome comparison={comparison} busy={preview.busy} error={preview.error} /> : <span style={{ color: "var(--color-neutral-500)" }}>This is today’s order. Move something to see the difference.</span>}
        </div>
      </div>
    </Page>
  )
}

function Meaning({ ids, line, start, title }: { ids: string[]; line: number; start: string[]; title: (id: string) => string }) {
  const above = ids.slice(0, line)
  const below = ids.slice(line)
  const startIds = start.filter((x) => x !== LINE)
  const wasAbove = new Set(start.slice(0, start.indexOf(LINE)))
  const out: string[] = []
  if (above.length && below.length) out.push(`Friday gives up all of “${title(below[0])}” and everything under it before any “${title(above[above.length - 1])}”.`)
  ids.forEach((id, i) => {
    const places = startIds.indexOf(id) - i
    const crossed = wasAbove.has(id) !== i < line ? (i < line ? ", and is now protected" : ", and is no longer protected") : ""
    if (places || crossed) out.push(`“${title(id)}” counts ${places >= 0 ? 2 ** places : `1/${2 ** -places}`}× what it did${crossed}.`)
  })
  out.push("Nothing here can make hard work late: deadlines sit above everything.")
  return (
    <ul style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 6, color: "var(--color-neutral-300)" }}>
      {out.map((s) => (
        <li key={s}>{s}</li>
      ))}
    </ul>
  )
}

function Row({ label, rank, locked, protectedRow, onUp, onDown }: { label: string; rank?: number; locked?: boolean; protectedRow?: boolean; onUp?: () => void; onDown?: () => void }) {
  return (
    <div className="fr-well" style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 12px", cursor: locked ? "default" : "grab" }}>
      <span className="tnum fr-kicker" style={{ width: 18 }}>
        {locked ? 1 : rank}
      </span>
      <Icon name={locked ? "lock-simple" : protectedRow ? "shield-check" : "dots-six-vertical"} size={16} style={{ color: "var(--color-neutral-500)" }} />
      <span style={{ flex: 1 }}>{label}</span>
      {locked ? <span className="fr-tag accent">Always first</span> : <Arrows onUp={onUp} onDown={onDown} />}
    </div>
  )
}

function Arrows({ onUp, onDown }: { onUp?: () => void; onDown?: () => void }) {
  return (
    <span style={{ display: "flex", gap: 2 }}>
      <button className="btn btn-icon btn-ghost" onClick={onUp} aria-label="Move up" style={{ width: 26, height: 26 }}>
        <Icon name="caret-up" />
      </button>
      <button className="btn btn-icon btn-ghost" onClick={onDown} aria-label="Move down" style={{ width: 26, height: 26 }}>
        <Icon name="caret-down" />
      </button>
    </span>
  )
}
