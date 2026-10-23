import { describe, expect, it } from "vitest"
import type { Schemas } from "@/api/client"
import { lines, summary } from "./changes"

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
      { title: "PS5", text: "09:00 → Thu 09:00" },
      { title: "essay", text: "new at 14:00" },
      { title: "book", text: "off the plan" },
    ])
  })
})
