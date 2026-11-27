// Glass box: the new Projects & exams page's rows and words (model.ts).
import { describe, expect, it } from "vitest"
import type { Item } from "@/api/client"
import { againstPlan, aimFor, at, behindRhythm, deadlineRows, diamonds, gridDays, milestones, nextOf, reached, rhythmWords, share, sinceTouched, touchedWords, weekStarts, type Exam, type Project } from "./model"

const NOW = "2026-11-16T09:00"
const TODAY = "2026-11-16"

function item(over: Partial<Item> & { id: number; title: string }): Item {
  return { preset: "Task", area: null, tags: [], parent_id: null, when: "window", start: null, end: null, release: null, due: null, amount: "fixed", duration_min: 60, firmness: "soft", importance: 3, energy: null, shape: "split", certainty: "planned", status: "todo", series_id: null, done_min: 0, remaining_min: 60, ...over } as Item
}

const essay: Project = {
  item: item({ id: 1, title: "Essay", preset: "Project", due: "2026-11-27T17:00", firmness: "hard", area: "HIST 2000" }),
  children: [item({ id: 2, title: "Outline", parent_id: 1, status: "done", duration_min: 60 }), item({ id: 3, title: "Draft", parent_id: 1, duration_min: 180 }), item({ id: 4, title: "Sub-step", parent_id: 3 })],
  done_min: 60,
  remaining_min: 180,
  planned_finish: null,
  status: "on_track",
}
const midterm: Exam = {
  item: item({ id: 10, title: "CS 2112 Prelim", preset: "Exam", when: "fixed", start: "2026-11-20T19:30", area: "CS 2112" }),
  prep: [{ item: item({ id: 11, title: "Review sheet", preset: "Exam prep", duration_min: 120 }), planned_finish: null }],
  done_min: 0,
  remaining_min: 120,
  planned_finish: null,
  status: "unplanned",
  focus_from: null,
}

describe("deadline rows", () => {
  const blocks = [
    { item_id: 3, start: "2026-11-18T14:00", end: "2026-11-18T16:00" },
    { item_id: 3, start: "2026-11-16T07:00", end: "2026-11-16T08:00" }, // already over
    { item_id: 20, start: "2026-11-17T10:00", end: "2026-11-17T12:00" },
  ]
  const rows = deadlineRows([essay], [midterm], blocks, NOW)

  it("puts projects and exams in one list, soonest first, and nothing else", () => {
    // 16 Nov: "it classifies most of my open assignments under projects which is NOT supposed to be the case"
    expect(rows.map((r) => [r.kind, r.title])).toEqual([
      ["exam", "CS 2112 Prelim"],
      ["project", "Essay"],
    ])
  })

  it("gives a project its direct steps and its next session from now", () => {
    const row = rows.find((r) => r.kind === "project")!
    expect(row.steps.map((s) => [s.title, s.done])).toEqual([
      ["Outline", true],
      ["Draft", false],
    ])
    expect(row.next).toBe("2026-11-18T14:00") // the one this morning is over
    expect([row.doneMin, row.totalMin, row.hard]).toEqual([60, 240, true])
  })

  it("dates an exam at its start, with its prep as its steps", () => {
    const row = rows.find((r) => r.kind === "exam")!
    expect([row.due, row.steps[0].title, row.status, row.hard]).toEqual(["2026-11-20T19:30", "Review sheet", "unplanned", true])
  })

})

describe("the six weeks", () => {
  it("places a moment as a share of six weeks from today's start, clamped", () => {
    expect(at("2026-11-16T00:00", TODAY)).toBe(0)
    expect(at("2026-11-23T00:00", TODAY)).toBeCloseTo(100 / 6)
    expect(at("2027-03-01T00:00", TODAY)).toBe(100)
    expect(at("2026-11-01T00:00", TODAY)).toBe(0) // overdue sits at the start
  })

  it("starts each week a week apart, today first", () => {
    expect(weekStarts(TODAY)).toEqual(["2026-11-16", "2026-11-23", "2026-11-30", "2026-12-07", "2026-12-14", "2026-12-21"])
  })

  it("fills a bar as far as it's done, never past full", () => {
    expect(share({ doneMin: 60, totalMin: 240 })).toBe(0.25)
    expect(share({ doneMin: 300, totalMin: 240 })).toBe(1)
    expect(share({ doneMin: 0, totalMin: 0 })).toBe(0)
  })

  it("finds the soonest session not yet over", () => {
    expect(nextOf([{ item_id: 1, start: "2026-11-16T08:00", end: "2026-11-16T10:00" }], [1], NOW)).toBe("2026-11-16T08:00") // under way
    expect(nextOf([], [1], NOW)).toBeNull()
  })
})

