import { describe, expect, it } from "vitest"
import type { Item } from "@/api/client"
import { dayLabel, dueGroups, dueSoon, isDeadline, lateWarning, overdueBy, stillMatters } from "./dueSoon"
import { toMin } from "./time"

const NOW = toMin("2026-11-03T22:00") // a Tuesday evening
const item = (id: number, due: string | null, extra: Partial<Item> = {}): Item =>
  ({ id, title: `T${id}`, status: "todo", due, firmness: "hard", pointless_late: false, fading_late: false, ...extra }) as Item
const ids = (rows: { item: Item }[]) => rows.map((r) => r.item.id)

// black box: what the list shows

describe("due this week", () => {
  it("lists the next seven days' work day by day, soonest first", () => {
    const out = dueSoon(
      [
        item(1, "2026-11-05T23:59"),
        item(2, "2026-11-03T23:59"),
        item(3, "2026-11-05T09:00"),
        item(4, "2026-11-09T23:59"),
        item(5, "2026-11-10T00:00"), // a week from today's start: next week
        item(6, null),
      ],
      NOW,
    )
    expect(out.days.map((d) => [d.day, ids(d.rows)])).toEqual([
      ["2026-11-03", [2]],
      ["2026-11-05", [3, 1]],
      ["2026-11-09", [4]],
    ])
  })

  it("keeps overdue work that still matters on top, and leaves off what stopped mattering at its due", () => {
    const out = dueSoon(
      [
        item(1, "2026-11-02T23:59"), // a hard deadline: still to do
        item(2, "2026-11-01T23:59", { firmness: "soft" }),
        item(3, "2026-11-02T12:00", { pointless_late: true }),
        item(4, "2026-10-30T23:59", { fading_late: true }), // a late reading
        item(5, "2026-11-03T21:00"), // an hour ago
        item(6, "2026-11-02T23:59", { status: "done" }),
      ],
      NOW,
    )
    expect(ids(out.overdue)).toEqual([1, 5])
    expect(out.days).toEqual([])
  })

  it("leaves out meals and other soft repeats, whose due only ends their window", () => {
    const out = dueSoon(
      [
        item(1, "2026-11-04T14:30", { title: "Lunch", firmness: "soft", series_id: 7 }),
        item(2, "2026-11-02T14:30", { title: "Lunch", firmness: "soft", series_id: 7 }),
        item(3, "2026-11-05T23:59", { title: "Weekly quiz", series_id: 8 }), // a hard repeat is a deadline
      ],
      NOW,
    )
    expect(out.overdue).toEqual([])
    expect(out.days.flatMap((d) => ids(d.rows))).toEqual([3])
  })

  it("says which work Friday has late or hasn't found time for", () => {
    const late = [{ item_id: 1, hours: 3 }, { item_id: 2, hours: 0, planned: false }]
    const out = dueSoon([item(1, "2026-11-04T17:00"), item(2, "2026-11-01T17:00"), item(3, "2026-11-04T18:00")], NOW, late)
    expect(out.overdue[0].late).toEqual(late[1])
    expect(out.days[0].rows.map((r) => r.late?.hours)).toEqual([3, undefined])
  })

  it("names days the way you say them", () => {
    expect(dayLabel("2026-11-03", "2026-11-03")).toBe("Today")
    expect(dayLabel("2026-11-04", "2026-11-03")).toBe("Tomorrow")
    expect(dayLabel("2026-11-06", "2026-11-03")).toBe("Fri 6")
  })

  it("says how long work has been overdue", () => {
    expect(overdueBy("2026-11-03T21:30", NOW)).toBe("just overdue")
    expect(overdueBy("2026-11-03T17:00", NOW)).toBe("5h overdue")
    expect(overdueBy("2026-11-02T22:00", NOW)).toBe("1 day overdue")
    expect(overdueBy("2026-10-30T12:00", NOW)).toBe("4 days overdue")
  })
})

// glass box: the rule for what still matters, and the edges of the week

