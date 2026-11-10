// Friday's questions in the Inbox (C75): counted there, set aside by "Not now" until what they're based on changes.
import { describe, expect, it } from "vitest"
import type { Schemas } from "@/api/client"
import { type Ask, mealAsks, waiting } from "./asks"
import { messagesOf, rowOf, waitingCount } from "./messages"

const ask = (key: string, evidence: string, more: Partial<Ask> = {}): Ask => ({ key, evidence, icon: "timer", kicker: "What Friday learned", title: `Ask ${key}`, why: "Because.", ...more })
const EMPTY = { decisions: [], days: [], suggestions: [], copies: [], again: [], repeats: [] }

describe("Friday's questions as Inbox messages (black box)", () => {
  it("each is a message, counted with the rest", () => {
    const list = messagesOf({ ...EMPTY, asks: [ask("durations", "8"), ask("sleep-times", "x")] })
    expect(list.map((m) => m.key)).toEqual(["ask:durations", "ask:sleep-times"])
    expect(waitingCount(list)).toBe(2)
  })

  it("reads as a question in the list", () => {
    const [m] = messagesOf({ ...EMPTY, asks: [ask("durations", "8", { title: "Use the lengths Friday learned", why: "They're 12% off." })] })
    expect(rowOf(m, "2026-11-09")).toMatchObject({ title: "Use the lengths Friday learned", line: "They're 12% off.", meta: "Question" })
  })

  it("comes after what only you can decide and the day's gaps, before mail", () => {
    const late = { kind: "late", key: "late", title: "Late", detail: "" } as unknown as Schemas["Decision"]
    const mail = { id: 1, source: "Gmail", origin: "x", command: "add", input: { title: "x" } } as unknown as Schemas["SuggestionOut"]
    const kinds = messagesOf({ ...EMPTY, decisions: [late], suggestions: [mail], asks: [ask("energy", "3")] }).map((m) => m.kind)
    expect(kinds).toEqual(["decision", "ask", "suggestion"])
  })
})

describe("Not now (glass box: waiting)", () => {
  const asks = [ask("durations", "8"), ask("energy", "12")]
  it("leaves a question out while its evidence is the same", () => {
    expect(waiting(asks, { durations: "8" }).map((a) => a.key)).toEqual(["energy"])
  })
  it("asks again once Friday has more to go on", () => {
    expect(waiting([ask("durations", "11"), asks[1]], { durations: "8" }).map((a) => a.key)).toEqual(["durations", "energy"])
  })
})

describe("meals' questions", () => {
  const run = { length: async () => ({}), time: async () => ({}), plan: async () => ({}) }
  const meals = {
    on: true,
    changes: [{ kind: "lunch", usual_min: 40, planned_min: 60 }],
    times: [{ kind: "dinner", usual_start: "19:00", start: "18:00", end: "19:00", new_start: "18:45", new_end: "19:45" }],
    plans: [{ kind: "breakfast", plan: false, usual_start: null }],
    decided: [] as string[],
  } as unknown as Schemas["MealsOut"]

  it("asks each, in words, with the answer on its button", () => {
    const found = mealAsks(meals, run)
    expect(found.map((a) => a.key)).toEqual(["meal-length:lunch", "meal-time:dinner", "meal-plan:breakfast"])
    expect(found[0].title).toBe("Lunch takes you about 40m")
    expect(found[0].yes?.label).toBe("Plan 45m")
    expect(found[1].yes?.label).toBe("Plan 6:45pm–7:45pm")
    expect(found[2]).toMatchObject({ title: "You usually skip breakfast", why: "Friday still plans it. Stop planning it?" })
  })

  it("leaves out a meal Friday decides itself", () => {
    expect(mealAsks({ ...meals, decided: ["lunch", "dinner"] } as Schemas["MealsOut"], run).map((a) => a.key)).toEqual(["meal-plan:breakfast"])
  })
})