describe("ongoing projects", () => {
  it("counts the days since it was touched", () => {
    expect(sinceTouched(["2026-11-10", "2026-11-14"], TODAY)).toBe(2)
    expect(sinceTouched([], TODAY)).toBeNull()
  })

  it("falls behind a rhythm once it's been longer than a week's spacing", () => {
    expect(behindRhythm({ touched: ["2026-11-14"], rhythm_days: 3 }, TODAY)).toBe(false) // 2 days, spacing 3
    expect(behindRhythm({ touched: ["2026-11-12"], rhythm_days: 3 }, TODAY)).toBe(true) // 4 days
    expect(behindRhythm({ touched: [], rhythm_days: null }, TODAY)).toBe(false) // no rhythm: never behind
  })

  it("says when it was touched, or how long it's paused", () => {
    const day = (d: string) => d
    const week = { start: "2026-11-09T04:00", end: "2026-11-16T04:00", target_min: 180, carried_min: 0, done_min: 0, planned_min: 0, item_id: 1 }
    const o = { touched: [] as string[], active: true, paused_until: null as string | null, past: [week] }
    expect(touchedWords({ ...o, touched: [TODAY] }, TODAY, day)).toBe("Touched today")
    expect(touchedWords({ ...o, touched: ["2026-11-15"] }, TODAY, day)).toBe("Last touched yesterday")
    expect(touchedWords(o, TODAY, day)).toBe("Not touched in eight weeks")
    expect(touchedWords({ ...o, past: [] }, TODAY, day)).toBe("Not started yet") // made this week: nothing to miss yet
    expect(touchedWords({ ...o, active: false, paused_until: "2026-11-30" }, TODAY, day)).toBe("Paused until 2026-11-30")
    expect(touchedWords({ ...o, active: false }, TODAY, day)).toBe("Paused")
  })

  it("lays out eight weeks of days from a Monday, today in the last week", () => {
    const days = gridDays(TODAY) // Monday 16 Nov
    expect(days).toHaveLength(56)
    expect(days[0]).toBe("2026-09-28")
    expect(new Date(`${days[0]}T00:00Z`).getUTCDay()).toBe(1)
    expect(days).toContain(TODAY)
  })

  it("says a rhythm with its value", () => {
    expect(rhythmWords(3, 3)).toBe("3 days a week, about 1h each")
    expect(rhythmWords(3, 0)).toBe("Whenever it fits")
  })
})

describe("finished projects", () => {
  it("says what it took against its plan", () => {
    expect(againstPlan({ estimate_min: 100, actual_min: 130 })).toEqual({ words: "30% longer", tone: "warn" })
    expect(againstPlan({ estimate_min: 100, actual_min: 70 })).toEqual({ words: "30% quicker", tone: "good" })
    expect(againstPlan({ estimate_min: 100, actual_min: 105 })).toEqual({ words: "about as planned", tone: "quiet" })
    expect(againstPlan({ estimate_min: 0, actual_min: 50 }).words).toBe("")
  })
})

