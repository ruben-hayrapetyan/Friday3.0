// Exams ahead, worked out apart from drawing them: how far off each is, said plainly; how ready you are; where each
// piece of prep stands against the plan; and the one line that sums it up.

import type { Block, Item, Schemas } from "@/api/client"
import { clock, dayLabel, dur, when } from "@/lib/format"
import { toMin } from "@/lib/time"
import { ahead } from "./gantt"

export type Exam = Schemas["ExamOut"]
export type Tone = "good" | "warn" | "due" | "quiet"

/** How far off an exam is: "Now" while it runs, "Today" and "Tomorrow", then days, then weeks. */
export function countdown(start: string, end: string, nowMin: number, today: string): string {
  if (nowMin >= toMin(start) && nowMin < toMin(end)) return "Now"
  return away(start, today)
}

/** How far off a day is: "Today", "Tomorrow", "In 3 days", "In 2 weeks"; "Overdue" once it has passed. */
export function away(local: string, today: string): string {
  const days = Math.round((toMin(local.slice(0, 10)) - toMin(today)) / 1440)
  if (days < 0) return "Overdue"
  if (days === 0) return "Today"
  if (days === 1) return "Tomorrow"
  if (days < 14) return `In ${days} days`
  return `In ${Math.round(days / 7)} weeks`
}

/** Its date and time, written out: "Fri 23 Oct, 7:30–9pm". */
export function sitting(start: string, end: string): string {
  const day = dayLabel(start.slice(0, 10))
  const sameDay = end.slice(0, 10) === start.slice(0, 10)
  return `${day}, ${clock(start)}${sameDay ? `–${clock(end)}` : ""}`
}

/** The share of its prep done, 0–100, by time; null with nothing to prepare. */
export function readiness(exam: Exam): number | null {
  const total = exam.done_min + exam.remaining_min
  if (!exam.prep.length) return null
  if (!total) return exam.status === "ready" ? 100 : 0
  return Math.round((exam.done_min / total) * 100)
}

export interface PrepState {
  item: Item
  state: "done" | "planned" | "late" | "unplanned"
  sessions: Block[] // its planned sessions in the plan ahead, soonest first
  note: string // where it stands, in a few words
  left: number // minutes still to do
}

/** One piece of prep against the plan: done, planned before the exam, planned after it, or not planned at all. */
export function prepState(prep: Exam["prep"][number], blocks: Block[], examStart: string, today: string): PrepState {
  const item = prep.item
  const left = item.remaining_min ?? item.duration_min ?? 0
  const sessions = blocks.filter((b) => b.item_id === item.id).sort((a, b) => a.start.localeCompare(b.start))
  if (item.status === "done") return { item, state: "done", sessions, note: "Done", left: 0 }
  const finish = prep.planned_finish
  if (!finish && !sessions.length) return { item, state: "unplanned", sessions, note: "Not planned yet", left }
  if (finish && finish > examStart) return { item, state: "late", sessions, note: `Planned after the exam, ${when(finish, today)}`, left }
  const first = sessions[0]
  const at = (local: string) => (local.startsWith(today) && local.length > 10 ? `today ${clock(local)}` : when(local, today))
  const note = !first
    ? `Planned by ${when(finish as string, today)}`
    : sessions.length === 1
      ? `${at(first.start)}–${clock(first.end)}`
      : `${sessions.length} sessions, from ${at(first.start)}`
  return { item, state: "planned", sessions, note, left }
}

/** The one line under an exam that says where its prep stands, and how it should read. */
export function summary(exam: Exam, states: PrepState[], today: string): { text: string; tone: Tone } {
  const start = exam.item.start ?? ""
  const unplaced = states.filter((s) => s.state === "unplanned").reduce((sum, s) => sum + s.left, 0)
  switch (exam.status) {
    case "no_prep":
      return { text: "Nothing to prepare yet. Add a study guide or a practice exam.", tone: "quiet" }
    case "ready":
      return { text: "All prep done.", tone: "good" }
    case "late":
      return { text: `Prep runs past the exam: it's planned to finish ${when(exam.planned_finish as string, today)}.`, tone: "due" }
    case "unplanned":
      return { text: `${dur(unplaced || exam.remaining_min)} of prep isn't planned yet.`, tone: "warn" }
    default: {
      const finish = exam.planned_finish as string
      const slack = toMin(start) - toMin(finish.length > 10 ? finish : `${finish}T23:59`)
      return { text: `${dur(exam.remaining_min)} to go, planned to finish ${when(finish, today)}${slack > 0 ? `, ${ahead(slack)} before` : ""}.`, tone: "good" }
    }
  }
}

/** Exams in the next three weeks show in full; the rest of the term waits behind a "later" fold. */
export function soonAndLater(exams: Exam[], today: string, days = 21): [Exam[], Exam[]] {
  const edge = toMin(today) + days * 1440
  const soon = exams.filter((e) => toMin((e.item.start ?? today).slice(0, 10)) < edge)
  return [soon, exams.filter((e) => !soon.includes(e))]
}

/** The course an exam is for: its tag, else a course code in its title ("MATH 2940"), else nothing. */
export function course(item: Item): string | null {
  if (item.area) return item.area
  const code = /\b([A-Z]{2,5})\s?(\d{4})\b/.exec(item.title)
  return code ? `${code[1]} ${code[2]}` : null
}
