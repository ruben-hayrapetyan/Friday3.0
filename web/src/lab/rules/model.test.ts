import { describe, expect, it } from "vitest"
import { daysChoice, withDays } from "./sentence"
import { applyChanges, applyDials, diffPlans, planMap, rankRules, readDials, type RuleSpec, shapeChanges, shapeOf } from "./model"

const block = (item_id: number, start: string, end: string) => ({ item_id, title: `T${item_id}`, start, end })

describe("a preview's plan", () => {
  it("is the saved plan with moved items replaced, new ones added and removed ones gone", () => {
    const base = planMap([block(1, "2026-10-21T09:00", "2026-10-21T10:00"), block(2, "2026-10-21T11:00", "2026-10-21T12:00")])
    const after = applyChanges(base, {
      moved: [{ item_id: 1, title: "T1", before: [["2026-10-21T09:00", "2026-10-21T10:00"]], after: [["2026-10-22T09:00", "2026-10-22T10:00"]] }],
      added: [{ key: "T3@x", item_id: 3, title: "T3", start: "2026-10-23T09:00", end: "2026-10-23T09:30" }],
      removed: [{ key: "T2@x", item_id: 2, title: "T2", start: "2026-10-21T11:00", end: "2026-10-21T12:00" }],
    })
    expect([...after.keys()].sort()).toEqual([1, 3])
    expect(diffPlans(base, after).map((m) => m.itemId)).toEqual([1, 2, 3])
    expect(diffPlans(after, after)).toEqual([])
  })
})

describe("a plan's shape", () => {
  it("counts late-night, weekend and back-to-back hours", () => {
    // Fri 23 Oct 2026 22:00–00:30 then Sat 10:00–11:00
    const plan = planMap([block(1, "2026-10-23T22:00", "2026-10-24T00:00"), block(2, "2026-10-24T00:00", "2026-10-24T00:30"), block(3, "2026-10-24T10:00", "2026-10-24T11:00")])
    const shape = shapeOf(plan)
    expect(shape).toMatchObject({ total: 3.5, lateNight: 2.5, weekends: 1, longestSitting: 2.5, sittings: 2, heaviestDay: 2.5 })
    expect(shapeChanges(shape, { ...shape, lateNight: 1 })).toEqual(["1.5 h less late-night work (after 22:00)"])
  })
})

const rules: RuleSpec[] = [
  { type: "late_night", name: "late_night", weight: 1, params: { gradient_start: "22:00", a: 2 } },
  { type: "reserve", name: "weekday_evenings", weight: 2, params: { free: "2h" } },
  { type: "finish_early", name: "finish_early", weight: 1, params: { days: 1 } },
]

describe("dials", () => {
  it("write their stop over the named rules and read back where they are", () => {
    const strict = applyDials(rules, { sleep: 2 })
    expect(strict[0]).toMatchObject({ weight: 3, params: { gradient_start: "21:00", a: 2 } })
    expect(readDials(strict).sleep).toBe(2)
    expect(readDials(rules).sleep).toBe(1)
    expect(readDials([{ ...rules[0], weight: 7 }]).sleep).toBe(-1)
  })
})

describe("ranking", () => {
  const concerns = [
    { id: "sleep", title: "Sleep", rules: ["late_night"] },
    { id: "evenings", title: "Evenings", rules: ["weekday_evenings"] },
    { id: "early", title: "Early", rules: ["finish_early"] },
  ]
  const start = ["sleep", "evenings", "early"]

  it("changes nothing in today's order", () => {
    expect(rankRules(rules, start, start, 2, concerns)).toEqual(rules)
  })

  it("doubles a weight per place up, halves it per place down, and stages by the line", () => {
    const ranked = rankRules(rules, start, ["early", "sleep", "evenings"], 2, concerns)
    expect(ranked.map((r) => [r.name, r.stage ?? null, r.weight])).toEqual([
      ["late_night", null, 0.5],
      ["weekday_evenings", "preferences", 1],
      ["finish_early", "wellbeing", 4],
    ])
  })
})

describe("days in a sentence", () => {
  it("read days and days_except as one choice and write it back", () => {
    expect(daysChoice({ days_except: ["sat", "sun"] })).toBe("weekdays")
    expect(daysChoice({ days: ["mon"] })).toBe("mon")
    expect(daysChoice({ days: ["mon", "wed"] })).toBe("custom")
    expect(withDays({ days_except: ["sat", "sun"], free: "2h" }, "weekends")).toEqual({ days: ["sat", "sun"], days_except: null, free: "2h" })
  })
})
