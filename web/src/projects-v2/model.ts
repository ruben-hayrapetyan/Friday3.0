// The new Projects & exams page's data, as plain functions (tested on their own in model.test.ts): every deadline as
// one kind of row, projects and exams alike, placed on six weeks across; ongoing projects with their
// weeks; and the words the shelves use.

import type { Block, Item, Schemas } from "@/api/client"
import { dur } from "@/lib/format"
import { addDays, toMin } from "@/lib/time"

export type Project = Schemas["ProjectOut"]
export type Exam = Schemas["ExamOut"]
export type Ongoing = Schemas["OngoingOut"]
export type Finished = Schemas["FinishedProject"]

export const WEEKS = 6

export interface Step {
  id: number
  title: string
  done: boolean
  minutes: number
  due: string | null // its own due, if it has one: a milestone on its project's bar
}

/** One row of the deadline shelf: a project with its steps, or an exam with its prep. Assignments stay on To-do, however
 * big (16 Nov: "it classifies most of my open assignments under projects which is NOT supposed to be the case"). */
export interface Row {
  kind: "project" | "exam"
  id: number
  title: string
  area: string | null
  preset: string | null
  due: string | null // a project's or to-do's due; an exam's start
  hard: boolean
  doneMin: number
  totalMin: number
  steps: Step[] // a project's steps, or an exam's prep, in order
  status: "on_track" | "late" | "unplanned" | "done" | "ready" | "no_prep"
  next: string | null // its next planned session's start
}

export const STATUS: Record<Row["status"], string> = {
  on_track: "On track",
  late: "Behind",
  unplanned: "Not planned yet",
  done: "Done",
  ready: "Ready",
  no_prep: "No prep yet",
}

/** The soonest planned start, from now on, among these items' blocks. */
export function nextOf(blocks: Pick<Block, "item_id" | "start" | "end">[], ids: number[], now: string): string | null {
  const from = toMin(now)
  return blocks.filter((b) => ids.includes(b.item_id) && toMin(b.end) > from).map((b) => b.start).sort()[0] ?? null
}

const stepOf = (i: Item): Step => ({ id: i.id, title: i.title, done: i.status === "done", minutes: i.duration_min ?? i.remaining_min ?? 0, due: i.due ?? null })

/** Every deadline as a row, soonest first: projects, exams with their prep, and big to-dos that aren't in either. */
export function deadlineRows(projects: Project[], exams: Exam[], blocks: Pick<Block, "item_id" | "start" | "end">[], now: string): Row[] {
  const rows: Row[] = [
    ...projects.map((p): Row => {
      const steps = p.children.filter((c) => c.parent_id === p.item.id)
      return {
        kind: "project",
        id: p.item.id,
        title: p.item.title,
        area: p.item.area ?? null,
        preset: p.item.preset ?? null,
        due: p.item.due ?? null,
        hard: p.item.firmness === "hard",
        doneMin: p.done_min,
        totalMin: p.done_min + p.remaining_min,
        steps: steps.map(stepOf),
        status: p.status,
        next: nextOf(blocks, [p.item.id, ...p.children.map((c) => c.id)], now),
      }
    }),
    ...exams.map((e): Row => ({
      kind: "exam",
      id: e.item.id,
      title: e.item.title,
      area: e.item.area ?? null,
      preset: e.item.preset ?? null,
      due: e.item.start ?? null,
      hard: true,
      doneMin: e.done_min,
      totalMin: e.done_min + e.remaining_min,
      steps: e.prep.map((x) => stepOf(x.item)),
      status: e.status,
      next: nextOf(blocks, e.prep.map((x) => x.item.id), now),
    })),
  ]
  return rows.sort((a, b) => (a.due ?? "9").localeCompare(b.due ?? "9") || a.id - b.id)
}

/** How far along: done against the whole, 0 to 1. */
export const share = (r: Pick<Row, "doneMin" | "totalMin">) => (r.totalMin ? Math.min(1, r.doneMin / r.totalMin) : 0)

/** How much of the bar to fill: how far along, and at least to the diamond of every step done, the diamonds standing at
 * their dues on the weeks (20 Nov, a user's notes: "if you complete one of the due dates, the progress bar should fill
 * until the diamond regardless of how long it took"); never past the diamond of a step not done yet (27 Nov, a user's
 * notes: the bar had passed the diamond of Final Presentations, due Mon 30, before the 30th: how far along is the
 * work's share, the diamonds are on the weeks, and the share ran past one). The bar runs from today to the due; 0 to 1
 * of it. */
export function reached(r: Pick<Row, "doneMin" | "totalMin" | "steps" | "due">, today: string): number {
  const end = r.due ? at(r.due, today) : 0
  const on = (m: Step) => at(m.due ?? "", today) / end
  const all = end > 0 ? milestones(r) : []
  const open = all.filter((m) => !m.done).map(on).filter((x) => x > 0) // one overdue sits at the bar's start: no cap
  const work = Math.min(share(r), ...open)
  return Math.min(1, Math.max(work, ...all.filter((m) => m.done).map(on)))
}
export const left = (r: Pick<Row, "doneMin" | "totalMin">) => dur(Math.max(0, r.totalMin - r.doneMin)) || "0m"

/** Where a moment sits on the six weeks from today's start, as a percent (0 to 100, clamped). */
export function at(moment: string, today: string, weeks = WEEKS): number {
  const span = weeks * 7 * 1440
  return Math.max(0, Math.min(100, ((toMin(moment) - toMin(`${today}T00:00`)) / span) * 100))
}

