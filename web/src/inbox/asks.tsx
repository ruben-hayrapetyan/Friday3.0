// Friday's questions to you, in the Inbox (PROGRESS.md C75, 9 Nov: "the weight changing questions that now pop up in
// insights should instead go to inbox. in fact anything that needs the user's attention (like questions friday asks
// to the user) should go into inbox instead of insights"). Each is a message: what Friday learned and wants to use (a
// new weighing of your rules, a rule, keeping a rule hard, learned lengths, the hours work slips, one kind before
// another), which of two days you'd rather have, your meals' times and lengths, and your real bedtimes. "Not now" sets
// one aside with what it was based on, and it's asked again once Friday has more to go on (`ask_later`). Insights
// still shows what was learned, with a link here.

import { useQuery } from "@tanstack/react-query"
import { type ReactNode, useMemo, useRef } from "react"
import { query, type Schemas } from "@/api/client"
import { useMeals, useSleep } from "@/hooks/queries"
import { useCommand } from "@/hooks/useCommand"
import { dur } from "@/lib/format"
import { ampm } from "@/lib/time"
import { daysSaid } from "@/settings/SleepTracking"
import type { Change } from "@/insights/shapes"
import { Weights } from "@/insights/Weights"

type Ran = Promise<unknown>

export interface Ask {
  key: string // the question, the same each time it's asked
  evidence: string // what it's based on: "Not now" holds while this stays the same
  icon: string
  kicker: string // what kind of question, above its title
  title: string
  why: string
  body?: ReactNode
  yes?: { label: string; run: () => Ran } // none: the body answers it (the two days)
  no?: { label: string; run: () => Ran } // none: "Not now", asked again with more evidence
  learned?: boolean // one of what Insights' "What Friday learned" counted
}

const many = (n: number, one: string) => `${n} ${one}${n === 1 ? "" : "s"}`
const named = (kind: string) => kind[0].toUpperCase() + kind.slice(1)
type Meal = "breakfast" | "lunch" | "dinner"

/** The questions waiting, those you set aside left out until what they're based on changes. */
export function useAsks(): Ask[] {
  const all = useAllAsks()
  const later = useQuery({ queryKey: ["asks_later"], queryFn: () => query("asks_later") }).data?.later
  return useMemo(() => waiting(all, later ?? {}), [all, later]) // the same list until something changes: the Inbox keys on it
}

/** What's still to ask: one set aside comes back when its evidence changes. */
export function waiting(asks: Ask[], later: Record<string, string>): Ask[] {
  return asks.filter((a) => later[a.key] !== a.evidence)
}

