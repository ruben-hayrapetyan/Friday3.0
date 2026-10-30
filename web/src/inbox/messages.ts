// The Inbox as one list of messages (29 Oct: "there are too many subcategories of inbox, simplify it and make
// everything just a message the user needs to deal with in inbox"): each thing waiting is a message with a line to
// say what it is, opened beside the list to deal with, and gone once you have. Most pressing first: what only you can
// decide; then the planned time Friday can't account for, yesterday's before today's, and sleep taps you missed; what
// came in from mail, calendars and syllabi; copies of a task; a go-over you started; each repeating calendar event not
// planned around yet (29 Oct: "i don't see any concrete action": go, or leave it out).

import type { Item, Schemas } from "@/api/client"
import { ampm, clock, dayLabel, dur, lateBy, weekday, when } from "@/lib/format"
import { addDays } from "@/lib/time"

type Decision = Schemas["Decision"]
type Gap = Schemas["ReviewGap"]
type SleepAsk = Schemas["SleepAsk"]
type Suggestion = Schemas["SuggestionOut"]
type Group = Schemas["DuplicateGroup"]
type Repeat = Schemas["RepeatFound"]

export type Message =
  | { kind: "decision"; key: string; decision: Decision }
  | { kind: "gap"; key: string; date: string; gap: Gap }
  | { kind: "sleep"; key: string; ask: SleepAsk }
  | { kind: "suggestion"; key: string; s: Suggestion; answered?: boolean }
  | { kind: "copies"; key: string; group: Group; from: Record<number, string> }
  | { kind: "again"; key: string; item: Item; from?: string }
  | { kind: "repeat"; key: string; found: Repeat }

export interface Sources {
  decisions: Decision[]
  days: { date: string; gaps: Gap[]; sleep: SleepAsk[] }[] // yesterday, then today
  suggestions: Suggestion[]
  answered?: Suggestion[] // dealt with here this visit, shown greyed after the rest
  copies: Group[]
  copySources?: Record<number, string>
  again: Item[]
  againSources?: Record<number, string>
  repeats: Repeat[] // repeating calendar events waiting to come in, one message each
}

/** A gap still to answer: no answer yet and the task not checked off. */
export const open = (g: Gap) => !g.answer && !g.finished

export function messagesOf(src: Sources): Message[] {
  const out: Message[] = src.decisions.map((d) => ({ kind: "decision", key: `d:${d.key}`, decision: d }))
  for (const day of src.days)
    for (const gap of day.gaps.filter(open)) out.push({ kind: "gap", key: `gap:${day.date}:${gap.item_id}`, date: day.date, gap })
  for (const day of src.days) for (const ask of day.sleep) out.push({ kind: "sleep", key: `sleep:${ask.date}:${ask.kind}`, ask })
  const waiting = new Set(src.suggestions.map((s) => s.id))
  for (const s of src.suggestions) out.push({ kind: "suggestion", key: `s:${s.id}`, s })
  for (const s of src.answered ?? []) if (!waiting.has(s.id)) out.push({ kind: "suggestion", key: `s:${s.id}`, s, answered: true })
  for (const group of src.copies) out.push({ kind: "copies", key: `copies:${group.key}`, group, from: src.copySources ?? {} })
  for (const item of src.again) out.push({ kind: "again", key: `again:${item.id}`, item, from: src.againSources?.[item.id] })
  for (const found of src.repeats) out.push({ kind: "repeat", key: found.batch, found })
  return out
}

/** Messages still to deal with: answered suggestions aside. */
export const waitingCount = (messages: Message[]) => messages.filter((m) => !(m.kind === "suggestion" && m.answered)).length

const FULL: Record<string, string> = { Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday", Thu: "Thursday", Fri: "Friday", Sat: "Saturday", Sun: "Sunday" }
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
/** "Thursday 29 October". */
export const dayName = (date: string) => `${FULL[weekday(date)]} ${Number(date.slice(8, 10))} ${MONTHS[Number(date.slice(5, 7)) - 1]}`

/** "Today", "Yesterday", or the day. */
export function dayWord(date: string, today: string): string {
  return date === today ? "Today" : date === addDays(today, -1) ? "Yesterday" : dayLabel(date)
}

/** When a gap's blocks were: "8–8:45am, 10:15–11:30am". */
export function spans(g: Pick<Gap, "spans">): string {
  return g.spans.map(([s, e]) => `${clock(s).replace(/(am|pm)$/, (m) => (clock(e).endsWith(m) ? "" : m))}–${clock(e)}`).join(", ")
}

export const SOURCE_ICONS: Record<string, string> = { gmail: "envelope-simple", ics: "rss", gcal: "google-logo", upload: "file-text" }
const DECISION_ICONS: Record<string, string> = { lock: "lock-simple", learned: "scales", late: "clock-countdown" }

export interface Row {
  icon: string
  title: string
  line: string
  meta: string
  warn?: boolean // what only you can decide
}

/** A message as its row in the list says it. */
export function rowOf(m: Message, today: string): Row {
  switch (m.kind) {
    case "decision": {
      const d = m.decision
      const items = d.items ?? []
      const line = items.length ? items.map((i) => `${i.title} (${lateBy(i.hours)} late)`).join(", ") : d.detail
      return { icon: DECISION_ICONS[d.kind] ?? "hand-pointing", title: d.title, line, meta: "Decide", warn: true }
    }
    case "gap":
      return { icon: "cards", title: m.gap.title, line: `${dur(m.gap.planned_min)} planned, ${spans(m.gap)}: did you do it?`, meta: dayWord(m.date, today) }
    case "sleep":
      return { icon: "moon", title: m.ask.question, line: `A sleep tap you missed; usually ${ampm(m.ask.at.slice(11, 16))}`, meta: dayWord(m.ask.date, today) }
    case "suggestion": {
      const f = m.s.input as Record<string, unknown>
      const at = (f.due ?? f.start) as string | undefined
      const change = m.s.command === "edit" ? "A change · " : m.s.command === "drop" ? "Gone · " : ""
      const line = `${change}${at ? `${f.due ? "due " : ""}${when(at, today)}` : ((f.preset as string) ?? "To add")}`
      return { icon: SOURCE_ICONS[m.s.source_kind ?? ""] ?? "tray", title: String(f.title ?? m.s.origin), line, meta: m.s.source }
    }
    case "copies":
      return { icon: "copy", title: m.group.items[0]?.title ?? m.group.key, line: `On your list ${m.group.items.length} times: keep one`, meta: "Copies" }
    case "again":
      return { icon: "arrow-counter-clockwise", title: m.item.title, line: `${m.item.preset ?? "No kind"} · from ${m.from ?? "you"}: keep it?`, meta: "Go over" }
    case "repeat":
      return { icon: "repeat", title: m.found.title, line: `${m.found.pattern}${m.found.location ? ` · ${m.found.location}` : ""}: do you go?`, meta: "Repeats" }
  }
}

/** The message after `key` once it's dealt with: the next still waiting, else the one before, else none. */
export function nextAfter(messages: Message[], key: string, gone: Set<string>): string | null {
  const live = (m: Message) => !gone.has(m.key) && m.key !== key && !(m.kind === "suggestion" && m.answered)
  const at = messages.findIndex((m) => m.key === key)
  const after = messages.slice(at + 1).find(live)
  const before = [...messages.slice(0, Math.max(0, at))].reverse().find(live)
  return (after ?? before)?.key ?? null
}
