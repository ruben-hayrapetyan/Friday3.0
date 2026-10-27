// What Friday learned (v22 Insights): the suggestions waiting for a yes, each a card with why, Approve or Not now and,
// once answered, what you chose with Undo; then how far each learner has got. Suggestions are a new set of weights
// (what would matter more and what less, the biggest change first, 27 Oct: one sentence quoting nineteen rules said
// neither which mattered nor how much), a proposed rule, keeping a "never" hard, learned lengths, the hours your plans
// tend to slip, and a kind you keep doing before another that's planned first.

import { useQuery, useQueryClient } from "@tanstack/react-query"
import { type ReactNode, useState } from "react"
import { NavLink } from "react-router"
import { query, type Schemas } from "@/api/client"
import { Icon } from "@/components/fr/controls"
import { useToast } from "@/components/Toasts"
import { useMeals, useSleep } from "@/hooks/queries"
import { undoAll, useCommand } from "@/hooks/useCommand"
import { dur } from "@/lib/format"
import { ampm } from "@/lib/time"
import { type Change, sides, times, type Weighed } from "./shapes"

type Ran = Promise<{ command_id: number | null } | undefined>

interface Suggestion {
  key: string
  icon: string
  title: string
  why: string
  body?: ReactNode
  yes: () => Ran
  no: () => Ran
}

