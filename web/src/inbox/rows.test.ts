// How each kind of Inbox message reads as its row, and the days it names: the kinds messages.test.ts leaves out.
import { describe, expect, it } from "vitest"
import type { Item, Schemas } from "@/api/client"
import { mealAsks } from "./asks"
import { dayName, dayWord, type Message, rowOf } from "./messages"

const TODAY = "2026-10-29"
const decision = (kind: string, more: Partial<Schemas["Decision"]> = {}) => ({ kind, key: kind, title: `A ${kind}`, detail: `Why ${kind}`, ...more }) as unknown as Schemas["Decision"]
const suggestion = (command: string, input: Record<string, unknown>, source_kind: string | null = "gcal") =>
  ({ id: 1, source: "Personal", origin: "From the calendar", command, input, quotes: {}, confidence: 1, duplicate_of: null, batch: null, created: "2026-10-29T09:00", source_kind }) as unknown as Schemas["SuggestionOut"]
const row = (m: Message) => rowOf(m, TODAY)

describe("an Inbox message as its row", () => {
  it("says a decision with no late work in its own words, with the icon of its kind", () => {
    expect(row({ kind: "decision", key: "d:lock", decision: decision("lock") })).toMatchObject({ icon: "lock-simple", line: "Why lock", meta: "Decide", warn: true })
    expect(row({ kind: "decision", key: "d:learned", decision: decision("learned") }).icon).toBe("scales")
    expect(row({ kind: "decision", key: "d:other", decision: decision("other") }).icon).toBe("hand-pointing")
  })

  it("lists each late task with how late it is", () => {
    const late = decision("late", { items: [{ item_id: 1, title: "PS 9", hours: 2, due: null }, { item_id: 2, title: "Essay", hours: 0.5, due: null }] } as never)
    expect(row({ kind: "decision", key: "d:late", decision: late }).line).toMatch(/^PS 9 \(.+ late\), Essay \(.+ late\)$/)
  })

  it("says a missed sleep tap with your usual time", () => {
    const ask = { kind: "bed", date: "2026-10-28", at: "2026-10-28T23:30", question: "When did you go to bed?" } as Schemas["SleepAsk"]
    expect(row({ kind: "sleep", key: "s", ask })).toMatchObject({ icon: "moon", title: "When did you go to bed?", line: "A sleep tap you missed; usually 11:30pm", meta: "Yesterday" })
  })

  it("says a change or a removal from a calendar, and what there is to add when it has no time", () => {
    expect(row({ kind: "suggestion", key: "s:1", s: suggestion("edit", { title: "Advising", start: "2026-10-30T11:40" }) }).line).toMatch(/^A change · /)
    expect(row({ kind: "suggestion", key: "s:1", s: suggestion("drop", { title: "Club" }) }).line).toBe("Gone · To add")
    expect(row({ kind: "suggestion", key: "s:1", s: suggestion("add", { title: "Pick up keys", preset: "Errand" }) }).line).toBe("Errand")
    expect(row({ kind: "suggestion", key: "s:1", s: suggestion("add", { title: "PS 9", due: "2026-10-31T23:59" }) }).line).toMatch(/^due /)
  })

  it("falls back to the source's words and a tray when a suggestion has no title or known source", () => {
    expect(row({ kind: "suggestion", key: "s:1", s: suggestion("add", {}, null) })).toMatchObject({ title: "From the calendar", icon: "tray" })
    expect(row({ kind: "suggestion", key: "s:1", s: suggestion("add", {}, "upload") }).icon).toBe("file-text")
  })

  it("says a task to go over with its kind and where it came from", () => {
    const item = { id: 30, title: "Read ch. 4", preset: null } as unknown as Item
    expect(row({ kind: "again", key: "again:30", item, from: "Canvas" })).toMatchObject({ line: "No kind · from Canvas: keep it?", meta: "Go over" })
    expect(row({ kind: "again", key: "again:30", item: { ...item, preset: "Reading" } })).toMatchObject({ line: "Reading · from you: keep it?" })
  })

  it("says a repeating event with no place without one", () => {
    const found = { batch: "b", title: "Club", kind: "Meeting", calendar: "c", pattern: "Every Monday", count: 3, first: null, location: null } as unknown as Schemas["RepeatFound"]
    expect(row({ kind: "repeat", key: "b", found }).line).toBe("Every Monday: do you go?")
  })

  it("titles copies by the key when the group is empty", () => {
    expect(row({ kind: "copies", key: "c", group: { key: "ps 9", keep: 1, items: [] }, from: {} })).toMatchObject({ title: "ps 9", line: "On your list 0 times: keep one" })
  })
})

describe("the days a message names", () => {
  it("names a day in full", () => {
    expect(dayName("2026-10-29")).toBe("Thursday 29 October")
    expect(dayName("2026-01-04")).toBe("Sunday 4 January")
  })

  it("says today and yesterday in words, other days by their label", () => {
    expect(dayWord(TODAY, TODAY)).toBe("Today")
    expect(dayWord("2026-10-28", TODAY)).toBe("Yesterday")
    expect(dayWord("2026-10-20", TODAY)).not.toMatch(/Today|Yesterday/)
  })
})

describe("a meal you have most days", () => {
  it("asks to plan it at the time you usually have it", () => {
    const run = { length: async () => ({}), time: async () => ({}), plan: async () => ({}) }
    const meals = { on: true, changes: [], times: [], plans: [{ kind: "breakfast", plan: true, usual_start: "08:30" }, { kind: "lunch", plan: true, usual_start: null }] } as unknown as Schemas["MealsOut"]
    const [breakfast, lunch] = mealAsks(meals, run)
    expect(breakfast).toMatchObject({ title: "You have breakfast most days, around 8:30am", why: "Friday doesn't plan it. Plan it from now on?", evidence: "true08:30" })
    expect(breakfast.yes?.label).toBe("Plan breakfast")
    expect(lunch.title).toBe("You have lunch most days, around 8am")
  })
})