describe("a project's milestones and aim", () => {
  it("makes its milestones of the steps due before it, soonest first", () => {
    const steps = [
      { id: 1, title: "Draft", done: false, minutes: 60, due: "2026-11-24T17:00" },
      { id: 2, title: "Outline", done: true, minutes: 60, due: "2026-11-20T17:00" },
      { id: 3, title: "Revise", done: false, minutes: 60, due: null },
      { id: 4, title: "Hand in", done: false, minutes: 10, due: "2026-11-27T17:00" }, // the project's own due: one too
      { id: 5, title: "Late extra", done: false, minutes: 10, due: "2026-11-28T17:00" }, // after the project's: none
    ]
    expect(milestones({ steps, due: "2026-11-27T17:00" }).map((m) => m.title)).toEqual(["Outline", "Draft", "Hand in"])
  })

  // 27 Nov, a user's notes ("Friday Notes-3"): LING Final Essay's bar had three diamonds for seven steps, though all but
  // the Final Draft had a due of their own: the Rubric was due with the project, and two steps due the same Monday
  // stood on one spot.
  describe("its diamonds, as the notes' essay has them", () => {
    const essaySteps = [
      { id: 1, title: "Share the representation", done: true, minutes: 30, due: "2026-11-16T23:59" },
      { id: 2, title: "Preliminary Thesis", done: true, minutes: 60, due: "2026-11-23T23:59" },
      { id: 3, title: "research", done: false, minutes: 79, due: "2026-11-30T23:59" },
      { id: 4, title: "Partial first draft of Essay 4 and peer review", done: false, minutes: 240, due: "2026-12-04T23:59" },
      { id: 5, title: "Rubric", done: false, minutes: 60, due: "2026-12-14T23:59" },
      { id: 6, title: "Final Presentations", done: false, minutes: 60, due: "2026-11-30T23:59" },
      { id: 7, title: "Final Draft", done: false, minutes: 120, due: null },
    ]
    const row = { steps: essaySteps, due: "2026-12-14T23:59" }
    it("has one for each day a step is due, the project's own day too, and none for a step with no due", () => {
      expect(diamonds(row).map((d) => d.due.slice(0, 10))).toEqual(["2026-11-16", "2026-11-23", "2026-11-30", "2026-12-04", "2026-12-14"])
      expect(diamonds(row).flatMap((d) => d.titles)).not.toContain("Final Draft")
    })
    it("names every step due that day on its one diamond, and is done only when all of them are", () => {
      const monday = diamonds(row).find((d) => d.due.startsWith("2026-11-30"))
      expect(monday?.titles).toEqual(["research", "Final Presentations"])
      expect(monday?.done).toBe(false)
      const one = diamonds({ ...row, steps: essaySteps.map((x) => (x.id === 3 ? { ...x, done: true } : x)) }).find((d) => d.due.startsWith("2026-11-30"))
      expect(one?.done).toBe(false) // research done, Final Presentations not
      const both = diamonds({ ...row, steps: essaySteps.map((x) => (x.id === 3 || x.id === 6 ? { ...x, done: true } : x)) }).find((d) => d.due.startsWith("2026-11-30"))
      expect(both?.done).toBe(true)
    })
    it("has none for a project with no steps due, and each step its own when no day is shared", () => {
      expect(diamonds({ steps: [{ id: 1, title: "A", done: false, minutes: 60, due: null }], due: "2026-12-14T23:59" })).toEqual([])
      expect(diamonds({ steps: essaySteps.slice(0, 2), due: "2026-12-14T23:59" }).map((d) => d.titles)).toEqual([["Share the representation"], ["Preliminary Thesis"]])
    })
  })

  // 20 Nov, a user's notes: "if you complete one of the due dates, the progress bar should fill until the diamond
  // regardless of how long it took to be completed (in this case the task was finished in 10 mins compared to a
  // projected 30)"
  it("fills its bar at least to the diamond of each step done, however quickly it was done", () => {
    const steps = [
      { id: 1, title: "Preliminary Thesis", done: true, minutes: 30, due: "2026-11-20T17:00" },
      { id: 2, title: "Partial first draft", done: false, minutes: 240, due: "2026-11-26T17:00" },
      { id: 3, title: "Final Draft", done: false, minutes: 300, due: null },
    ]
    const row = { steps, due: "2026-12-14T17:00", doneMin: 10, totalMin: 10 + 540 }
    const diamond = at("2026-11-20T17:00", TODAY) / at("2026-12-14T17:00", TODAY)
    expect(share(row)).toBeLessThan(diamond) // 10 minutes of 550 alone falls short of it
    expect(reached(row, TODAY)).toBeCloseTo(diamond)
    const draft = at("2026-11-26T17:00", TODAY) / at("2026-12-14T17:00", TODAY)
    expect(reached({ ...row, doneMin: 500 }, TODAY)).toBeCloseTo(draft) // never past the draft's diamond, not done yet
    expect(reached({ ...row, steps: steps.map((x) => ({ ...x, done: false })) }, TODAY)).toBeCloseTo(10 / 550) // none done
  })

  // 27 Nov, a user's notes ("Friday Notes-3"): the bar had passed the diamond of Final Presentations, due Mon 30, before
  // the 30th: how far along is the work's share, the diamonds are on the weeks, and the share ran past an open one.
  describe("never past a diamond whose step isn't done", () => {
    const steps = [
      { id: 1, title: "Preliminary Thesis", done: true, minutes: 60, due: "2026-11-20T17:00" },
      { id: 2, title: "Final Presentations", done: false, minutes: 60, due: "2026-11-23T17:00" },
      { id: 3, title: "Partial first draft", done: false, minutes: 240, due: "2026-11-26T17:00" },
      { id: 4, title: "Final Draft", done: false, minutes: 120, due: null },
    ]
    const row = { steps, due: "2026-12-14T17:00", doneMin: 400, totalMin: 480 } // most of the work done
    const on = (due: string) => at(due, TODAY) / at("2026-12-14T17:00", TODAY)
    it("stops at the first open one, however much work is done", () => {
      expect(share(row)).toBeGreaterThan(on("2026-11-23T17:00"))
      expect(reached(row, TODAY)).toBeCloseTo(on("2026-11-23T17:00"))
    })
    it("goes by the work between the done diamond and the open one", () => {
      const between = { ...row, doneMin: 96 } // a fifth of it: past the thesis's diamond, short of the presentations'
      expect(on("2026-11-20T17:00")).toBeLessThan(0.2)
      expect(on("2026-11-23T17:00")).toBeGreaterThan(0.2)
      expect(reached(between, TODAY)).toBeCloseTo(0.2)
    })
    it("moves on to the next open one once that step is done", () => {
      const next = { ...row, steps: steps.map((x) => (x.id === 2 ? { ...x, done: true } : x)) }
      expect(reached(next, TODAY)).toBeCloseTo(on("2026-11-26T17:00"))
    })
    it("goes by the work alone once every step due is done", () => {
      const all = { ...row, steps: steps.map((x) => (x.due ? { ...x, done: true } : x)) }
      expect(reached(all, TODAY)).toBeCloseTo(400 / 480)
    })
    it("still reaches a done step's diamond past an open one (done out of order)", () => {
      const ahead = { ...row, doneMin: 10, steps: steps.map((x) => (x.id === 3 ? { ...x, done: true } : x)) }
      expect(reached(ahead, TODAY)).toBeCloseTo(on("2026-11-26T17:00"))
    })
    it("isn't held at the start by a step that's overdue and not done", () => {
      const overdue = { ...row, steps: [{ id: 9, title: "Late one", done: false, minutes: 60, due: "2026-11-10T17:00" }] }
      expect(reached(overdue, TODAY)).toBeCloseTo(400 / 480)
    })
    it("goes by the work alone for a project with no due", () => {
      expect(reached({ ...row, due: null }, TODAY)).toBeCloseTo(400 / 480)
    })
  })

  it("aims for its due less the days early, at the same time of day", () => {
    expect(aimFor("2026-11-27T17:00", 3)).toBe("2026-11-24T17:00")
    expect(aimFor("2026-12-02T09:00", 5)).toBe("2026-11-27T09:00")
  })

  it("carries its steps' dues into its row", () => {
    const withDue: Project = { ...essay, children: [{ ...essay.children[1], due: "2026-11-22T12:00" }] }
    const [row] = deadlineRows([withDue], [], [], NOW)
    expect(row.steps[0].due).toBe("2026-11-22T12:00")
  })
})