const many = (n: number, one: string) => `${n} ${one}${n === 1 ? "" : "s"}`

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
  // A rule in its own words (the Rules page's sentence); one no longer there, by its name tidied.
  const said = (rule: string) => rules?.find((r) => r.name === rule)?.sentence ?? rule.replace(/^you:/, "").replaceAll(/[-_]/g, " ")
  const suggested = learning?.suggested as { version: number; changes: Change[] } | null | undefined
  if (suggested) {
    const { drags = 0, comparisons = 0 } = learning ?? {}
    const from = [drags ? many(drags, "block") + " you moved" : "", comparisons ? many(comparisons, "day") + " you compared" : ""].filter(Boolean).join(" and ")
    items.push({
      key: `profile${suggested.version}`,
      icon: "sliders-horizontal",
      title: "Weigh your rules the way you plan",
      why: from ? `From ${from}. Approving changes how much each rule counts when Friday plans.` : "From how you've planned.",
      body: <Weights changes={suggested.changes ?? []} said={said} />,
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
  const durations = learning?.durations as { in_use: boolean; n: number; better: boolean | null; error: number; error_before: number } | null | undefined
  if (durations?.better && !durations.in_use) {
    items.push({ key: "durations", icon: "timer", title: "Use the lengths Friday learned", why: `They're typically ${Math.round(durations.error * 100)}% off, against ${Math.round(durations.error_before * 100)}% for the estimates now.`, yes: () => use({ module: "durations", use: true }), no: async () => ({ command_id: null }) })
  }
  const energy = learning?.energy as { in_use: boolean; observations: number; worst: { day: string; time: string }[] } | null | undefined
  if (energy?.worst.length && !energy.in_use) {
    items.push({ key: "energy", icon: "battery-low", title: "Plan less deep work when it tends to slip", why: `Planned work often slips around ${energy.worst.slice(0, 3).map((w) => `${w.day} ${ampm(w.time)}`).join(", ")}.`, yes: () => use({ module: "energy", use: true }), no: async () => ({ command_id: null }) })
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
  const act = async (s: Suggestion, yes: boolean) => {
    const out = await (yes ? s.yes() : s.no())
    if (out) setClosed({ ...closed, [s.key]: { state: yes ? "Approved" : "Not now", id: out.command_id } })
  }
  const undo = async (key: string, id: number) => (await undoAll(client, toast, [id]), setClosed(({ [key]: _, ...rest }) => rest))
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <span className="fr-eyebrow">Waiting for a yes</span>
        {items.map((s) => (
          <Card key={s.key} s={s} closed={closed[s.key]} onAct={(yes) => act(s, yes)} onUndo={(id) => undo(s.key, id)} />
        ))}
        {!items.length && <span className="fr-kicker">Nothing to approve. Friday learns from your reviews and the blocks you move.</span>}
      </div>
      <SoFar learning={learning} />
    </div>
  )
}

function Card({ s, closed, onAct, onUndo }: { s: Suggestion; closed?: { state: string; id: number | null }; onAct: (yes: boolean) => void; onUndo: (id: number) => void }) {
  return (
    <div className="fr-well" style={{ display: "flex", flexDirection: "column", gap: 14, padding: "14px 16px", opacity: closed ? 0.6 : 1 }}>
      <div style={{ display: "flex", gap: 12, alignItems: "flex-start", flexWrap: "wrap" }}>
        <span style={{ flex: "none", width: 28, height: 28, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", background: "var(--color-bg)" }}>
          <Icon name={s.icon} size={15} style={{ color: "var(--color-accent-300)" }} />
        </span>
        <span style={{ flex: "1 1 260px", display: "flex", flexDirection: "column", gap: 3, minWidth: 0 }}>
          <span style={{ fontWeight: 500 }}>{s.title}</span>
          <span className="fr-kicker" style={{ textWrap: "pretty" }}>
            {s.why}
          </span>
        </span>
        {closed ? (
          <span style={{ display: "flex", gap: 10, alignItems: "center", fontSize: 12, color: "var(--color-neutral-400)" }}>
            {closed.state}
            {closed.id !== null && (
              <button className="fr-link" onClick={() => onUndo(closed.id as number)}>
                Undo
              </button>
            )}
          </span>
        ) : (
          <span style={{ display: "flex", gap: 6, marginLeft: "auto" }}>
            <button className="btn btn-ghost" onClick={() => onAct(false)}>
              Not now
            </button>
            <button className="btn btn-primary" onClick={() => onAct(true)}>
              Approve
            </button>
          </span>
        )}
      </div>
      {s.body}
    </div>
  )
}

const SHOWN = 4 // each side's biggest changes; the rest on "Show all"

/** What would count more and what less, each rule on its line with how much, the biggest first; big changes marked. */
function Weights({ changes, said }: { changes: Change[]; said: (rule: string) => string }) {
  const [all, setAll] = useState(false)
  const { more, less } = sides(changes)
  const big = [...more, ...less].filter((w) => w.big)
  const hidden = Math.max(0, more.length - SHOWN) + Math.max(0, less.length - SHOWN)
  const side = (title: string, list: Weighed[], icon: string) =>
    list.length > 0 && (
      <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
        <span className="fr-eyebrow" style={{ display: "flex", alignItems: "center", gap: 6, paddingBottom: 4 }}>
          <Icon name={icon} size={11} />
          {title} · {list.length}
        </span>
        {(all ? list : list.slice(0, SHOWN)).map((w) => (
          <div key={w.rule} title={`${said(w.rule)}: ${w.word} (${times(w.factor)})`} style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", gap: 10, alignItems: "baseline", padding: "4px 0", fontSize: 12.5 }}>
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{said(w.rule)}</span>
            <span className="tnum" style={{ fontSize: 11.5, whiteSpace: "nowrap", color: w.big ? "var(--fr-warn)" : "var(--color-neutral-400)" }}>
              {w.big && <Icon name="warning" size={11} style={{ marginRight: 4 }} />}
              {w.word} <span style={{ color: "var(--color-neutral-600)" }}>{times(w.factor)}</span>
            </span>
          </div>
        ))}
      </div>
    )
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, paddingLeft: 40 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "10px 28px" }}>
        {side("Counts more", more, "arrow-up")}
        {side("Counts less", less, "arrow-down")}
      </div>
      <div style={{ display: "flex", gap: 12, alignItems: "baseline", flexWrap: "wrap" }}>
        {big.length > 0 && (
          <span className="fr-kicker" style={{ color: "var(--fr-warn)", textWrap: "pretty", flex: "1 1 260px" }}>
            {big.length === 1 ? "One big change" : `${big.length} big changes`}: {big.map((w) => `“${said(w.rule)}” would count ${w.word}`).join("; ")}. Approve only if that's how you want to plan.
          </span>
        )}
        {hidden > 0 && (
          <button className="fr-link" onClick={() => setAll(!all)} style={{ fontSize: 12, marginLeft: "auto" }}>
            {all ? "Show fewer" : `Show all ${more.length + less.length}`}
          </button>
        )}
      </div>
    </div>
  )
}

/** How far each learner has got: what it has seen, what it waits for, and what it learned once it has. */
function SoFar({ learning }: { learning?: Schemas["LearningOut"] }) {
  const sleep = useSleep().data
  const meals = useMeals().data
  const progress = learning?.progress ?? {}
  const durations = learning?.durations as { in_use: boolean; n: number } | null | undefined
  const energy = learning?.energy as { observations: number; worst: unknown[] } | null | undefined
  const mealDays = (meals?.days ?? []).filter((d) => (d.meals ?? []).length > 0).length
  const nights = sleep?.recorded_nights ?? 0
  const needNights = sleep?.min_nights ?? 4
  const learnedMeals = (meals?.learned ?? []).filter((m) => m.usual_start)
  const rows: { icon: string; name: string; have?: number; need?: number; text: string; to?: string }[] = [
    {
      icon: "timer",
      name: "How long things take",
      ...(durations ? {} : { have: progress.lengths?.have ?? 0, need: progress.lengths?.need ?? 5 }),
      text: durations
        ? `${durations.in_use ? "In use" : "Learned"} from ${many(durations.n, "finished thing")} you timed`
        : `${progress.lengths?.have ?? 0} of ${progress.lengths?.need ?? 5} finished things timed. Use Start on a task to time it.`,
    },
    {
      icon: "sort-ascending",
      name: "The order you work in",
      ...(learning?.order ? {} : { have: progress.order?.have ?? 0, need: progress.order?.need ?? 4 }),
      text: learning?.order
        ? `Suggests ${learning.order.first} before ${learning.order.then}`
        : `${progress.order?.have ?? 0} of ${progress.order?.need ?? 4} times you started one kind of work before another planned first`,
    },
    {
      icon: "battery-medium",
      name: "When planned work slips",
      text: energy?.observations ? `${many(energy.observations, "planned block")} watched${energy.worst.length ? ": a pattern to suggest" : ", no pattern yet"}` : "Watches whether planned work happens; nothing seen yet",
    },
    {
      icon: "moon",
      name: "Sleep",
      ...(sleep?.on && nights < needNights ? { have: nights, need: needNights } : {}),
      text: !sleep?.on
        ? "Off: turn it on to learn your bedtime and wake time"
        : nights < needNights
          ? `${nights} of ${needNights} nights recorded`
          : `Learned from ${many(nights, "night")}${sleep.changes?.length ? ": suggests a new time" : ", in step with your settings"}`,
      to: "/body",
    },
    {
      icon: "fork-knife",
      name: "Meals",
      ...(meals?.on && !learnedMeals.length ? { have: mealDays, need: meals.min_days ?? 4 } : {}),
      text: !meals?.on
        ? "Off: turn it on to learn when you eat"
        : learnedMeals.length
          ? learnedMeals
              .slice(0, 3)
              .map((m) => `${m.kind[0].toUpperCase()}${m.kind.slice(1)} about ${ampm(m.usual_start as string)}${m.usual_min ? `, ${dur(m.usual_min)}` : ""}${m.group === "weekends" ? " at weekends" : ""}`)
              .join(" · ")
          : `${mealDays} of ${meals.min_days ?? 4} days recorded`,
      to: "/body?tab=meals",
    },
    {
      icon: "sliders-horizontal",
      name: "What you prefer",
      text: `${many(learning?.drags ?? 0, "block")} you moved, ${many(learning?.comparisons ?? 0, "day")} you compared${learning?.version ? `; in use since version ${learning.version}` : ""}`,
    },
  ]
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <span className="fr-eyebrow" style={{ paddingBottom: 6 }}>
        So far
      </span>
      {rows.map((r) => (
        <div key={r.name} className="fr-row" style={{ display: "grid", gridTemplateColumns: "20px minmax(110px, 190px) minmax(0,1fr) auto", gap: "4px 12px", alignItems: "center", padding: "8px 0", fontSize: 12.5 }}>
          <Icon name={r.icon} size={14} style={{ color: "var(--color-neutral-400)" }} />
          <span style={{ fontWeight: 500 }}>{r.name}</span>
          <span style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0, flexWrap: "wrap" }}>
            {r.need !== undefined && <Meter have={r.have ?? 0} need={r.need} />}
            <span style={{ color: "var(--color-neutral-400)", textWrap: "pretty", minWidth: 0 }}>{r.text}</span>
          </span>
          {r.to ? (
            <NavLink to={r.to} className="fr-link" style={{ fontSize: 12, whiteSpace: "nowrap" }}>
              Open
            </NavLink>
          ) : (
            <span />
          )}
        </div>
      ))}
    </div>
  )
}

/** A few dots, one for each thing a learner waits for, filled as they come. */
function Meter({ have, need }: { have: number; need: number }) {
  const dots = Math.min(need, 8)
  const filled = Math.min(dots, Math.round((Math.min(have, need) / need) * dots))
  return (
    <span role="img" aria-label={`${have} of ${need}`} style={{ display: "inline-flex", gap: 3, flex: "none" }}>
      {Array.from({ length: dots }, (_, n) => (
        <span key={n} style={{ width: 7, height: 7, borderRadius: 2, background: n < filled ? "var(--color-accent)" : "color-mix(in srgb, var(--color-text) 12%, transparent)" }} />
      ))}
    </span>
  )
}