function useAllAsks(): Ask[] {
  const learning = useQuery({ queryKey: ["learning"], queryFn: () => query("learning") }).data
  const questions = useQuery({ queryKey: ["questions"], queryFn: () => query("questions") }).data
  const rules = useQuery({ queryKey: ["rules"], queryFn: () => query("rules") }).data
  const meals = useMeals().data
  const sleep = useSleep().data
  const apply = useCommand("learn_apply", { label: (o) => o.result.message ?? "Approved" })
  const reject = useCommand("learn_reject", { label: (o) => o.result.message ?? "Kept as it was" })
  const answer = useCommand("proposal_answer", { label: (o) => o.result.message ?? "Thanks" })
  const use = useCommand("learn_module", { label: (o) => o.result.message ?? "Saved" })
  const order = useCommand("learn_order", { label: (o) => o.result.message ?? "Saved" })
  const mealLength = useCommand("meal_use_length", { label: (o) => o.result.message ?? "Saved" })
  const mealTime = useCommand("meal_use_time", { label: (o) => o.result.message ?? "Saved" })
  const mealPlan = useCommand("meal_plan", { label: (o) => o.result.message ?? "Saved" })
  const setting = useCommand("settings_set", { label: () => "Your bedtimes and wake times are updated" })
  // The commands are new functions each render (their labels are): the questions hold the latest through a ref, so
  // the list stays the same object until what's asked changes (else the Inbox, keyed on it, renders forever).
  const latest = useRef({ apply, reject, answer, use, order, mealLength, mealTime, mealPlan, setting })
  latest.current = { apply, reject, answer, use, order, mealLength, mealTime, mealPlan, setting }
  return useMemo(() => {
  const { apply, reject, answer, use, order, mealLength, mealTime, mealPlan, setting } = {
    apply: (i: Parameters<typeof latest.current.apply>[0]) => latest.current.apply(i),
    reject: (i: Parameters<typeof latest.current.reject>[0]) => latest.current.reject(i),
    answer: (i: Parameters<typeof latest.current.answer>[0]) => latest.current.answer(i),
    use: (i: Parameters<typeof latest.current.use>[0]) => latest.current.use(i),
    order: (i: Parameters<typeof latest.current.order>[0]) => latest.current.order(i),
    mealLength: (i: Parameters<typeof latest.current.mealLength>[0]) => latest.current.mealLength(i),
    mealTime: (i: Parameters<typeof latest.current.mealTime>[0]) => latest.current.mealTime(i),
    mealPlan: (i: Parameters<typeof latest.current.mealPlan>[0]) => latest.current.mealPlan(i),
    setting: (i: Parameters<typeof latest.current.setting>[0]) => latest.current.setting(i),
  }
  const out: Ask[] = []
  // A rule in its own words (the Rules page's sentence); one no longer there, by its name tidied.
  const said = (rule: string) => rules?.find((r) => r.name === rule)?.sentence ?? rule.replace(/^you:/, "").replaceAll(/[-_]/g, " ")
  const learnedKicker = "What Friday learned"

  const suggested = learning?.suggested as { version: number; changes: Change[] } | null | undefined
  if (suggested) {
    const { drags = 0, comparisons = 0 } = learning ?? {}
    const from = [drags ? many(drags, "block") + " you moved" : "", comparisons ? many(comparisons, "day") + " you compared" : ""].filter(Boolean).join(" and ")
    out.push({
      key: "weights",
      evidence: String(suggested.version),
      icon: "sliders-horizontal",
      kicker: learnedKicker,
      title: "Weigh your rules the way you plan",
      why: from ? `From ${from}. Approving changes how much each rule counts when Friday plans.` : "From how you've planned.",
      body: <Weights changes={suggested.changes ?? []} said={said} />,
      yes: { label: "Approve", run: () => apply({ version: suggested.version }) },
      no: { label: "Keep them as they are", run: () => reject({ version: suggested.version }) },
      learned: true,
    })
  }
  if (questions?.proposal) {
    const p = questions.proposal
    out.push({
      key: `rule:${p.name}`,
      evidence: p.name,
      icon: "list-plus",
      kicker: learnedKicker,
      title: p.sentence.replace(" Add that as a rule?", ""),
      why: "You keep moving work away from this. Add it as a rule?",
      yes: { label: "Add the rule", run: () => answer({ kind: "rule", name: p.name, yes: true }) },
      no: { label: "No", run: () => answer({ kind: "rule", name: p.name, yes: false }) },
      learned: true,
    })
  }
  if (questions?.wall) {
    const w = questions.wall
    out.push({
      key: `wall:${w.name}`,
      evidence: w.name,
      icon: "wall",
      kicker: learnedKicker,
      title: w.sentence ?? `Keep ${w.name} as a hard rule?`,
      why: "It gave way to deadlines lately. Keep it hard, or let it bend?",
      yes: { label: "Keep it hard", run: () => answer({ kind: "wall", name: w.name, yes: true }) },
      no: { label: "Let it bend", run: () => answer({ kind: "wall", name: w.name, yes: false }) },
      learned: true,
    })
  }
  const durations = learning?.durations as { in_use: boolean; n: number; better: boolean | null; error: number; error_before: number } | null | undefined
  if (durations?.better && !durations.in_use) {
    out.push({
      key: "durations",
      evidence: String(durations.n),
      icon: "timer",
      kicker: learnedKicker,
      title: "Use the lengths Friday learned",
      why: `From ${many(durations.n, "thing")} you timed. They're typically ${Math.round(durations.error * 100)}% off, against ${Math.round(durations.error_before * 100)}% for the estimates now.`,
      yes: { label: "Use them", run: () => use({ module: "durations", use: true }) },
      learned: true,
    })
  }
  const energy = learning?.energy as { in_use: boolean; observations: number; worst: { day: string; time: string }[] } | null | undefined
  if (energy?.worst.length && !energy.in_use) {
    out.push({
      key: "energy",
      evidence: String(energy.observations),
      icon: "battery-low",
      kicker: learnedKicker,
      title: "Plan less deep work when it tends to slip",
      why: `Planned work often slips around ${energy.worst.slice(0, 3).map((w) => `${w.day} ${ampm(w.time)}`).join(", ")}.`,
      yes: { label: "Plan less then", run: () => use({ module: "energy", use: true }) },
      learned: true,
    })
  }
  const first = learning?.order
  if (first) {
    const plural = (kind: string) => (kind.endsWith("s") ? kind : `${kind}s`)
    out.push({
      key: `order:${first.first}>${first.then}`,
      evidence: `${first.chose}/${first.of}`,
      icon: "sort-ascending",
      kicker: learnedKicker,
      title: `Plan ${plural(first.first)} before ${plural(first.then)}`,
      why: `You started a ${first.first} instead of the ${first.then} planned then ${first.chose} of ${first.of} times.`,
      yes: { label: "Plan them first", run: () => order({ first: first.first, then: first.then, use: true }) },
      no: { label: "No", run: () => order({ first: first.first, then: first.then, use: false }) },
      learned: true,
    })
  }
  const day = questions?.comparisons[0]
  if (day) {
    out.push({
      key: "compare",
      evidence: String(day.id),
      icon: "columns",
      kicker: "Which day you'd rather have",
      title: "Which version of the day looks better?",
      why: "Two ways to plan the same work. One quick pick helps Friday learn what you prefer.",
    })
  }
  if (meals) out.push(...mealAsks(meals, { length: mealLength, time: mealTime, plan: mealPlan }))
  if (sleep?.suggested && sleep.changes?.length) {
    out.push({
      key: "sleep-times",
      evidence: sleep.changes.map((c) => `${c.field}${c.days.join("")}${c.learned}`).join(","),
      icon: "moon",
      kicker: "Your sleep",
      title: "Your real times differ from your schedule",
      why: sleep.changes.map((c) => `${daysSaid(c.days, c.field)}: ${c.field === "bedtime" ? "to bed" : "up"} around ${ampm(c.learned)}, not ${ampm(c.now)}`).join("; ") + ".",
      body: sleep.against?.length ? (
        <span style={{ fontSize: 12, color: "var(--fr-warn)", textWrap: "pretty" }}>{sleep.against.map((a) => `${a}.`).join(" ")} Taking these times leaves a question here: your bedtime or the rule.</span>
      ) : undefined,
      yes: { label: "Use these times", run: () => setting({ key: "sleep", value: sleep.suggested }) },
    })
  }
  return out
  }, [learning, questions, rules, meals, sleep])
}

