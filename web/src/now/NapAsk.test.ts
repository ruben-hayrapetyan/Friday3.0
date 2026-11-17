// The things being timed, as the nap's question says them (16 Nov: a nap asks whether to stop timing them).
import { describe, expect, it } from "vitest"
import { named } from "./NapAsk"

describe("what's being timed, said", () => {
  it("names one, two, or a list ending in and", () => {
    expect(named([{ item_id: 1, title: "PS5" }])).toBe("PS5")
    expect(named([{ item_id: 1, title: "PS5" }, { item_id: 2, title: "Laundry" }])).toBe("PS5 and Laundry")
    expect(named([{ item_id: 1, title: "PS5" }, { item_id: 2, title: "Laundry" }, { item_id: 3, title: "Reading" }])).toBe("PS5, Laundry and Reading")
  })
  it("says a task with no name as a task", () => {
    expect(named([{ item_id: 1, title: null }])).toBe("a task")
  })
})
