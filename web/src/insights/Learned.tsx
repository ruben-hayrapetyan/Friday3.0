// What Friday learned (v22 Insights), and how far each learner has got. Its questions (a new weighing of your rules, a
// rule, keeping a "never" hard, learned lengths, the hours your plans slip, one kind before another) are asked in the
// Inbox, where everything waiting for you is (C75, 9 Nov: "anything that needs the user's attention ... should go into
// inbox instead of insights"); here a link says how many wait.

import { useQuery } from "@tanstack/react-query"
import { NavLink } from "react-router"
import { query, type Schemas } from "@/api/client"
import { Icon } from "@/components/fr/controls"
import { useMeals, useSleep } from "@/hooks/queries"
import { useAsks } from "@/inbox/asks"
import { dur } from "@/lib/format"
import { ampm } from "@/lib/time"

const many = (n: number, one: string) => `${n} ${one}${n === 1 ? "" : "s"}`

export function Learned() {
  const learning = useQuery({ queryKey: ["learning"], queryFn: () => query("learning") }).data
  const asks = useAsks().filter((a) => a.learned).length
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <InboxLink n={asks} what="about what Friday learned" none="Nothing to answer. Friday learns from your reviews and the blocks you move." />
      <SoFar learning={learning} />
    </div>
  )
}

/** "2 questions about what Friday learned wait in your Inbox", a link there; `none` when nothing waits. */
export function InboxLink({ n, what, none }: { n: number; what: string; none?: string }) {
  if (!n) return none ? <span className="fr-kicker">{none}</span> : null
  return (
    <NavLink to="/inbox" className="fr-link" style={{ display: "inline-flex", gap: 6, alignItems: "center", alignSelf: "flex-start", fontSize: 13 }}>
      <Icon name="tray" size={14} />
      {n === 1 ? "1 question" : `${n} questions`} {what} {n === 1 ? "waits" : "wait"} in your Inbox
    </NavLink>
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
          : `Learned from ${many(nights, "night")}${sleep.changes?.length ? ": suggests a new time" : ", in step with your settings"}${sleep.usual_nap_min ? `; you nap about ${dur(sleep.usual_nap_min)}` : ""}`,
      to: "/insights?tab=sleep",
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
      to: "/insights?tab=meals",
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
