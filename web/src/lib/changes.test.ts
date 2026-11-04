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
    expect(summary({ late_hours: { PS5: 1.5 } })).toBe("Nothing moves · PS5 1.5 h late")
  })

  it("gives each item one line", () => {
    expect(lines(changes, "2026-10-20")).toEqual([
      { title: "PS5", text: "9am → Thu 9am" },
      { title: "essay", text: "new at 2pm" },
      { title: "book", text: "off the plan" },
    ])
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