describe("dueSoon's edges", () => {
  it("still matters: hard, and neither fading nor pointless once late", () => {
    expect(stillMatters(item(1, "x"))).toBe(true)
    expect(stillMatters(item(1, "x", { firmness: "soft" }))).toBe(false)
    expect(stillMatters(item(1, "x", { firmness: "none" }))).toBe(false)
    expect(stillMatters(item(1, "x", { fading_late: true }))).toBe(false)
    expect(stillMatters(item(1, "x", { pointless_late: true }))).toBe(false)
  })

  it("a deadline: a one-off, or a repeat that is hard", () => {
    expect(isDeadline(item(1, "x", { firmness: "soft" }))).toBe(true)
    expect(isDeadline(item(1, "x", { series_id: 3 }))).toBe(true)
    expect(isDeadline(item(1, "x", { series_id: 3, firmness: "soft" }))).toBe(false)
  })

  it("work due this very minute is due today, not overdue", () => {
    const out = dueSoon([item(1, "2026-11-03T22:00")], NOW)
    expect(out.overdue).toEqual([])
    expect(ids(out.days[0].rows)).toEqual([1])
  })

  it("soft work still to come is listed: only its lateness stops it mattering", () => {
    expect(ids(dueSoon([item(1, "2026-11-04T23:59", { firmness: "soft" })], NOW).days[0].rows)).toEqual([1])
  })

  it("every open item due in the window lands in exactly one day, days in order", () => {
    const items = Array.from({ length: 60 }, (_, n) => item(n, `2026-11-${String(3 + (n % 9)).padStart(2, "0")}T${String(n % 24).padStart(2, "0")}:00`))
    const out = dueSoon(items, NOW)
    const listed = out.days.flatMap((d) => ids(d.rows))
    expect(new Set(listed).size).toBe(listed.length)
    const expected = items.filter((i) => toMin(i.due!) >= NOW && i.due! < "2026-11-10T00:00").map((i) => i.id)
    expect([...listed].sort((a, b) => a - b)).toEqual([...expected].sort((a, b) => a - b))
    expect(out.days.map((d) => d.day)).toEqual([...out.days.map((d) => d.day)].sort())
    for (const d of out.days) expect(d.rows.every((r) => r.item.due!.startsWith(d.day))).toBe(true)
  })
})

describe("the to-do drawer's Due view", () => {
  it("is Overdue in red, then each day by name", () => {
    const groups = dueGroups([item(1, "2026-11-02T23:59"), item(2, "2026-11-03T23:00"), item(3, "2026-11-04T09:00"), item(4, "2026-11-06T12:00")], NOW)
    expect(groups.map((g) => [g.name, g.items.map((i) => i.id), !!g.red])).toEqual([
      ["Overdue", [1], true],
      ["Today", [2], false],
      ["Tomorrow", [3], false],
      ["Fri 6", [4], false],
    ])
    expect(groups[0].overdue).toBe(true)
  })

  it("has no Overdue group when nothing overdue still matters", () => {
    expect(dueGroups([item(1, "2026-11-02T23:59", { firmness: "soft" })], NOW)).toEqual([])
  })

  it("carries the plan's late work to each row", () => {
    const groups = dueGroups([item(1, "2026-11-04T09:00")], NOW, [{ item_id: 1, hours: 2 }])
    expect(groups[0].late?.get(1)).toEqual({ item_id: 1, hours: 2 })
  })
})

describe("what a row says of Friday's lateness", () => {
  it("says how late, or that there's no time for it", () => {
    expect(lateWarning(undefined)).toBeNull()
    expect(lateWarning({ item_id: 1, hours: 0.5 })).toBe("Friday has it 30m late")
    expect(lateWarning({ item_id: 1, hours: 2.25 })).toBe("Friday has it 2h 15m late")
    expect(lateWarning({ item_id: 1, hours: 14.8 })).toBe("Friday has it 15h late")
    expect(lateWarning({ item_id: 1, hours: 0, planned: false })).toBe("Friday has no time for it")
  })
})