type MealRun = { length: (i: { kind: Meal }) => Ran; time: (i: { kind: Meal }) => Ran; plan: (i: { kind: Meal; plan: boolean }) => Ran }

/** A meal's learned length, time, or whether to plan it, each a question; none for a meal Friday decides itself. */
export function mealAsks(meals: Schemas["MealsOut"], run: MealRun): Ask[] {
  const decided = new Set(meals.decided ?? [])
  const out: Ask[] = []
  for (const c of meals.changes ?? []) {
    if (decided.has(c.kind)) continue
    const minutes = Math.max(15, Math.round(c.usual_min / 15) * 15)
    out.push({ key: `meal-length:${c.kind}`, evidence: String(c.usual_min), icon: "fork-knife", kicker: "Your meals", title: `${named(c.kind)} takes you about ${dur(c.usual_min)}`, why: `Friday plans ${dur(c.planned_min)}. Plan ${dur(minutes)} from now on?`, yes: { label: `Plan ${dur(minutes)}`, run: () => run.length({ kind: c.kind as Meal }) } })
  }
  for (const t of meals.times ?? []) {
    if (decided.has(t.kind)) continue
    out.push({ key: `meal-time:${t.kind}`, evidence: t.usual_start, icon: "fork-knife", kicker: "Your meals", title: `You usually have ${t.kind} around ${ampm(t.usual_start)}`, why: `It's planned ${ampm(t.start)}–${ampm(t.end)}. Plan it ${ampm(t.new_start)}–${ampm(t.new_end)} instead?`, yes: { label: `Plan ${ampm(t.new_start)}–${ampm(t.new_end)}`, run: () => run.time({ kind: t.kind as Meal }) } })
  }
  for (const p of meals.plans ?? []) {
    if (decided.has(p.kind)) continue
    out.push({
      key: `meal-plan:${p.kind}`,
      evidence: `${p.plan}${p.usual_start ?? ""}`,
      icon: "fork-knife",
      kicker: "Your meals",
      title: p.plan ? `You have ${p.kind} most days, around ${ampm(p.usual_start ?? "08:00")}` : `You usually skip ${p.kind}`,
      why: p.plan ? "Friday doesn't plan it. Plan it from now on?" : "Friday still plans it. Stop planning it?",
      yes: { label: p.plan ? `Plan ${p.kind}` : "Stop planning it", run: () => run.plan({ kind: p.kind as Meal, plan: p.plan }) },
    })
  }
  return out
}
