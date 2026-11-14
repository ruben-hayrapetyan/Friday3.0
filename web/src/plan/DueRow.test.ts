// The due row under the dates (plan/DueRow.tsx; 13 Nov: the to-do lane squeezed each day's tasks and events). Which of
// a day's deadlines show, in what order, and how many wait behind "+N more".
import { describe, expect, it } from "vitest"
import { toMin } from "@/lib/time"
import { DUE_ROW_MAX, dayDues, dueAt } from "./DueRow"

const due = (item_id: number, title: string, at: string) => ({ item_id, title, due: at })
const day = "2026-11-18"
const noon = toMin(`${day}T12:00`)

describe("a day's row of deadlines", () => {
  it("shows a light day whole, in the order they're due", () => {
    const row = dayDues([due(1, "Reading", `${day}T17:00`), due(2, "Lab", `${day}T09:00`)], day, toMin(`${day}T07:00`))
    expect(row.shown.map((d) => d.title)).toEqual(["Lab", "Reading"])
    expect(row.more).toBe(0)
  })

  it("puts what's already late first, then the rest by when they're due", () => {
    const dues = [due(1, "HW 12", `${day}T23:59`), due(2, "Pre-lab 10", `${day}T13:00`), due(3, "Post-lab 9", `${day}T09:00`)]
    expect(dayDues(dues, day, noon).shown.map((d) => d.title)).toEqual(["Post-lab 9", "Pre-lab 10", "HW 12"])
    expect(dayDues(dues, day, toMin(`${day}T14:00`)).shown.map((d) => d.title)).toEqual(["Post-lab 9", "Pre-lab 10", "HW 12"])
  })

  it("stops a busy day at three and counts the rest, keeping every one for the list it opens", () => {
    const dues = Array.from({ length: 8 }, (_, i) => due(i + 1, `Task ${i + 1}`, `${day}T${String(9 + i).padStart(2, "0")}:00`))
    const row = dayDues(dues, day, toMin(`${day}T06:00`))
    expect(DUE_ROW_MAX).toBe(3)
    expect(row.shown).toHaveLength(3)
    expect(row.more).toBe(5)
    expect(row.all.map((d) => d.item_id)).toEqual([1, 2, 3, 4, 5, 6, 7, 8])
  })

  it("keeps to its own day", () => {
    const row = dayDues([due(1, "Tomorrow's", "2026-11-19T09:00"), due(2, "Today's", `${day}T09:00`)], day, noon)
    expect(row.all.map((d) => d.title)).toEqual(["Today's"])
  })

  it("says a due at the day's last minute is due at the end of the day", () => {
    expect(dueAt(due(1, "x", `${day}T23:59`))).toBe("end of day")
    expect(dueAt(due(1, "x", `${day}T17:00`))).toBe("5pm")
  })
})
