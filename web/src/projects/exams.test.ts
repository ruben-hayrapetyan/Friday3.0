import { describe, expect, it } from "vitest"
import type { Block, Item } from "@/api/client"
import { toMin } from "@/lib/time"
import { away, countdown, course, type Exam, prepState, readiness, sitting, soonAndLater, summary } from "./exams"

const TODAY = "2026-10-24"
const NOON = toMin(`${TODAY}T12:00`)

function item(over: Partial<Item>): Item {
  return { id: 1, title: "Study guide", preset: "Exam prep", area: null, status: "todo", duration_min: 120, remaining_min: 120, done_min: 0, start: null, end: null, due: null, ...over } as Item
}

function exam(over: Partial<Exam> = {}, at = "2026-10-27T19:30"): Exam {
  return {
    item: item({ id: 9, title: "MATH 2940 Prelim 2", preset: "Exam", event_kind: "exam", start: at, end: "2026-10-27T21:00" }),
    prep: [],
    done_min: 0,
    remaining_min: 0,
    planned_finish: null,
    status: "no_prep",
    focus_from: null,
    ...over,
  }
}

const block = (start: string, end: string, item_id = 1) => ({ key: start, item_id, start, end }) as Block

describe("how far off an exam is", () => {
  it("says now while it runs, today and tomorrow, then days, then weeks", () => {
    expect(countdown(`${TODAY}T11:00`, `${TODAY}T13:00`, NOON, TODAY)).toBe("Now")
    expect(countdown(`${TODAY}T19:30`, `${TODAY}T21:00`, NOON, TODAY)).toBe("Today")
    expect(countdown("2026-10-25T09:00", "2026-10-25T10:00", NOON, TODAY)).toBe("Tomorrow")
    expect(countdown("2026-10-27T19:30", "2026-10-27T21:00", NOON, TODAY)).toBe("In 3 days")
    expect(countdown("2026-12-10T09:00", "2026-12-10T11:00", NOON, TODAY)).toBe("In 7 weeks")
  })

  it("says a day that has passed is overdue", () => {
    expect(away("2026-10-22T17:00", TODAY)).toBe("Overdue")
  })

  it("writes its sitting on a 12-hour clock", () => {
    expect(sitting("2026-10-27T19:30", "2026-10-27T21:00")).toBe("Tue 27 Oct, 7:30pm–9pm")
  })
})

describe("readiness", () => {
  it("is the share of prep time done, and nothing without prep", () => {
    expect(readiness(exam())).toBeNull()
    const prep = [{ item: item({}), planned_finish: null }]
    expect(readiness(exam({ prep, done_min: 30, remaining_min: 90, status: "on_track" }))).toBe(25)
    expect(readiness(exam({ prep, status: "ready" }))).toBe(100)
  })
})

describe("a piece of prep against the plan", () => {
  const start = "2026-10-27T19:30"
  it("is done, unplanned, planned after the exam, or planned with its sessions", () => {
    expect(prepState({ item: item({ status: "done" }), planned_finish: null }, [], start, TODAY).state).toBe("done")
    expect(prepState({ item: item({}), planned_finish: null }, [], start, TODAY)).toMatchObject({ state: "unplanned", left: 120 })
    expect(prepState({ item: item({}), planned_finish: "2026-10-28T10:00" }, [], start, TODAY).state).toBe("late")
    const one = prepState({ item: item({}), planned_finish: "2026-10-26T16:00" }, [block("2026-10-26T14:00", "2026-10-26T16:00")], start, TODAY)
    expect(one).toMatchObject({ state: "planned", note: "Mon 2pm–4pm" })
    const two = [block("2026-10-26T14:00", "2026-10-26T15:00"), block("2026-10-25T09:00", "2026-10-25T10:00"), block("2026-10-25T09:00", "2026-10-25T10:00", 2)]
    expect(prepState({ item: item({}), planned_finish: "2026-10-26T15:00" }, two, start, TODAY).note).toBe("2 sessions, from Sun 9am")
    const later = prepState({ item: item({}), planned_finish: `${TODAY}T18:00` }, [block(`${TODAY}T16:00`, `${TODAY}T18:00`)], start, TODAY)
    expect(later.note).toBe("today 4pm–6pm")
  })
})

describe("the line under an exam", () => {
  it("says how much isn't planned, or when prep finishes and how long before", () => {
    const prep = { item: item({}), planned_finish: null }
    const states = [prepState(prep, [], "2026-10-27T19:30", TODAY)]
    expect(summary(exam({ prep: [prep], remaining_min: 120, status: "unplanned" }), states, TODAY)).toEqual({ text: "2h of prep isn't planned yet.", tone: "warn" })
    const onTrack = exam({ prep: [prep], remaining_min: 120, status: "on_track", planned_finish: "2026-10-26T16:00" })
    expect(summary(onTrack, [], TODAY)).toEqual({ text: "2h to go, planned to finish Mon 4pm, 1 day before.", tone: "good" })
    expect(summary(exam(), [], TODAY).tone).toBe("quiet")
  })

  // 19 Nov, a user's notes: "Prep runs past the exam: it's planned to finish 18:30" of an exam at 19:00
  it("says how much prep has no room when the rest finishes before the exam, and runs past only when it does", () => {
    const at = "2026-10-27T19:30"
    const late = (finish: string, unfit_min: number) => summary(exam({ status: "late", remaining_min: 240, planned_finish: finish, unfit_min }, at), [], TODAY)
    expect(late("2026-10-27T18:30", 15)).toEqual({ text: "15m of prep doesn't fit before the exam; the rest is planned to finish Tue 6:30pm.", tone: "due" })
    expect(late("2026-10-27", 90)).toEqual({ text: "1h 30m of prep doesn't fit before the exam; the rest is planned to finish Tue.", tone: "due" }) // a day, the exam's
    expect(late("2026-10-27T18:30", 0)).toEqual({ text: "Some prep is planned after its own due; all of it finishes Tue 6:30pm, before the exam.", tone: "warn" })
    expect(late("2026-10-27T20:00", 15).text).toBe("Prep runs past the exam: it's planned to finish Tue 8pm.")
    expect(late("2026-10-28", 0).text).toBe("Prep runs past the exam: it's planned to finish Wed.")
  })
})

describe("soon and later", () => {
  it("keeps the next three weeks in full and folds the rest", () => {
    const near = exam()
    const far = exam({}, "2026-12-10T09:00")
    expect(soonAndLater([near, far], TODAY)).toEqual([[near], [far]])
  })

  it("reads the course from the tag, else a course code in the title", () => {
    expect(course(item({ area: "CS 2800", title: "Prelim" }))).toBe("CS 2800")
    expect(course(item({ title: "MATH 2940 Prelim 2" }))).toBe("MATH 2940")
    expect(course(item({ title: "Driving test" }))).toBeNull()
  })
})
