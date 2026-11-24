import { describe, expect, it } from "vitest"
import type { Schemas } from "@/api/client"
import { because, lines, summary } from "./changes"

const block = (item_id: number, title: string, start: string) => ({ key: `T${item_id}@${start}`, item_id, title, start, end: start })

const changes: Schemas["ChangeOut"] = {
  added: [block(1, "essay", "2026-10-20T14:00"), block(1, "essay", "2026-10-21T09:00")],
  removed: [block(2, "book", "2026-10-20T20:00")],
  moved: [{ item_id: 3, title: "PS5", before: [["2026-10-20T09:00", "2026-10-20T11:00"]], after: [["2026-10-22T09:00", "2026-10-22T11:00"]] }],
}

describe("change list", () => {
  it("counts items, not blocks, and says when deadlines hold", () => {
    expect(summary(changes)).toBe("3 items change · all deadlines met")
    expect(summary({ late_hours: { PS5: 1.5 } })).toBe("Nothing moves · PS5 1h 30m late")
  })

  it("a preview names only what the change makes later (18 Nov: Push said an overdue draft was 11.02 h late)", () => {
    const draft = { late_hours: { "edit article draft": 11.02 } }
    expect(summary({ ...draft, late_hours_before: { "edit article draft": 11.02 } })).toBe("Nothing moves · nothing new is late")
    expect(summary({ late_hours: { "edit article draft": 11.02, essay: 2 }, late_hours_before: { "edit article draft": 11.02, essay: 0.5 } })).toBe("Nothing moves · essay 2h late")
    expect(summary({ late_hours: { PS5: 1.5 }, late_hours_before: {} })).toBe("Nothing moves · PS5 1h 30m late")
    expect(summary({ late_hours_before: { PS5: 1.5 } })).toBe("Nothing moves · all deadlines met")
    expect(summary(draft)).toBe("Nothing moves · edit article draft 11h late") // What changed: the plan's lateness
  })

  it("gives each item one line", () => {
    expect(lines(changes, "2026-10-20")).toEqual([
      { title: "PS5", text: "9am → Thu 9am" },
      { title: "essay", text: "new at 2pm" },
      { title: "book", text: "off the plan" },
    ])
  })
})

describe("a moved item's line names what actually moved (23 Nov, Friday Notes: \"HW 12: Sun 19:45 → Sun 19:45\")", () => {
  const move = (before: string[][], after: string[][]) => lines({ moved: [{ item_id: 7, title: "HW 12", before, after }] }, "2026-10-20")[0].text
  it("its start, when that moves", () => {
    expect(move([["2026-10-25T19:45", "2026-10-25T21:00"]], [["2026-10-25T20:30", "2026-10-25T21:45"]])).toBe("Sun 7:45pm → Sun 8:30pm")
  })
  it("where its first stretch ends, when only that moves", () => {
    expect(move([["2026-10-25T19:45", "2026-10-25T21:00"]], [["2026-10-25T19:45", "2026-10-25T20:30"]])).toBe("Sun 7:45pm, until 8:30pm instead of 9pm")
  })
  it("its later times, when only those move", () => {
    expect(move([["2026-10-25T19:45", "2026-10-25T21:00"], ["2026-10-26T09:00", "2026-10-26T10:00"]], [["2026-10-25T19:45", "2026-10-25T21:00"], ["2026-10-27T09:00", "2026-10-27T10:00"]])).toBe("Sun 7:45pm; its later times move")
  })
})

describe("because (What changed, 3 Nov)", () => {
  it("says what you did, each kind once, in order", () => {
    expect(because([{ actor: "you", command: "drop" }, { actor: "you", command: "settings_set" }, { actor: "you", command: "drop" }])).toBe("After you deleted something and changed a setting.")
  })
  it("three or more read as a list", () => {
    expect(because([{ actor: "you", command: "add" }, { actor: "you", command: "pin" }, { actor: "you", command: "pace" }])).toBe("After you added something, pinned a block and changed the pace.")
  })
  it("a command it has no words for is said by its name", () => {
    expect(because([{ actor: "you", command: "frobnicate_all" }])).toBe("After you used frobnicate all.")
  })
  it("nothing in particular", () => {
    expect(because([])).toBe("Friday planned again on its own.")
  })
  it("Friday's own runs aren't said as yours", () => {
    expect(because([{ actor: "worker", command: "sync" }])).toBe("After Friday read your calendars.")
  })
})
