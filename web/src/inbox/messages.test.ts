import { describe, expect, it } from "vitest"
import type { Item, Schemas } from "@/api/client"
import { type Message, messagesOf, nextAfter, rowOf, type Sources, spans, waitingCount } from "./messages"

const TODAY = "2026-10-29"
const YESTERDAY = "2026-10-28"

const gap = (item_id: number, title: string, more: Partial<Schemas["ReviewGap"]> = {}): Schemas["ReviewGap"] => ({
  item_id,
  title,
  planned_min: 90,
  spans: [["2026-10-28T10:15", "2026-10-28T11:45"]],
  blocks: [`T${item_id}@x`],
  ...more,
})
const suggestion = (id: number, title: string, source = "Gmail"): Schemas["SuggestionOut"] =>
  ({ id, source, origin: title, command: "add", input: { title, due: "2026-10-31T23:59" }, quotes: {}, confidence: 1, duplicate_of: null, batch: null, created: "2026-10-29T09:00", source_kind: "gmail" }) as Schemas["SuggestionOut"]
const late = { kind: "late", key: "late", title: "3 things will be late", detail: "Nothing fits before their dues.", items: [{ item_id: 1, title: "PS 9", hours: 2, due: null }] } as unknown as Schemas["Decision"]
const item = (id: number, title: string) => ({ id, title, preset: "Assignment" }) as Item

const SOURCES: Sources = {
  decisions: [late],
  days: [
    { date: YESTERDAY, gaps: [gap(10, "Psych WA8"), gap(11, "Answered already", { answer: "done" }), gap(12, "Checked off", { finished: true })], sleep: [{ kind: "bed", date: YESTERDAY, at: "2026-10-28T23:30", question: "When did you go to bed?" }] },
    { date: TODAY, gaps: [gap(20, "Chem pre-lab")], sleep: [] },
  ],
  suggestions: [suggestion(100, "Palantir screening"), suggestion(101, "CUAI zoom")],
  answered: [suggestion(99, "Accepted earlier")],
  copies: [{ key: "ps 9", keep: 1, items: [item(1, "PS 9"), item(2, "PS 9")] }],
  again: [item(30, "Read ch. 4")],
  repeats: [{ batch: "repeat:club", title: "CS Theory Club", kind: "Meeting", calendar: "student@school.edu", pattern: "Every Wednesday until May 31, 5pm–6:30pm", count: 12, first: "2026-11-04T17:00", location: "CIS Building" }],
}

describe("the Inbox as one list of messages", () => {
  const list = messagesOf(SOURCES)

  it("puts what only you can decide first, then yesterday's gaps and today's, missed sleep taps, what came in, copies, a go-over and repeating events", () => {
    expect(list.map((m) => m.key)).toEqual(["d:late", `gap:${YESTERDAY}:10`, `gap:${TODAY}:20`, `sleep:${YESTERDAY}:bed`, "s:100", "s:101", "s:99", "copies:ps 9", "again:30", "repeat:club"])
  })

  it("asks only the gaps not answered and not checked off", () => {
    expect(list.filter((m) => m.kind === "gap").map((m) => (m as Extract<Message, { kind: "gap" }>).gap.title)).toEqual(["Psych WA8", "Chem pre-lab"])
  })

  it("counts what's waiting, not suggestions you've already answered here", () => {
    expect(waitingCount(list)).toBe(9)
    expect(waitingCount(messagesOf({ ...SOURCES, repeats: [], answered: [] }))).toBe(8)
  })

  it("an answered suggestion still waiting on the server isn't listed twice", () => {
    const twice = messagesOf({ ...SOURCES, answered: [suggestion(100, "Palantir screening")] })
    expect(twice.filter((m) => m.key === "s:100")).toHaveLength(1)
  })

  it("says each in a row: the decision in warm, a gap's day and question, a suggestion's source", () => {
    expect(rowOf(list[0], TODAY)).toMatchObject({ title: "3 things will be late", warn: true, meta: "Decide" })
    expect(rowOf(list[1], TODAY)).toMatchObject({ title: "Psych WA8", meta: "Yesterday", line: "1h 30m planned, 10:15–11:45am: did you do it?" })
    expect(rowOf(list[2], TODAY).meta).toBe("Today")
    expect(rowOf(list[4], TODAY)).toMatchObject({ title: "Palantir screening", meta: "Gmail", icon: "envelope-simple" })
    expect(rowOf(list[7], TODAY).line).toBe("On your list 2 times: keep one")
    expect(rowOf(list[9], TODAY)).toMatchObject({ title: "CS Theory Club", line: "Every Wednesday until May 31, 5pm–6:30pm · CIS Building: do you go?" })
  })

  it("opens the next one once you've dealt with one, else the one before", () => {
    expect(nextAfter(list, "d:late", new Set())).toBe(`gap:${YESTERDAY}:10`)
    expect(nextAfter(list, "s:101", new Set())).toBe("copies:ps 9") // the answered one is passed over
    expect(nextAfter(list, "repeat:club", new Set())).toBe("again:30")
    expect(nextAfter(list, "copies:ps 9", new Set(["again:30", "repeat:club"]))).toBe("s:101")
    expect(nextAfter([list[0]], "d:late", new Set())).toBeNull()
  })
})

describe("when a task's time was", () => {
  it("drops the first am or pm when both ends share it", () => {
    expect(spans({ spans: [["2026-10-28T08:00", "2026-10-28T08:45"]] })).toBe("8–8:45am")
  })
  it("keeps both when the time crosses noon", () => {
    expect(spans({ spans: [["2026-10-28T11:30", "2026-10-28T12:30"]] })).toBe("11:30am–12:30pm")
  })
  it("lists each block", () => {
    const two = spans({ spans: [["2026-10-28T08:00", "2026-10-28T08:45"], ["2026-10-28T22:15", "2026-10-28T23:30"]] })
    expect(two).toBe("8–8:45am, 10:15–11:30pm")
  })
})