/** The six weeks' first days, today's first. */
export const weekStarts = (today: string, weeks = WEEKS) => Array.from({ length: weeks }, (_, i) => addDays(today, i * 7))

/** Days since an ongoing project was last worked on; null when not in eight weeks. */
export function sinceTouched(touched: string[], today: string): number | null {
  const last = [...touched].sort().at(-1)
  return last ? Math.round((toMin(`${today}T00:00`) - toMin(`${last}T00:00`)) / 1440) : null
}

/** Whether a rhythm has fallen behind: longer since it was touched than a week's spacing (7 ÷ days a week). */
export function behindRhythm(o: Pick<Ongoing, "touched" | "rhythm_days">, today: string): boolean {
  if (!o.rhythm_days) return false
  const since = sinceTouched(o.touched, today)
  return since === null || since > Math.ceil(7 / o.rhythm_days)
}

/** "Touched today", "Last touched 3 days ago", "Not touched in eight weeks", "Not started yet" (no week before this
 * one), or how long it's paused. */
export function touchedWords(o: Pick<Ongoing, "touched" | "active" | "paused_until" | "past">, today: string, day: (d: string) => string): string {
  if (o.paused_until) return `Paused until ${day(o.paused_until)}`
  if (!o.active) return "Paused"
  const since = sinceTouched(o.touched, today)
  if (since === null) return o.past.length ? "Not touched in eight weeks" : "Not started yet"
  if (since === 0) return "Touched today"
  return `Last touched ${since === 1 ? "yesterday" : `${since} days ago`}`
}

/** The last `weeks` weeks of days, oldest first, starting on a Monday: the ongoing card's grid of days. */
export function gridDays(today: string, weeks = 8): string[] {
  const dow = (new Date(`${today}T00:00Z`).getUTCDay() + 6) % 7 // Monday 0
  const start = addDays(today, -(weeks - 1) * 7 - dow)
  return Array.from({ length: weeks * 7 }, (_, i) => addDays(start, i))
}

/** What a finished project took against its plan, in words: "20% longer", "15% quicker", "about as planned". */
export function againstPlan(f: Pick<Finished, "estimate_min" | "actual_min">): { words: string; tone: "warn" | "good" | "quiet" } {
  if (!f.estimate_min) return { words: "", tone: "quiet" }
  const ratio = f.actual_min / f.estimate_min
  if (ratio > 1.15) return { words: `${Math.round((ratio - 1) * 100)}% longer`, tone: "warn" }
  if (ratio < 0.85) return { words: `${Math.round((1 - ratio) * 100)}% quicker`, tone: "good" }
  return { words: "about as planned", tone: "quiet" }
}

/** What carry-over means, said with its value. */
export const CARRIES = [
  { value: 0, label: "None", desc: "each week starts fresh" },
  { value: 0.5, label: "Half", desc: "half of what's missed comes into next week" },
  { value: 1, label: "All", desc: "everything missed comes into next week" },
] as const

export const PRIORITIES = ["Lowest", "Low", "Normal", "High", "Highest"]

/** Hours as Friday writes every length: "3h", "2h 30m". */
export const hoursText = (h: number) => dur(Math.round(h * 60))

/** "N days a week, about 1 h each", or whenever it fits, from its hours and rhythm. */
export function rhythmWords(hours: number, days: number): string {
  if (!days) return "Whenever it fits"
  return `${days} ${days === 1 ? "day" : "days"} a week, about ${dur(Math.round((hours * 60) / days))} each`
}

/** A project's milestones: its steps with a due of their own, by the project's, soonest first (27 Nov, a user's notes:
 * three diamonds for seven steps, a step due with the project, the Rubric, had none). */
export const milestones = (r: Pick<Row, "steps" | "due">) => r.steps.filter((s) => s.due && (!r.due || s.due <= r.due)).sort((a, b) => (a.due ?? "").localeCompare(b.due ?? ""))

/** The bar's diamonds: one a day, for the steps due that day ("Final Presentations and research"), done when all are,
 * as two diamonds on one spot read as one step (27 Nov). */
export function diamonds(r: Pick<Row, "steps" | "due">): { key: string; due: string; titles: string[]; done: boolean }[] {
  const out: { key: string; due: string; titles: string[]; done: boolean }[] = []
  for (const m of milestones(r)) {
    const day = (m.due ?? "").slice(0, 10)
    const same = out.find((d) => d.due.slice(0, 10) === day)
    if (same) {
      same.titles.push(m.title)
      same.done &&= m.done
    } else out.push({ key: String(m.id), due: m.due ?? "", titles: [m.title], done: m.done })
  }
  return out
}


/** Where a project aims to be done: its due less the days early it aims for (a local time, as dues are). */
export function aimFor(due: string, days: number): string {
  return addDays(due.slice(0, 10), -days) + due.slice(10)
}

export const EARLY_DAYS = [0, 1, 2, 3, 5, 7]

/** A project's pace through its work, and what each does with its hours. */
export const PACES = [
  { value: "kind", label: "Not set", desc: "about the same each week up to its due, as Friday paces any project" },
  { value: "front", label: "Front-load it", desc: "most of it in the first weeks, done well before its due" },
  { value: "linear", label: "Evenly", desc: "about the same each week, up to its due" },
  { value: "back", label: "Toward the end", desc: "a little now, most of it in the last weeks" },
] as const
